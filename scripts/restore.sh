#!/usr/bin/env bash
# Inspect or start the lab's existing EC2, RDS and Redshift resources after Start Lab.
set -euo pipefail
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""

usage() {
  echo "Usage: scripts/restore.sh [--plan | --apply]"
  echo "Default: --plan (read-only). --apply starts or resumes the lab and waits for AWS readiness."
}

mode=${1:---plan}
if (( $# > 1 )); then usage >&2; exit 2; fi
case $mode in
  --plan|--apply) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

fail() { echo "$*" >&2; exit 1; }

host_state() {
  aws ec2 describe-instances \
    --filters "Name=tag:project,Values=mlops-lab" "Name=tag:role,Values=$1" \
      Name=instance-state-name,Values=pending,running,stopping,stopped \
    --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text
}

rds_state() {
  aws rds describe-db-instances --db-instance-identifier lab \
    --query 'DBInstances[?TagList[?Key==`project` && Value==`mlops-lab`]].DBInstanceStatus' --output text
}

redshift_state() {
  aws redshift describe-clusters --cluster-identifier lab \
    --query 'Clusters[?Tags[?Key==`project` && Value==`mlops-lab`]].ClusterStatus' --output text
}

check_state() {
  case "$1:$2" in
    ec2:running|ec2:pending|ec2:stopping|ec2:stopped|\
    rds:available|rds:starting|rds:stopping|rds:stopped|\
    redshift:available|redshift:resuming|redshift:pausing|redshift:paused) ;;
    *) fail "$3 has unexpected state '${2:-missing}'. See runbooks/restore.md." ;;
  esac
}

# Resolve every resource and validate state before making any write calls.
aws sts get-caller-identity --query Account --output text >/dev/null
roles=(app platform llm)
ids=()
states=()
for role in "${roles[@]}"; do
  row=$(host_state "$role")
  [[ -n $row && $row != *$'\n'* ]] || fail "Expected one active lab EC2 instance tagged role=$role."
  read -r id state <<<"$row"
  [[ $id =~ ^i-[[:xdigit:]]+$ ]] || fail "Invalid EC2 ID for $role."
  check_state ec2 "$state" "$role"
  ids+=("$id")
  states+=("$state")
  printf '%-9s %s (%s)\n' "$role" "$state" "$id"
done
rds=$(rds_state)
redshift=$(redshift_state)
check_state rds "$rds" RDS
check_state redshift "$redshift" Redshift
printf '%-9s %s\n' rds "$rds" redshift "$redshift"
if [[ $mode == --plan ]]; then
  echo "Use --apply to start stopped resources and resume paused Redshift."
  exit 0
fi

restore() {
  local service=$1 name=$2 ready=$3 state=$4 id=${5:-}
  local requested=0 begin=$SECONDS
  if [[ $state != "$ready" ]]; then
    echo "$name: waiting for $ready (initial state: $state)"
  fi
  while [[ $state != "$ready" ]]; do
    check_state "$service" "$state" "$name"
    if (( SECONDS - begin >= 1200 )); then
      fail "$name did not reach $ready after 20 minutes (last state: $state)."
    fi
    if (( requested == 0 )); then
      case "$service:$state" in
        ec2:stopped) aws ec2 start-instances --instance-ids "$id" >/dev/null; requested=1 ;;
        rds:stopped) aws rds start-db-instance --db-instance-identifier lab >/dev/null; requested=1 ;;
        redshift:paused) aws redshift resume-cluster --cluster-identifier lab >/dev/null; requested=1 ;;
      esac
    fi
    sleep 15
    case $service in
      ec2) state=$(aws ec2 describe-instances --instance-ids "$id" \
        --query 'Reservations[0].Instances[0].State.Name' --output text) ;;
      rds) state=$(rds_state) ;;
      redshift) state=$(redshift_state) ;;
    esac
  done
  echo "$name: $ready ($((SECONDS - begin))s)"
}

# These resources can recover in parallel. Wait for every job and report any failures.
pids=()
for i in "${!roles[@]}"; do
  restore ec2 "${roles[i]}" running "${states[i]}" "${ids[i]}" &
  pids+=("$!")
done
restore rds RDS available "$rds" &
pids+=("$!")
restore redshift Redshift available "$redshift" &
pids+=("$!")
failed=0
for pid in "${pids[@]}"; do
  wait "$pid" || failed=1
done
(( failed == 0 )) || fail "Recovery incomplete. Check the errors above, then see runbooks/restore.md."

echo "AWS resources are ready. Verify champion predictions and refresh status per runbooks/restore.md."
