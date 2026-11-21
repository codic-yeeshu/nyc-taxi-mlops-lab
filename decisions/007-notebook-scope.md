# 007: Notebook scope

Stage: S2 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Use the notebook for data exploration and small side-by-side fits of the baseline and LightGBM. Record prototype metrics in the separate `trip-duration-notebook` experiment. Dagster owns the official training runs, holdout evaluation, registry, and challenger alias.

## Rejected alternative

Keep the notebook for SQL, charts, and inspection of existing pipeline results, with all fitting done in Dagster.

## Why

Sample fits let us try an idea and inspect how the models behave on slices before spending time on a full pipeline build. Interactive fits consume notebook compute, and small random samples can give a different result from the full holdout. The separate experiment makes the origin of each result visible.

## What would show this was wrong

Revisit if the notebook routinely runs large jobs or if prototype metrics are being used as evidence for registry changes.
