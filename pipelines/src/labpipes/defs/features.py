"""trip_features: one month of model inputs and labels, valid trips only (contracts/features.yaml).

The feature contract check attaches here (feature_check.py): a column that isn't in the contract
stops training before it starts.
"""

import dagster as dg

from ..partitions import check_month, trip_months
from ..resources import RedshiftData
from ..runs import run_metadata
from ..sql import statements


@dg.asset(partitions_def=trip_months, deps=["mart_ready_trips"], group_name="model", kinds={"redshift"}, pool="redshift")
def trip_features(context: dg.AssetExecutionContext, redshift: RedshiftData) -> dg.MaterializeResult:
    month = check_month(context.partition_key)
    run_metadata(context.instance, context.run.run_id, "mart_ready_trips")
    redshift.execute(*statements("trip_features", month=month))
    rows = redshift.scalar(f"select count(*) from staging.trip_features where trip_month = '{month}'")
    return dg.MaterializeResult(metadata={"rows": dg.MetadataValue.int(int(rows))})
