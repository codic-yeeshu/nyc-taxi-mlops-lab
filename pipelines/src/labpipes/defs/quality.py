"""Check a staging partition against its source count and the measured quality policy."""

import dagster as dg

from ..partitions import check_month, trip_months
from ..resources import DataBucket, RedshiftData
from ..sql import statements
from .staging import stg_trips


@dg.multi_asset_check(
    specs=[
        dg.AssetCheckSpec("passenger_count_completeness", asset=stg_trips, partitions_def=trip_months),
        dg.AssetCheckSpec("staging_quality_gate", asset=stg_trips, partitions_def=trip_months, blocking=True),
    ],
    can_subset=True,
)
def staging_quality(
    context: dg.AssetCheckExecutionContext, data_bucket: DataBucket, redshift: RedshiftData,
):
    month = check_month(context.partition_key)
    (query,) = statements("profile_trips", month=month)
    (profile,) = redshift.query(query)
    rows = int(profile["rows"])
    source_rows = data_bucket.footer(month).num_rows
    denominator = max(rows, 1)
    null_passenger_pct = 100 * profile["null_passengers"] / denominator
    duplicate_pct = 100 * profile["duplicate_rows"] / denominator
    invalid_duration_pct = 100 * (profile["nonpositive_duration"] + profile["over_3h"]) / denominator
    invalid_zone_pct = 100 * profile["unknown_zone"] / denominator

    selected = {key.name for key in context.selected_asset_check_keys}
    if "passenger_count_completeness" in selected:
        yield dg.AssetCheckResult(
            check_name="passenger_count_completeness",
            passed=null_passenger_pct <= 15,
            severity=dg.AssetCheckSeverity.WARN,
            description="At most 15% of trips may have a missing passenger count before warning.",
            metadata={"null_passengers": profile["null_passengers"], "null_passenger_pct": null_passenger_pct},
        )

    if "staging_quality_gate" in selected:
        failures = [
            label for failed, label in [
                (rows == 0, "empty month"),
                (rows != source_rows, "staging row count differs from the Parquet footer"),
                (profile["null_timestamps"] > 0, "null trip timestamps"),
                (duplicate_pct > 0.01, "exact duplicates above 0.01%"),
                (invalid_duration_pct > 0.5, "invalid trip durations above 0.5%"),
                (invalid_zone_pct > 2, "invalid or missing zone IDs above 2%"),
                (profile["negative_distance"] > 0, "negative trip distance"),
            ] if failed
        ]
        yield dg.AssetCheckResult(
            check_name="staging_quality_gate",
            passed=not failures,
            severity=dg.AssetCheckSeverity.ERROR,
            description=", ".join(failures) if failures else "All blocking staging limits passed.",
            metadata={
                **profile,
                "source_rows": source_rows,
                "duplicate_pct": duplicate_pct,
                "invalid_duration_pct": invalid_duration_pct,
                "invalid_zone_pct": invalid_zone_pct,
            },
        )
