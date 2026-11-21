"""Block positional COPY when the landed Parquet schema differs from the contract."""

import dagster as dg

from ..contracts import Column, trips_schema
from ..partitions import trip_months
from ..resources import DataBucket
from .trip_files import trip_files


def _column_signature(columns: list[Column]) -> list[str]:
    return [f"{column.name.lower()} {column.type}" for column in columns]


@dg.asset_check(asset=trip_files, partitions_def=trip_months, blocking=True)
def schema_contract(
    context: dg.AssetCheckExecutionContext, data_bucket: DataBucket,
) -> dg.AssetCheckResult:
    expected = _column_signature(trips_schema())
    actual = _column_signature(data_bucket.footer(context.partition_key).columns)
    passed = actual == expected
    return dg.AssetCheckResult(
        passed=passed,
        severity=dg.AssetCheckSeverity.ERROR,
        description=(
            "Parquet columns match the contract in order."
            if passed
            else "The Parquet column names, order or storage types differ from the contract."
        ),
        metadata={"expected": dg.MetadataValue.json(expected), "actual": dg.MetadataValue.json(actual)},
    )
