# 001: Runner credentials

Stage: S0 · Date: 2026-11-21 · Author: YEESHU · Drafted by agent: yes

## Choice

Use the EC2 host’s `LabInstanceProfile` as the source of AWS credentials for workloads on the app runner. The S0 CD job authenticates to GHCR with its GitHub token.

## Rejected alternative

Store temporary Learner Lab session credentials as GitHub Actions secrets for the deploy runner.

## Why

The instance profile supplies temporary credentials to the host and renews them automatically. GitHub secrets would need manual rotation whenever the Learner Lab session expires.

## What would show this was wrong

Revisit this if a required AWS operation fails under `LabInstanceProfile`, or if deployment moves to a runner outside EC2 that cannot use the profile.
