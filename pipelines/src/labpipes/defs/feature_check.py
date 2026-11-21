"""Verify the feature table's exact schema and each month's usable training rows."""

import dagster as dg

from ..contracts import features_contract
from ..partitions import check_month, trip_months
from ..resources import RedshiftData
from .features import trip_features


def check_feature_month(redshift: RedshiftData, month: str) -> dg.AssetCheckResult:
    month = check_month(month)
    contract = features_contract()
    expected = [(column["name"], column["type"]) for column in [
        *contract["keys"], *contract["inputs"], contract["label"],
    ]]
    columns = redshift.query(
        "select column_name, data_type, character_maximum_length from information_schema.columns "
        "where table_schema = 'staging' and table_name = 'trip_features' order by ordinal_position"
    )
    actual = [
        (column["column_name"], f"char({column['character_maximum_length']})"
         if column["data_type"] == "character" else column["data_type"])
        for column in columns
    ]
    if actual != expected:
        return dg.AssetCheckResult(
            passed=False,
            description="Feature columns or types differ from the frozen contract.",
            metadata={"expected": dg.MetadataValue.json(expected), "actual": dg.MetadataValue.json(actual)},
        )

    invalid = []
    for column in [*contract["inputs"], contract["label"]]:
        name = column["name"]
        lower, upper = column["range"]
        operator = "<=" if column.get("exclusive_min") else "<"
        invalid.append(f"{name} is null or {name} {operator} {lower} or {name} > {upper}")
    (profile,) = redshift.query(
        f"select count(*) as rows, count(case when {' or '.join(invalid)} then 1 end) as invalid_rows "
        f"from staging.trip_features where trip_month = '{month}'"
    )
    return dg.AssetCheckResult(
        passed=profile["rows"] > 0 and profile["invalid_rows"] == 0,
        description="Feature rows must be present and within the contract ranges.",
        metadata=profile,
    )


@dg.asset_check(asset=trip_features, partitions_def=trip_months, blocking=True)
def feature_contract(context: dg.AssetCheckExecutionContext, redshift: RedshiftData) -> dg.AssetCheckResult:
    return check_feature_month(redshift, context.partition_key)
