# 014: S5 active-series budget

Stage: S5 · Date: 2026-11-22 · Author: YEESHU · Drafted by agent: yes

## Choice

Target at most 5,000 active series across the S5 app and platform hosts, reserving the remaining 5,000 for the LLM host and later stages.

## Rejected alternative

Spend up to 7,500 series in S5 to retain more detailed per-container metrics.

## Why

Keep the rider, model and Traefik metrics used by dashboards, SLOs and the later canary. Keep basic host health and named-container CPU and memory. Drop other exporter metrics and remove deployment-specific container IDs, image names and Docker labels from the retained container metrics. Keeping names preserves per-service diagnostics across container replacement.

## What would show this was wrong

Revisit if the combined count exceeds 5,000 after three app deployments, or if an incident exposes a missing metric that would have helped. Compare the unfiltered Grafana baseline with the filtered series count and the Alloy counts on both hosts after deployment.
