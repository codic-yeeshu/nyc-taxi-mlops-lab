"""Export a chronological split, train and compare a candidate, then publish only after the gate."""

import math
import os
import re
from datetime import date
from pathlib import Path
from uuid import UUID

import dagster as dg
import mlflow
import pandas as pd
from mlflow.exceptions import MlflowException

import tripmodel
from tripmodel import LABEL, REQUIRED, BaselineModel, LightGBMModel, evaluate, model_signature

from ..contracts import features_contract, mlflow_contract
from ..partitions import check_month
from ..resources import ArtifactBucket, MlflowTracking, RedshiftData
from ..runs import run_metadata
from .feature_check import check_feature_month


class TrainingWindow(dg.Config):
    training_start: str = "2024-01"
    training_end: str = "2024-03"
    holdout_month: str = "2024-04"


MIN_IMPROVEMENT_PCT = 3.0
MAX_P95_LATENCY_MS = 25.0


def _next_month(month: str) -> str:
    current = date.fromisoformat(f"{check_month(month)}-01")
    year, next_month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
    return f"{year:04d}-{next_month:02d}"


def _training_months(config: TrainingWindow) -> list[str]:
    start, end, holdout = map(check_month, (config.training_start, config.training_end, config.holdout_month))
    if start > end or _next_month(end) != holdout:
        raise dg.Failure("Use a contiguous training window followed by the next month as holdout.")
    months = [start]
    while months[-1] < end:
        months.append(_next_month(months[-1]))
    return months


def _unload(bucket: ArtifactBucket, prefix: str, query: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket.bucket):
        raise dg.Failure("Training artifacts require a valid S3 bucket name.")
    escaped_query = query.replace("'", "''")
    return f"unload ('{escaped_query}') to '{bucket.uri(prefix)}/part_' iam_role default format as parquet allowoverwrite"


@dg.asset(deps=["trip_features"], group_name="model", kinds={"redshift", "s3"}, pool="redshift")
def training_set(
    context: dg.AssetExecutionContext, config: TrainingWindow, redshift: RedshiftData, artifacts: ArtifactBucket,
) -> dg.MaterializeResult:
    months = _training_months(config)
    for month in [*months, config.holdout_month]:
        result = check_feature_month(redshift, month)
        if not result.passed:
            raise dg.Failure(f"Feature contract failed for {month}.", metadata=result.metadata)

    start, end = months[0], months[-1]
    holdout = check_month(config.holdout_month)
    run_prefix = f"training/{UUID(context.run.run_id).hex}"
    paths = {f"{part}_prefix": f"{run_prefix}/{part}" for part in ("train", "holdout", "distances")}
    columns = ", ".join([*REQUIRED, LABEL])
    select_features = f"select {columns} from staging.trip_features where trip_month"
    redshift.execute(
        _unload(artifacts, paths["train_prefix"], f"{select_features} between '{start}' and '{end}'"),
        _unload(artifacts, paths["holdout_prefix"], f"{select_features} = '{holdout}'"),
        _unload(
            artifacts, paths["distances_prefix"],
            "select pickup_zone_id, dropoff_zone_id, median(trip_distance) as est_distance_miles "
            f"from staging.trip_feature_distances where trip_month between '{start}' and '{end}' group by 1, 2",
        ),
    )
    return dg.MaterializeResult(metadata={
        **paths, "training_window": f"{start}..{end}", "holdout_month": holdout,
    })


@dg.asset(deps=[training_set], group_name="model", kinds={"mlflow", "lightgbm"})
def trained_model(
    context: dg.AssetExecutionContext, artifacts: ArtifactBucket, tracking: MlflowTracking,
) -> dg.MaterializeResult:
    exported = run_metadata(context.instance, context.run.run_id, "training_set")
    train = artifacts.read_parquet(exported["train_prefix"])
    distances = artifacts.read_parquet(exported["distances_prefix"])
    if train.empty:
        raise dg.Failure("The exported training set is empty.")
    model = LightGBMModel().fit(train, distances)
    example = train.loc[:, REQUIRED].head(3).astype("int64")
    tracking.client()
    tags = {
        "training_window": exported["training_window"],
        "holdout_month": exported["holdout_month"],
        "features_version": str(features_contract()["version"]),
        "git_sha": os.environ.get("GIT_SHA", "unknown"),
    }
    with mlflow.start_run(run_name=f"LightGBM {tags['training_window']}", tags=tags) as run:
        mlflow.log_param("training_rows", len(train))
        info = mlflow.pyfunc.log_model(
            name="model", python_model=model, signature=model_signature(), input_example=example,
            code_paths=[str(Path(tripmodel.__file__).parent)],
        )
    return dg.MaterializeResult(metadata={
        "model_uri": info.model_uri, "mlflow_run_id": run.info.run_id, **tags,
    })


