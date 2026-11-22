# Runbook: Restore champion predictions after a Learner Lab session ends

Owner: YEESHU · Last triage: 2026-11-22

## When to use it

Start here when the public app times out, returns a fallback prediction, or Dagster or MLflow is missing after restarting Learner Lab.

## Before you start

Start the lab in AWS Academy, then export the current AWS Details credentials in your terminal. Keep credentials outside the repo. Use AWS CLI with access to the lab, sign in to GitHub CLI, and run the commands from the repo root. For SSM tunnels you also need the Session Manager plugin.

## Initial triage

| Check | Observed on 2026-11-22 | What to do | Took |
| --- | --- | --- | --- |
| AWS session and resource reads | STS identified the session. An RDS describe call was explicitly denied by the Learner Lab credential-cancellation policy. The initial script showed RDS, Redshift and SageMaker as absent and omitted host and prediction rows. | Started Learner Lab and refreshed credentials. The next check found all three hosts running and both databases available. | Manual session refresh was untimed. |
| Laptop IPv4 | The script warned because the laptop's individual `/32` was missing from the local variable file. S0 selected public IPv4 ingress. | Updated the health check to test CIDR membership for TCP port 80 on the app's deployed security groups. IPv4 passed with the existing rules. | Included in the 21.79 s end-to-end health check. |
| GitHub status | The last successful run was 351 minutes old. | Dispatched [run 45014520899](https://github.com/codic-yeeshu/nyc-taxi-mlops-lab/actions/runs/45014520899) and downloaded both artifacts. | 15 s from dispatch to completion. |

## Recovery evidence

On November 22, the databases were already up after the earlier morning restore. AWS and the status artifacts supplied the following timestamps. The S4 restore command observed ready AWS resources in its first check and made zero start or resume calls.

| Component | Evidence | Observed time |
| --- | --- | --- |
| RDS | AWS events show recovery started at 04:59:11 UTC and the DB instance started at 05:01:04 UTC. | 1 min 53 s from the first recovery event. |
| Redshift | AWS events show resume started at 04:58:57 UTC and succeeded at 05:02:13 UTC. | 3 min 15 s from the resume event. |
| EC2 and serving | EC2 lists 10:49:12 UTC as the latest launch time for all three hosts. The app status artifact shows the serving container loaded champion at 10:50:06 UTC. Public `/predict` was verified separately. | 54 s from app host launch to champion loaded. |
| Dagster and MLflow | The platform status job queried Dagster and reported the MLflow champion alias by 10:52:31 UTC. | Verified within 3 min 19 s of platform host launch. Exact readiness times were not captured. |

## Steps

1. Run `scripts/health.sh`. Record every warning or failure and its timestamp. If AWS reports an expired token or the Learner Lab credential-cancellation policy, restart the lab session, refresh your exported credentials, and retry.
2. Preview with `scripts/restore.sh --plan`. After confirming the affected resources, run `scripts/restore.sh --apply`. For a manual drill, use `aws ec2 start-instances --instance-ids <stopped-id>`, `aws rds start-db-instance --db-instance-identifier lab`, or `aws redshift resume-cluster --cluster-identifier lab` for the affected resource in `us-east-1`. Record the start and time to `running` or `available`. Pending or stopping resources may need time to settle. Investigate other unexpected states before proceeding.
3. Check the public rider path using the known trip below. If it returns a fallback, inspect the app's serving status and the platform stack over SSM. For interactive checks, reopen the [Dagster and MLflow tunnels](../deploy/compose.platform.yaml) and verify the Dagster code location is loaded and the registered model has a champion alias. Record the time at which each becomes usable.

   ```bash
   app_ip=$(terraform -chdir=infra/live output -raw app_public_ip)
   curl -fsS -m 10 "http://$app_ip/predict" \
     -H 'Content-Type: application/json' \
     -d '{"pickup_zone_id":132,"dropoff_zone_id":230,"pickup_datetime":"2024-03-08T17:05:00"}' |
     jq -e '.model | select(.alias == "champion")'
   ```

4. Run `gh workflow run status.yaml --ref main` and watch the returned run in GitHub. Download its artifacts with `gh run download <run-id> --dir <empty-directory>`. Check `lab-status/lab-status.json` for `infra.rds` and `infra.redshift` both set to `available`. Compare `mlflow.aliases.champion` with `serving.champion.version` in `lab-status-app/lab-status-app.json` and the public response.
5. Run `scripts/health.sh` again. If the laptop IPv4 is outside a deployed allowlist, review the intended access and get approval for any Terraform ingress change before applying it.

## Done when

- Public `/predict` returns the expected champion alias and version. This run returned `trip-duration`, `champion`, version `1`.
- The fresh status run is green and reports both databases available.
- `scripts/health.sh` exits 0.

## What we automated, and what we left as a step

The [S4 decision](../decisions/012-restore-trigger.md) requires an explicit operator command to start billable resources. Instance startup and database recovery run in parallel. AWS Academy session startup, credential refresh, notebook startup, ingress changes, and the final application checks remain operator steps. The notebook can stay stopped until an experiment needs it. The promotion workflow retains ownership of the champion alias.

The optional pause-and-reboot drill was deferred. The live lab was already healthy and the chosen script has no boot trigger.
