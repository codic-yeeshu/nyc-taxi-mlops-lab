"""MLflow operations owned by the approval-gated promotion workflow."""

import json
import math
import os
import re
import sys
from uuid import UUID

from mlflow import MlflowClient

MODEL = "trip-duration"
PROVENANCE = ("training_window", "holdout_month", "features_version", "git_sha")
METRICS = ("mae_min", "champion_mae_min", "p95_latency_ms")


def evaluated_version(client, version):
    if not version or not re.fullmatch(r"[1-9][0-9]*", version):
        raise SystemExit("Choose an evaluated model version or use the current challenger.")
    candidate = client.get_model_version(MODEL, version)
    tags = candidate.tags
    try:
        UUID(tags["dagster_run_id"])
        run = client.get_run(candidate.run_id)
        experiment = client.get_experiment(run.info.experiment_id)
        provenance_matches = all(tags[key] and tags[key] == run.data.tags.get(key) for key in PROVENANCE)
        metrics_match = all(
            math.isfinite(float(tags[key])) and float(tags[key]) == run.data.metrics[key] for key in METRICS
        )
    except (KeyError, TypeError, ValueError):
        raise SystemExit("The version is missing pipeline evaluation evidence.") from None
    if candidate.status != "READY" or run.info.status != "FINISHED" or experiment.name != MODEL:
        raise SystemExit("The model and its pipeline evaluation must be ready.")
    if not provenance_matches or not metrics_match:
        raise SystemExit("The version tags do not match the pipeline evaluation.")
    return {key: tags[key] for key in METRICS}


def main(action, version, previous):
    client = MlflowClient(tracking_uri=os.environ["MLFLOW_TRACKING_URI"])
    aliases = client.get_registered_model(MODEL).aliases
    current = aliases.get("champion", "")
    if action == "resolve":
        selected = version or aliases.get("challenger")
        metrics = evaluated_version(client, selected)
        print(json.dumps({"target": selected, "previous": current, "metrics": metrics}))
    elif action == "promote":
        evaluated_version(client, version)
        if current != previous:
            raise SystemExit("The champion changed while this approval was pending. Dispatch a fresh promotion.")
        if version != current:
            client.set_registered_model_alias(MODEL, "champion", version)
    elif action == "restore":
        if current != version:
            raise SystemExit("The failed promotion no longer owns the alias.")
        if previous:
            client.set_registered_model_alias(MODEL, "champion", previous)
        else:
            client.delete_registered_model_alias(MODEL, "champion")
    else:
        raise SystemExit("Unknown promotion action.")


if __name__ == "__main__":
    main(*sys.argv[1:])
