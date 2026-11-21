"""Keep the last approved rows for each month so a later mart refresh excludes rejected loads."""

import dagster as dg

from ..partitions import check_month, trip_months
from ..resources import RedshiftData
from ..sql import statements
from .staging import stg_trips


@dg.asset(partitions_def=trip_months, deps=[stg_trips], group_name="staging", kinds={"redshift"}, pool="redshift")
def mart_ready_trips(context: dg.AssetExecutionContext, redshift: RedshiftData) -> dg.MaterializeResult:
    month = check_month(context.partition_key)
    records = context.instance.get_records_for_run(
        context.run.run_id, of_type=dg.DagsterEventType.ASSET_CHECK_EVALUATION,
    ).records
    blocking_results = [
        evaluation.passed
        for record in records
        if (evaluation := record.event_log_entry.asset_check_evaluation) is not None
        and evaluation.asset_key == stg_trips.key
        and evaluation.partition == month
        and evaluation.blocking
    ]
    if not blocking_results or not all(blocking_results):
        raise dg.Failure("Select stg_trips and run its blocking quality check before publishing this month.")
    redshift.execute(*statements("mart_ready_trips", month=month))
    return dg.MaterializeResult()
