# 005: Trip table sort and distribution

Stage: S1 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Use `DISTSTYLE AUTO` on both trip tables and lead with pickup time. The raw sort key is `tpep_pickup_datetime` and the staging sort key is `pickup_at`.

## Rejected alternative

Keep AUTO distribution with `source_file` first in raw and `trip_month` first in staging.

## Why

A pickup-time sort key helps Redshift skip blocks for time-range trip queries. AUTO leaves distribution tuning to Redshift as the tables grow. A file- or month-first layout would favor the predicates used in monthly replacement and profiling.

## What would show this was wrong

Revisit if query and load timings show that monthly reloads dominate and testing a file- or month-first layout makes them materially faster.
