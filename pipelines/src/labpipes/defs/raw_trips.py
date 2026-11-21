"""Load one contracted Parquet file into the Redshift landing table."""

import re

import dagster as dg

from ..contracts import redshift_columns, trips_schema
from ..partitions import source_file, trip_months
from ..resources import DataBucket, RedshiftData
from .trip_files import trip_files


@dg.asset(partitions_def=trip_months, deps=[trip_files], group_name="ingest", kinds={"redshift"}, pool="redshift")
def raw_trips(
    context: dg.AssetExecutionContext, data_bucket: DataBucket, redshift: RedshiftData,
) -> dg.MaterializeResult:
    month = context.partition_key
    filename = source_file(month)
    uri = data_bucket.trip_uri(month)
    if not re.fullmatch(r"s3://[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]/trips/" + re.escape(filename), uri):
        raise ValueError("Trip COPY requires the contracted key in a valid S3 bucket.")
    columns = redshift_columns(trips_schema())
    redshift.execute(
        "create schema if not exists ingest",
        f"create table if not exists ingest.raw_trips ({columns}, source_file varchar(64) not null) "
        "diststyle auto sortkey (tpep_pickup_datetime)",
        f"create temp table landing ({columns})",
        f"copy landing from '{uri}' iam_role default format as parquet",
        f"delete from ingest.raw_trips where source_file = '{filename}'",
        f"insert into ingest.raw_trips select landing.*, '{filename}' from landing",
    )
    rows = redshift.scalar(f"select count(*) from ingest.raw_trips where source_file = '{filename}'")
    return dg.MaterializeResult(metadata={"rows": int(rows), "source": uri})
