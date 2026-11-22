#!/usr/bin/env bash
# One line per piece of the lab: what state it's in, and whether that's what a working lab needs.
# Read-only (S4, given): it changes nothing, so it's safe to run at any time.
#
#   scripts/health.sh
#
# Needs this session's AWS credentials in the environment, gh logged in, jq, and Python 3.
# Exit status: 0 when every line is OK, 1 otherwise.
set -uo pipefail
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
bad=0

line() { # STATUS NAME DETAIL
  printf '%-4s  %-12s %s\n' "$1" "$2" "$3"
  [[ $1 == OK ]] || bad=1
}

if ! who=$(aws sts get-caller-identity --query Arn --output text 2>&1); then
  line FAIL session "AWS credentials don't work: export this session's from Learner Lab ($(tail -1 <<<"$who" | cut -c1-80))"
  exit 1
fi
line OK session "${who##*/}"

repo=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || repo=""
if [[ -z $repo ]] || ! runners=$(gh api --paginate "repos/$repo/actions/runners" 2>/dev/null | jq -s '[.[].runners[]]'); then
  line FAIL runners "could not read the GitHub runner list"
  runners='[]'
fi
if hosts=$(aws ec2 describe-instances \
  --filters Name=tag:project,Values=mlops-lab Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[].Instances[]' --output json 2>&1); then
  for role in app platform llm; do
    instances=$(jq --arg role "$role" '[.[] | select(any(.Tags[]; .Key == "role" and .Value == $role))]' <<<"$hosts")
    if [[ $(jq length <<<"$instances") != 1 ]]; then
      line FAIL "$role" "expected exactly one active lab host"
      continue
    fi
    host_state=$(jq -r '.[0].State.Name' <<<"$instances")
    host_ip=$(jq -r '.[0].PublicIpAddress // empty' <<<"$instances")
    runner=$(jq -r --arg name "lab-$role" '.[] | select(.name == $name) | .status' <<<"$runners")
    detail="$host_state${host_ip:+, $host_ip}, runner ${runner:-not registered}"
    # The LLM host gets its runner in S6; until then an unregistered one is fine.
    if [[ $host_state == running && ( $runner == online || ( -z $runner && $role == llm ) ) ]]; then
      line OK "$role" "$detail"
    else
      line FAIL "$role" "$detail"
    fi
    if [[ $role == app ]]; then
      app=$host_ip
      groups=$(jq -r '.[0].SecurityGroups[].GroupId' <<<"$instances")
    fi
  done
else
  line FAIL hosts "could not read EC2 state: $hosts"
fi

if ! ip=$(curl -4 -fsS -m 5 https://checkip.amazonaws.com); then
  line WARN laptop-ip "could not determine this terminal's public IPv4"
elif [[ -z ${groups:-} ]]; then
  line FAIL laptop-ip "could not resolve the app's security groups"
else
  group_ids=()
  while read -r group; do group_ids+=("$group"); done <<<"$groups"
  if cidrs=$(aws ec2 describe-security-groups --group-ids "${group_ids[@]}" \
    --query 'SecurityGroups[].IpPermissions[] | [?IpProtocol==`-1` || (IpProtocol==`tcp` && FromPort<=`80` && ToPort>=`80`)].IpRanges[].CidrIp' \
    --output text 2>&1); then
    if python3 -c 'import ipaddress, sys
address = ipaddress.IPv4Address(sys.argv[1])
sys.exit(not any(address in ipaddress.ip_network(cidr) for cidr in sys.stdin.read().split()))' "$ip" <<<"$cidrs"; then
      line OK laptop-ip "$ip is allowed by an app security group for TCP port 80"
    else
      line WARN laptop-ip "$ip is outside the app security groups' IPv4 CIDRs for TCP port 80"
    fi
  else
    line FAIL laptop-ip "could not read app ingress: $cidrs"
  fi
fi

state() { # NAME STATE WANTED HINT
  if [[ $2 == "$3" ]]; then
    line OK "$1" "$2"
  else
    line FAIL "$1" "$(tail -1 <<<"$2"): $4"
  fi
}
rds=$(aws rds describe-db-instances --db-instance-identifier lab --query 'DBInstances[0].DBInstanceStatus' --output text 2>&1)
state rds "$rds" available "Dagster and MLflow need it (aws rds start-db-instance, ~7 min)"
rs=$(aws redshift describe-clusters --cluster-identifier lab --query 'Clusters[0].ClusterStatus' --output text 2>&1)
state redshift "$rs" available "ingestion and the marts need it (aws redshift resume-cluster, ~3 min)"
nb=$(aws sagemaker describe-notebook-instance --notebook-instance-name lab --query NotebookInstanceStatus --output text 2>&1)
# Nothing but exploration needs the notebook, so stopped is a working lab (and cheaper).
if [[ $nb == Stopped ]]; then
  line OK notebook "Stopped (when you need it: aws sagemaker start-notebook-instance --notebook-instance-name lab, ~6 min)"
else
  state notebook "$nb" InService "aws sagemaker start-notebook-instance, ~6 min"
fi

if [[ -n ${app:-} ]]; then
  if r=$(curl -fsS -m 10 "http://$app/predict" -H 'Content-Type: application/json' \
      -d '{"pickup_zone_id": 132, "dropoff_zone_id": 230, "pickup_datetime": "2024-03-08T17:05:00"}' 2>&1); then
    who=$(jq -r '.model | "\(.name) \(.alias // "") \(.version)"' <<<"$r")
    if jq -e '.model.alias == "champion"' <<<"$r" >/dev/null; then line OK predict "$who"; else line WARN predict "answering, but from $who (fallback)"; fi
  else
    line FAIL predict "no answer from $app ($(tail -1 <<<"$r" | cut -c1-60))"
  fi
else
  line FAIL predict "the app has no resolved public IPv4"
fi

if [[ -n $repo ]]; then
  read -r result age < <(gh api "repos/$repo/actions/workflows/status.yaml/runs?per_page=1" \
    -q '.workflow_runs[0] | "\(.conclusion // .status) \((now - (.created_at | fromdateiso8601)) / 60 | floor)"' 2>/dev/null)
  if [[ $result == success && ${age:-999} -le 40 ]]; then
    line OK status "Dagster answered the status run ${age} min ago"
  elif [[ $result == success ]]; then
    line WARN status "last good status run ${age} min ago: run it now (gh workflow run status.yaml)"
  else
    line FAIL status "last status run: ${result:-none}${age:+ ${age} min ago}: run it now (gh workflow run status.yaml), then read its log"
  fi
else
  line FAIL status "could not resolve this lab's GitHub repository"
fi
exit $bad
