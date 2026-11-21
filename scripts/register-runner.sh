#!/usr/bin/env bash
# Register a lab host with GitHub over SSM. Enter the short-lived GitHub
# registration token at the remote prompt. It is never sent as an SSM parameter.
set -euo pipefail
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""

root="$(cd "$(dirname "$0")/.." && pwd)"
role="${1:-app}"
case "$role" in
  app|platform|llm) ;;
  *) echo "Usage: $0 [app|platform|llm]" >&2; exit 2 ;;
esac

repo=$(cd "$root" && gh repo view --json nameWithOwner --jq .nameWithOwner)
policy=$(gh api "repos/$repo/actions/permissions/fork-pr-contributor-approval" --jq .approval_policy)
if [[ "$policy" != all_external_contributors ]]; then
  echo "Set the fork PR approval policy to all external contributors before registering." >&2
  exit 1
fi

instance=$(terraform -chdir="$root/infra/live" output -raw "${role}_instance_id")
label="lab-$role"
url="https://github.com/$repo"
remote_script=$(cat <<'REMOTE'
set -euo pipefail
url=$1
label=$2
cd /opt/actions-runner

if [[ ! -f /var/lib/lab-setup-done ]]; then
  echo "Host setup is still pending. Check /var/log/lab-setup.log." >&2
  exit 1
fi

if [[ -f .runner ]]; then
  jq -e --arg url "$url" --arg label "$label" '
    (.gitHubUrl | rtrimstr("/")) == $url and .agentName == $label
  ' .runner >/dev/null || { echo "This host is already registered to another runner." >&2; exit 1; }
else
  sudo -u runner -- /bin/bash -c '
    set -euo pipefail
    [[ $(uname -m) == aarch64 ]] || { echo "This lab requires an arm64 host." >&2; exit 1; }
    version=2.338.2
    archive=$(mktemp)
    trap "rm -f -- \"\$archive\"" EXIT
    curl -fsSL --retry 3 -o "$archive" \
      "https://github.com/actions/runner/releases/download/v$version/actions-runner-linux-arm64-$version.tar.gz"
    printf "%s  %s\n" 670adb2f268fe21dcbb58b3db0e0aa9d5b3bddfe2c651481336e561ff86de945 "$archive" | sha256sum -c -
    tar -xzf "$archive"
    read -rs -p "GitHub runner registration token: " ACTIONS_RUNNER_INPUT_TOKEN
    printf "\n"
    [[ -n "$ACTIONS_RUNNER_INPUT_TOKEN" ]]
    export ACTIONS_RUNNER_INPUT_TOKEN
    ./config.sh --unattended --url "$1" --name "$2" --labels "$2"
  ' bash "$url" "$label"
fi

if [[ ! -s .service ]]; then
  sudo ./svc.sh install runner
fi
sudo ./svc.sh start
REMOTE
)

printf 'Open %s/settings/actions/runners/new to get the registration token if prompted.\n' "$url"
printf -v command '/bin/bash -c %q bash %q %q' "$remote_script" "$url" "$label"
parameters=$(jq -cn --arg command "$command" '{command: [$command]}')
aws ssm start-session --target "$instance" --document-name AWS-StartInteractiveCommand --parameters "$parameters"

for attempt in {1..12}; do
  online=$(gh api "repos/$repo/actions/runners" --paginate --jq \
    ".runners[] | select(.name == \"$label\" and .status == \"online\") | .labels[] | select(.name == \"$label\") | .name")
  if [[ "$online" == "$label" ]]; then
    printf 'Runner %s is online.\n' "$label"
    exit 0
  fi
  if (( attempt < 12 )); then
    sleep 5
  fi
done
echo "GitHub has not reported runner $label online." >&2
exit 1
