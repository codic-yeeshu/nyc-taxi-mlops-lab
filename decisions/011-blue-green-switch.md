# 011: When app traffic switches

Stage: S3 · Date: 2026-11-22 · Author: YEESHU · Drafted by agent: yes

## Choice

Deploy the new build to the idle colour and verify its health, requested commit, valid prediction, and HTTP 422 for an invalid request. Require manual approval in GitHub's `app-production` environment before switching traffic.

## Rejected alternative

Switch traffic automatically after the same smoke tests pass.

## Why

Manual approval gives the reviewer time to inspect the tested commit and smoke results before exposing the build to riders. It adds a wait to CD. Keeping the previous colour running gives the reviewer a rollback target without building or pulling another image.

## What would show this was wrong

Revisit if review routinely delays small releases without catching issues, or if the existing smoke tests miss failures the reviewer needs to see.
