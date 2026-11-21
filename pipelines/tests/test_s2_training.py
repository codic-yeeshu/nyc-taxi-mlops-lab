import dagster as dg
import mlflow
import pytest
from fakes import FakeRedshift, LocalArtifacts, unloading_redshift

from labpipes.defs import training
from labpipes.defs.feature_check import check_feature_month
from labpipes.resources import MlflowTracking


def test_feature_contract_rejects_post_trip_column():
    class LeakyRedshift(FakeRedshift):
        def query(self, sql):
            assert "information_schema.columns" in sql
            return [{
                "column_name": "trip_distance", "data_type": "double precision",
                "character_maximum_length": None,
            }]

    redshift = LeakyRedshift(cluster_id="lab", database="lab", db_user="labadmin")
    result = check_feature_month(redshift, "2024-04")
    assert not result.passed


@pytest.mark.parametrize(("candidate_mae", "latency_ms", "passes"), [
    (4.5, 2.0, True),
    (4.5, 26.0, False),
    (4.9, 2.0, False),
])
def test_only_a_passing_run_registers_and_sets_challenger(tmp_path, monkeypatch, candidate_mae, latency_ms, passes):
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    mlflow.set_tracking_uri(uri)
    mlflow.create_experiment("trip-duration", artifact_location=str(tmp_path / "mlflow-artifacts"))
    redshift = unloading_redshift(root=str(tmp_path))
    monkeypatch.setattr(training, "check_feature_month", lambda *_: dg.AssetCheckResult(passed=True))
    comparisons = iter([5.0, candidate_mae])
    monkeypatch.setattr(training, "evaluate", lambda *_: {
        "mae_min": next(comparisons), "p95_latency_ms": latency_ms,
    })

    result = dg.materialize(
        [training.training_set, training.trained_model, training.eval_report, training.beats_champion, training.challenger],
        resources={
            "redshift": redshift,
            "artifacts": LocalArtifacts(bucket="lab-artifacts", root=str(tmp_path)),
            "tracking": MlflowTracking(tracking_uri=uri),
        },
        raise_on_error=False,
    )
    client = mlflow.MlflowClient(tracking_uri=uri)
    versions = client.search_model_versions("name = 'trip-duration'")
    if not passes:
        assert not result.success and not versions
    else:
        assert result.success and len(versions) == 1
        assert client.get_model_version_by_alias("trip-duration", "challenger").version == versions[0].version
        assert client.get_registered_model("trip-duration").aliases == {"challenger": versions[0].version}
        assert {"training_window", "holdout_month", "features_version", "git_sha",
                "mae_min", "p95_latency_ms", "champion_mae_min"} <= versions[0].tags.keys()
