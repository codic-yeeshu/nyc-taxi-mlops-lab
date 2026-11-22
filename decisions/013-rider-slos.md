# 013: Rider service level objectives

Stage: S5 · Date: 2026-11-22 · Author: YEESHU · Drafted by agent: yes

## Choice

Over 30 days, aim for 99% non-5xx responses at the public entrypoint, 95% of `POST /predict` responses within 500 ms in the app, and 99% model-backed quotes. Page when burn exceeds 14.4× in both 5 min and 1 hour or 6× in both 30 min and 6 hours.

## Rejected alternative

Set 99.9% non-5xx responses, 95% within 250 ms, and 99.5% model-backed quotes.

## Why

The lab has low and intermittent traffic, plus planned restarts and deployments. The selected targets leave room for brief transitions. The 500 ms bucket covers the normal serving timeout and application overhead. A static fallback can return 200, so model-backed quotes have a separate objective. Paired alert windows distinguish sustained burn from a short spike.

## What would show this was wrong

Revisit if riders experience poor quotes while these indicators repeatedly meet their objectives, or if routine lab transitions page often enough that alerts lose value. An idle request window has no measured SLI.
