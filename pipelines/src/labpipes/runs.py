"""Read what an earlier asset recorded, so a later step uses exactly the version it produced."""

import dagster as dg


def last_metadata(instance: dg.DagsterInstance, asset: str) -> dict:
    """The metadata values of an asset's latest materialization ({} if it has none)."""
    records = instance.fetch_materializations(dg.AssetKey(asset), limit=1).records
    if not records:
        return {}
    return {k: v.value for k, v in records[0].asset_materialization.metadata.items()}


def run_metadata(instance: dg.DagsterInstance, run_id: str, asset: str) -> dict:
    """Read a materialization from this run, even when another run finishes more recently."""
    records = instance.get_records_for_run(
        run_id, of_type=dg.DagsterEventType.ASSET_MATERIALIZATION, ascending=False,
    ).records
    for record in records:
        materialization = record.event_log_entry.asset_materialization
        if materialization and materialization.asset_key == dg.AssetKey(asset):
            return {key: value.value for key, value in materialization.metadata.items()}
    raise dg.Failure(f"Run {asset} in this job before running its downstream steps.")
