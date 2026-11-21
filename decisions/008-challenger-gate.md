# 008: Challenger gate

Stage: S2 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Compare mean absolute error in minutes on the same April holdout trips. Require at least a 3% relative reduction in MAE and in-process single-row p95 latency at or below 25 ms. Before a champion exists, use the v1 zone-pair and hour baseline for comparison.

## Rejected alternative

Require a 1% relative reduction in MAE at the same latency budget.

## Why

MAE expresses error in minutes and gives individual large errors less influence than RMSE. A 3% hurdle calls for a larger gain before changing the challenger. The latency cap keeps prediction speed part of the decision.

## What would show this was wrong

Revisit if repeated holdouts show that ordinary month-to-month variation exceeds 3%, or if a model under the in-process budget consistently misses the deployed service's latency target.
