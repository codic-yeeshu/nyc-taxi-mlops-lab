# 004: Monthly warehouse ingestion

Stage: S1 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Use Redshift COPY to load each month's Parquet file into a temporary landing table. Replace that file's rows in `ingest.raw_trips` within the same transaction.

## Rejected alternative

Query the source Parquet directly through Redshift Spectrum external tables.

## Why

COPY gives `ingest.raw_trips` a physical copy that staging can reuse. One transaction keeps the previous month intact if a reload fails. Spectrum avoids storing duplicate data in Redshift, with queries scanning the S3 files as needed.

## What would show this was wrong

Revisit if measured COPY latency or local storage dominates the workload and most months are rarely queried after ingestion.
