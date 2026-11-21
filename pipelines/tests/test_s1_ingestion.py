import dagster as dg
from fakes import LOG, FakeRedshift, fake_bucket, fake_redshift

from labpipes.contracts import Column, trips_schema
from labpipes.defs.mart_ready_trips import mart_ready_trips
from labpipes.defs.quality import staging_quality
from labpipes.defs.raw_trips import raw_trips
from labpipes.defs.schema_check import schema_contract
from labpipes.defs.sensor import trip_files_sensor
from labpipes.defs.staging import stg_trips
from labpipes.defs.trip_files import trip_files
from labpipes.partitions import trip_months


def test_schema_contract_blocks_reordered_columns_but_accepts_case_changes():
    @dg.asset(deps=[trip_files], partitions_def=trip_months)
    def downstream():
        return None

    expected = trips_schema()
    for columns, passed in [
        ([Column(column.name.lower(), column.type) for column in expected], True),
        (expected[1:2] + expected[:1] + expected[2:], False),
    ]:
        with dg.instance_for_test() as instance:
            instance.add_dynamic_partitions("trip_months", ["2024-01"])
            result = dg.materialize(
                [trip_files, schema_contract, downstream],
                resources={"data_bucket": fake_bucket({"2024-01": ("etag", columns)})},
                instance=instance,
                partition_key="2024-01",
                raise_on_error=False,
            )
        assert result.get_asset_check_evaluations()[0].passed is passed
        assert result.success is passed
        assert (len(result.asset_materializations_for_node("downstream")) == 1) is passed


def test_sensor_requests_a_new_run_when_an_object_reverts_to_an_earlier_etag():
    cursor = None
    for etag, keys in [
        ("first", ["2024-01:1"]),
        ("first", []),
        ("second", ["2024-01:2"]),
        ("first", ["2024-01:3"]),
    ]:
        with dg.build_sensor_context(cursor=cursor) as context:
            result = trip_files_sensor(
                context, data_bucket=fake_bucket({"2024-01": (etag, trips_schema())}),
            )
        assert [request.run_key for request in result.run_requests] == keys
        assert [request.partition_key for request in result.run_requests] == ["2024-01"] * len(keys)
        cursor = result.cursor


def test_copy_uses_a_landing_table_and_replaces_only_the_selected_month():
    month = "2024-01"
    with dg.instance_for_test() as instance:
        instance.add_dynamic_partitions("trip_months", [month])
        result = dg.materialize(
            [trip_files, schema_contract, raw_trips],
            resources={
                "data_bucket": fake_bucket({month: ("etag", trips_schema())}),
                "redshift": fake_redshift(),
            },
            instance=instance,
            partition_key=month,
        )
    assert result.success
    assert LOG[3:6] == [
        "copy landing from 's3://data/trips/yellow_tripdata_2024-01.parquet' iam_role default format as parquet",
        "delete from ingest.raw_trips where source_file = 'yellow_tripdata_2024-01.parquet'",
        "insert into ingest.raw_trips select landing.*, 'yellow_tripdata_2024-01.parquet' from landing",
    ]


def test_publication_requires_a_quality_pass_for_the_same_month_and_run():
    @dg.asset_check(asset=stg_trips, partitions_def=trip_months, blocking=True)
    def test_gate(context: dg.AssetCheckExecutionContext):
        return dg.AssetCheckResult(passed=context.partition_key == "2024-01")

    with dg.instance_for_test() as instance:
        instance.add_dynamic_partitions("trip_months", ["2024-01", "2024-02"])
        for month, assets, passed in [
            ("2024-01", [stg_trips, test_gate, mart_ready_trips], True),
            ("2024-02", [stg_trips, test_gate, mart_ready_trips], False),
            ("2024-01", [mart_ready_trips], False),
        ]:
            result = dg.materialize(
                assets, resources={"redshift": fake_redshift()},
                instance=instance, partition_key=month, raise_on_error=False,
            )
            assert result.success is passed
            assert any(sql.startswith("insert into staging.mart_ready_trips") for sql in LOG) is passed


def test_staging_policy_warns_on_missing_passengers_and_blocks_invalid_durations():
    class ProfiledRedshift(FakeRedshift):
        invalid_durations: int

        def query(self, sql: str) -> list[dict]:
            if "distinct_rows" in sql:
                return [{
                    "rows": 3, "duplicate_rows": 0, "null_timestamps": 0, "null_passengers": 1,
                    "nonpositive_duration": self.invalid_durations, "over_3h": 0,
                    "unknown_zone": 0, "negative_distance": 0,
                }]
            return super().query(sql)

    month = "2024-01"
    with dg.instance_for_test() as instance:
        instance.add_dynamic_partitions("trip_months", [month])
        for invalid_durations in (0, 1):
            result = dg.materialize(
                [stg_trips, staging_quality, mart_ready_trips],
                resources={
                    "data_bucket": fake_bucket({month: ("etag", trips_schema())}),
                    "redshift": ProfiledRedshift(
                        cluster_id="lab", database="lab", db_user="labadmin", invalid_durations=invalid_durations,
                    ),
                },
                instance=instance, partition_key=month, raise_on_error=False,
            )
            checks = {check.check_name: check for check in result.get_asset_check_evaluations()}
            assert checks["passenger_count_completeness"].severity == dg.AssetCheckSeverity.WARN
            assert not checks["passenger_count_completeness"].passed
            assert checks["staging_quality_gate"].passed is (invalid_durations == 0)
            assert result.success is (invalid_durations == 0)
