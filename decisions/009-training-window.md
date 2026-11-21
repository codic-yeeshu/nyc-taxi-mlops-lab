# 009: Training window and holdout

Stage: S2 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Train on January through March 2024 and evaluate on April 2024. Fit the zone-pair distance lookup using the training months.

## Rejected alternative

Train on February and March and use the same April holdout.

## Why

The earlier three months contain more trips and broader coverage of zone pairs. A later holdout measures how models trained on past trips perform on a new month. The shorter window reduces training cost and emphasizes recent trips.

## What would show this was wrong

Revisit if rolling holdouts show the two-month window consistently lowers error, or if the three-month window exceeds the platform's resource budget.
