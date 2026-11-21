"""Run monthly ingestion when a trip object appears or changes."""

import json

import dagster as dg

from ..partitions import MONTH, trip_months
from ..resources import DataBucket


ingest_month = dg.define_asset_job(
    "ingest_month",
    selection=dg.AssetSelection.assets(
        "taxi_zones", "trip_files", "raw_trips", "stg_trips", "mart_ready_trips", "zone_hour_stats",
    ),
)


@dg.sensor(job=ingest_month, minimum_interval_seconds=60)
def trip_files_sensor(context: dg.SensorEvaluationContext, data_bucket: DataBucket):
    seen = json.loads(context.cursor or "{}")
    current = {file.month: file.etag for file in data_bucket.trip_files() if MONTH.fullmatch(file.month)}
    next_cursor = {}
    requests = []
    partition_keys = []

    for month in sorted(seen.keys() | current.keys()):
        previous_etag, revision = seen.get(month, [None, 0])
        etag = current.get(month)
        if etag is not None and etag != previous_etag:
            revision += 1
            requests.append(dg.RunRequest(partition_key=month, run_key=f"{month}:{revision}"))
            partition_keys.append(month)
        next_cursor[month] = [etag, revision]

    return dg.SensorResult(
        run_requests=requests,
        dynamic_partitions_requests=[trip_months.build_add_request(partition_keys)] if partition_keys else [],
        skip_reason=dg.SkipReason("No new or changed trip files.") if not requests else None,
        cursor=json.dumps(next_cursor, sort_keys=True),
    )
