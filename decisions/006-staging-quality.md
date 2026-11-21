# 006: Blocking and warning thresholds for staging

Stage: S1 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Block publication for an empty month, a row count mismatch against the Parquet footer, any null pickup or drop-off timestamp, or any negative distance. Also block if exact duplicates exceed 0.01%, trip durations outside (0, 180] minutes exceed 0.5%, or rows with an invalid or missing pickup or drop-off zone ID exceed 2%. Warn when null passenger counts exceed 15%.

## Rejected alternative

Block on row count and timestamp failures, and warn on duplicate, duration, zone, and distance failures.

## Why

January through April 2024 had 13,069,067 staged rows, exactly matching the source footers. There were zero null trip timestamps or negative distances and one exact staged duplicate. The highest monthly rates were 0.10% for out-of-range durations, 1.06% for invalid or missing zones, and 11.90% for null passenger counts. The chosen allowances let the observed months through while blocking larger changes in the fields that affect the mart. Passenger count is absent from the mart's calculations.

## What would show this was wrong

Revisit if a schema-valid month with a confirmed source change repeatedly breaches the limits, or if a month passes and its zone-hour statistics still show material corruption.
