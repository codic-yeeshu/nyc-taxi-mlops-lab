# 012: Manual lab recovery

Stage: S4 · Date: 2026-11-22 · Author: YEESHU · Drafted by agent: yes

## Choice

Run recovery from the laptop after starting Learner Lab and refreshing the session credentials. The command inspects the three lab EC2 hosts, RDS, and Redshift. An explicit `--apply` starts or resumes resources as needed and waits for them to be ready.

## Rejected alternative

Also resume Redshift automatically when the platform host boots.

## Why

The script handles repeated state checks and waits. A person decides when to bring the lab up, so a platform reboot cannot resume a cluster paused to save budget. Notebook startup, public ingress changes, deployments, and model promotion remain separate actions. The operator checks the rider response and reviews the GitHub status artifact to confirm recovery.

## What would show this was wrong

Revisit if waiting for someone to run the command repeatedly delays recovery enough to miss lab exercises, and the budget allows Redshift to resume on every platform boot.
