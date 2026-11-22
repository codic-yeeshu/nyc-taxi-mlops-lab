# scripts/

- `register-runner.sh [app|platform|llm]`: register a host as a self-hosted runner over SSM (S0 builds this).
- `gh-secrets.sh`: copy session credentials into GitHub secrets, only for workflows that call AWS from GitHub-hosted runners (S10's destroy). CI and CD don't need it.
- `catch-up.sh N`: rebuild infrastructure and pipeline state for `stage-N`.
- `health.sh` (S4, given): read-only, one line per piece of the lab, exit 0 only when all are OK. Start every morning and every incident with it.
- `verify-teardown.sh` (S10, given): every billable thing left in us-east-1 and us-west-2, one line each; you're done when it prints nothing.
- `restore.sh --plan`: preview the lab's recovery state. Use `--apply` to start stopped EC2 hosts and RDS, resume paused Redshift, and wait for readiness. See [the restore runbook](../runbooks/restore.md).
- `python3 scripts/store-s6-secret.py wiki [aws_credentials_file]`: save the instructor's HTTPS wiki base URL and bearer token to `lab/wiki`. Use `langfuse` in place of `wiki` to save the project API keys to `lab/langfuse` after Terraform creates it. Both commands prompt for the secret and print only the AWS version ID. They use exported Learner Lab credentials or the optional local credentials file.
