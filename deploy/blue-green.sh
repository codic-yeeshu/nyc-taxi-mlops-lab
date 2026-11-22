#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

web=deploy/web.sh
url=http://127.0.0.1:${HTTP_PORT:-80}
compose=(docker compose -f deploy/compose.web.yaml)
trip='{"pickup_zone_id":132,"dropoff_zone_id":230,"pickup_datetime":"2024-03-08T17:05:00"}'
invalid_trip='{"pickup_zone_id":999,"dropoff_zone_id":230,"pickup_datetime":"2024-03-08T17:05:00"}'

other_colour() {
    case "$1" in
        blue) echo green ;;
        green) echo blue ;;
        *) echo "Expected a live app colour." >&2; return 1 ;;
    esac
}

check_sha() {
    [[ "$1" =~ ^[0-9a-f]{40}$ ]] || { echo "Expected a full app commit SHA." >&2; return 1; }
}

smoke() {
    local colour=$1 sha=$2 status
    "$web" smoke "$colour" "$sha"
    curl -fsS --max-time 5 -H "X-Lab-Color: $colour" "$url/healthz" | jq -e '.status == "ok"' >/dev/null
    status=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' -H "X-Lab-Color: $colour" \
        -H 'Content-Type: application/json' -d "$invalid_trip" "$url/predict")
    [[ "$status" == 422 ]]
}

live_probe() {
    local sha=$1 response
    for _ in {1..24}; do
        if response=$(curl -fsS --max-time 3 "$url/version" 2>/dev/null) &&
            jq -e --arg sha "$sha" '.git_sha == $sha and .image_tag == $sha' <<<"$response" >/dev/null &&
            curl -fsS --max-time 5 -H 'Content-Type: application/json' -d "$trip" "$url/predict" 2>/dev/null |
                jq -e '(.duration_minutes | type == "number" and . > 0) and (.model.name | type == "string")' >/dev/null; then
            return 0
        fi
        sleep 1
    done
    echo "The public route did not return a healthy prediction from $sha." >&2
    return 1
}

stage() {
    local sha=$1 live idle seed old_image
    check_sha "$sha"
    : "${IMAGE_PREFIX:?set IMAGE_PREFIX}"
    live=$("$web" live)
    export BLUE_TAG GREEN_TAG
    BLUE_TAG=$("$web" tag blue)
    GREEN_TAG=$("$web" tag green)
    if [[ "$live" == none ]]; then
        "$web" init
        old_image=$(docker inspect lab-app-app-1 --format '{{.Config.Image}}' 2>/dev/null || true)
        seed=${old_image##*:}
        BLUE_TAG=${seed:-$sha}
        check_sha "$BLUE_TAG"
        "${compose[@]}" up -d --no-deps --wait --wait-timeout 120 app-blue
        "$web" switch blue
        live=blue
    fi
    "$web" prepare
    idle=$(other_colour "$live")
    case "$idle" in
        blue) BLUE_TAG=$sha ;;
        green) GREEN_TAG=$sha ;;
    esac
    "${compose[@]}" pull "app-$idle"
    "${compose[@]}" up -d --no-deps --wait --wait-timeout 120 "app-$idle"
    smoke "$idle" "$sha"
}

switch_app() {
    local colour=$1 sha=$2 old old_sha started elapsed
    check_sha "$sha"
    old=$("$web" live)
    old_sha=$("$web" tag "$old")
    [[ "$colour" == "$(other_colour "$old")" && "$("$web" tag "$colour")" == "$sha" ]] ||
        { echo "The requested build must be on the idle colour." >&2; return 1; }
    smoke "$colour" "$sha"
    started=$(date +%s%3N)
    "$web" switch "$colour"
    if ! live_probe "$sha"; then
        "$web" switch "$old"
        live_probe "$old_sha"
        return 1
    fi
    elapsed=$(( $(date +%s%3N) - started ))
    printf 'Traffic switched %s → %s in %s ms (first verified prediction).\n' "$old" "$colour" "$elapsed"
    if docker container inspect lab-app-app-1 >/dev/null 2>&1; then
        docker rm -f lab-app-app-1 >/dev/null
    fi
    "$web" status
}

case "${1:-}" in
    stage) stage "${2:?app commit SHA required}" ;;
    switch) switch_app "${2:?colour required}" "${3:?app commit SHA required}" ;;
    rollback)
        idle=$(other_colour "$("$web" live)")
        switch_app "$idle" "$("$web" tag "$idle")"
        ;;
    *) echo "Usage: $0 stage SHA | switch COLOUR SHA | rollback" >&2; exit 2 ;;
esac
