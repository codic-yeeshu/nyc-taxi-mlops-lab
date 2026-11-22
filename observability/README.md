# observability/

Given in S5. Metrics only: LLM tracing (Langfuse) arrives with the assistant in S6.

- `alloy/`: Alloy scrape targets and shared configuration. `budget.alloy` keeps the telemetry selected in [decision 014](../decisions/014-active-series-budget.md). Format with `docker run --rm -v "$PWD/observability/alloy:/c" grafana/alloy:v1.19.2 fmt -w /c/<file>`.
- `rules/`: Prometheus recording and alerting rules and their promtool unit tests. `make check` runs them. The observability workflow loads the rules into Grafana Cloud, one namespace per file (`lab-<file>`).
- `slo.yaml`: the measurements, objectives, and reasons from [decision 013](../decisions/013-rider-slos.md).
- `dashboards/ride-app.json`: import it in Grafana via **Dashboards → New → Import** and select the Cloud Prometheus data source in the dashboard.
- `push-rules.sh`: promtool check and test, then load the rules (needs `lab/grafana` in Secrets Manager).
- `alloy-stats.sh`: what Alloy on this host has sent and had refused, and its active series. The status workflow adds it to both status artifacts.

## Connect Grafana Cloud

1. Open your Grafana Cloud stack. In **Administration → Users and access → Cloud access policies**, create a stack-scoped policy with `metrics:write`, `metrics:read`, `rules:write`, and `rules:read`. Add a token to the policy and save it securely.
2. In the Cloud Portal, open your stack's **Prometheus → Details**. Copy the remote-write URL ending in `/api/prom/push` and the numeric Prometheus username.
3. Review and apply the Terraform plan that creates the `lab/grafana` container. Run the command below from your laptop. It uses your exported Learner Lab credentials. If you keep the three `aws_*` credentials in a local file instead, insert its path after `python3 -` on the first line. The token prompt is hidden and the payload travels over stdin into Secrets Manager.

   ```bash
   python3 - <<'PY'
   import getpass
   import json
   import os
   import subprocess
   import sys
   import warnings
   from pathlib import Path
   from urllib.parse import urlsplit

   env = os.environ.copy()
   if len(sys.argv) == 2:
       keys = {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}
       credentials = {}
       for line in Path(sys.argv[1]).expanduser().read_text().splitlines():
           key, _, value = line.partition("=")
           key = key.strip().upper()
           if key in keys:
               credentials[key] = value.strip().strip("'\"")
       if set(credentials) != keys or not all(credentials.values()):
           raise SystemExit("The credential file must contain all three Learner Lab values.")
       env.update(credentials)

   sys.stdin = open("/dev/tty")
   url = input("Prometheus remote-write URL: ").strip()
   parsed = urlsplit(url)
   if parsed.scheme != "https" or not parsed.hostname or not parsed.path.endswith("/api/prom/push"):
       raise SystemExit("Use the HTTPS remote-write URL ending in /api/prom/push.")
   user = input("Prometheus numeric username: ").strip()
   if not user.isascii() or not user.isdecimal():
       raise SystemExit("Use the numeric Prometheus username from Cloud Portal.")
   warnings.simplefilter("error", getpass.GetPassWarning)
   token = getpass.getpass("Cloud Access Policy token: ").strip()
   if not token:
       raise SystemExit("A token is required.")
   subprocess.run(
       ["aws", "secretsmanager", "put-secret-value", "--region", "us-east-1",
        "--secret-id", "lab/grafana", "--secret-string", "file:///dev/stdin",
        "--query", "VersionId", "--output", "text", "--no-cli-pager"],
       input=json.dumps({"url": url, "user": user, "token": token}),
       text=True,
       check=True,
       env=env,
   )
   PY
   ```

4. Set `gh variable set LAB_OBSERVABILITY --body on` and dispatch `gh workflow run observability.yaml`. The host instance profiles read the secret when Alloy starts.

## Verify S5

- Capture the unfiltered baseline in Grafana Explore with `count by (host, job) ({__name__=~".+"})`. After deploying the budget, exercise three app releases. In this repo each release starts with a push to `main`, followed by CI and a CD switch reviewed in `app-production`. Let each release finish before starting the next. Compare the Explore count with the sum of `alloy.active_series` from the app and platform status artifacts. The combined S5 target is 5,000. Cloud counts can retain old series for a while.
- Import the dashboard and check the availability, latency, and model-backed panels. A window without traffic shows no SLI. The dashboard's recent burn curves use the fast paging windows.
- In an approved drill, send steady valid predictions and pause the champion serving container long enough to observe fallback quotes and the model-backed SLO alert. Record when the fault began, when the alert fired, and when champion responses returned. Restore the container and verify the public response and the alert status.

The cost of container metrics: cAdvisor needs the Docker socket, which gives Alloy root-equivalent access to the host. Traefik deliberately has none.