def _champion_version(client, name: str) -> str | None:
    try:
        return client.get_registered_model(name).aliases.get("champion")
    except MlflowException as error:
        if error.error_code != "RESOURCE_DOES_NOT_EXIST":
            raise
        return None


@dg.asset(deps=[training_set, trained_model], group_name="model", kinds={"mlflow"})
def eval_report(
    context: dg.AssetExecutionContext, artifacts: ArtifactBucket, tracking: MlflowTracking, redshift: RedshiftData,
) -> dg.MaterializeResult:
    exported = run_metadata(context.instance, context.run.run_id, "training_set")
    candidate = run_metadata(context.instance, context.run.run_id, "trained_model")
    client = tracking.client()
    name = mlflow_contract()["registered_model"]
    version = _champion_version(client, name)
    if version is None:
        baseline = BaselineModel().fit(
            artifacts.read_parquet(exported["train_prefix"]), artifacts.read_parquet(exported["distances_prefix"]),
        )

        def predict_reference(data: pd.DataFrame):
            return baseline.predict(None, data)
    else:
        predict_reference = mlflow.pyfunc.load_model(f"models:/{name}/{version}").predict

    holdout = artifacts.read_parquet(exported["holdout_prefix"])
    if holdout.empty:
        raise dg.Failure("The exported holdout is empty.")
    boroughs = {row["location_id"]: row["borough"] for row in redshift.query(
        "select location_id, borough from ingest.taxi_zones"
    )}
    reference = evaluate(predict_reference, holdout, boroughs)
    metrics = evaluate(mlflow.pyfunc.load_model(candidate["model_uri"]).predict, holdout, boroughs)
    metrics["champion_mae_min"] = reference["mae_min"]
    with mlflow.start_run(run_id=candidate["mlflow_run_id"]):
        mlflow.log_metrics(metrics)
        mlflow.log_param("comparison", f"champion v{version}" if version is not None else "v1 baseline")
    return dg.MaterializeResult(metadata={
        **metrics, "comparison": f"champion v{version}" if version is not None else "v1 baseline",
        "champion_version": version or "",
    })


@dg.asset_check(asset=eval_report, blocking=True)
def beats_champion(context: dg.AssetCheckExecutionContext) -> dg.AssetCheckResult:
    report = run_metadata(context.instance, context.run.run_id, "eval_report")
    candidate, reference, latency = (report[key] for key in ("mae_min", "champion_mae_min", "p95_latency_ms"))
    passed = (
        all(math.isfinite(value) and value >= 0 for value in (candidate, reference, latency))
        and candidate < reference
        and candidate <= reference * (1 - MIN_IMPROVEMENT_PCT / 100)
        and latency <= MAX_P95_LATENCY_MS
    )
    return dg.AssetCheckResult(passed=passed, metadata={
        "mae_min": candidate, "champion_mae_min": reference, "p95_latency_ms": latency,
        "required_improvement_pct": MIN_IMPROVEMENT_PCT, "max_p95_latency_ms": MAX_P95_LATENCY_MS,
    })


@dg.asset(deps=[eval_report, trained_model], group_name="model", kinds={"mlflow"})
def challenger(context: dg.AssetExecutionContext, tracking: MlflowTracking) -> dg.MaterializeResult:
    run_id = context.run.run_id
    records = context.instance.get_records_for_run(run_id, of_type=dg.DagsterEventType.ASSET_CHECK_EVALUATION).records
    if not any(
        evaluation.asset_key == eval_report.key and evaluation.check_name == "beats_champion"
        and evaluation.blocking and evaluation.passed
        for record in records
        if (evaluation := record.event_log_entry.asset_check_evaluation) is not None
    ):
        raise dg.Failure("Run the blocking beats_champion check in this job before publishing.")

    contract = mlflow_contract()
    name = contract["registered_model"]
    model = run_metadata(context.instance, run_id, "trained_model")
    report = run_metadata(context.instance, run_id, "eval_report")
    client = tracking.client()
    if (_champion_version(client, name) or "") != report["champion_version"]:
        raise dg.Failure("The champion changed during evaluation. Rerun training against the current champion.")

    metadata = model | report
    tags = {key: str(metadata[key]) for key in contract["version_tags"]}
    versions = client.search_model_versions(f"name = '{name}'")
    version = next((v for v in versions if v.tags.get("dagster_run_id") == run_id), None)
    if version is None:
        version = mlflow.register_model(model["model_uri"], name, tags={**tags, "dagster_run_id": run_id})
    client.set_registered_model_alias(name, "challenger", version.version)
    return dg.MaterializeResult(metadata={"version": str(version.version), **tags})


train_model = dg.define_asset_job(
    "train_model", selection=dg.AssetSelection.assets(training_set, trained_model, eval_report, challenger),
    tags={"lab/training": "model"},
)
