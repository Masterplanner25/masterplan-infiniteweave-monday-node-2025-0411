#!/usr/bin/env bash
# Usage: ./run_all_examples.sh
# Runs the three aindy-examples projects end-to-end against a local docker-compose stack.

set -e

BASE_URL="${AINDY_BASE_URL:-http://localhost:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
API_KEY=""
JWT_TOKEN=""
PASS_COUNT=0
FAIL_COUNT=0

extract_json_value() {
  local json="$1"
  local key="$2"
  printf '%s' "$json" \
    | tr -d '\r\n' \
    | sed 's/[[:space:]]//g' \
    | sed -n "s/.*\"${key}\":\"\([^\"]*\)\".*/\1/p"
}

print_result() {
  local name="$1"
  local status="$2"
  echo "[$status] $name"
}

setup_auth() {
  local stamp email username password register_response key_response

  echo "Checking API health at $BASE_URL/health ..."
  curl -fsS "$BASE_URL/health" >/dev/null

  stamp="$(date +%s)"
  email="examples_${stamp}@local.test"
  username="examples_${stamp}"
  password="Examples123!"

  echo "Registering temporary user ..."
  register_response="$(curl -fsS -X POST "$BASE_URL/auth/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$email\",\"password\":\"$password\",\"username\":\"$username\"}")"

  JWT_TOKEN="$(extract_json_value "$register_response" "access_token")"
  if [ -z "$JWT_TOKEN" ]; then
    echo "Failed to parse JWT token from /auth/register response"
    exit 1
  fi

  echo "Creating platform API key ..."
  key_response="$(curl -fsS -X POST "$BASE_URL/platform/keys" \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"examples-runner","scopes":["platform.admin"]}')"

  API_KEY="$(extract_json_value "$key_response" "key")"
  if [ -z "$API_KEY" ]; then
    echo "Failed to parse platform API key from /platform/keys response"
    exit 1
  fi

  export AINDY_BASE_URL="$BASE_URL"
  export AINDY_API_KEY="$API_KEY"
}

run_memory_analyzer() {
  (
    cd "$SCRIPT_DIR/memory-analyzer"
    python main.py
  )
}

run_event_automation() {
  local start_pid
  (
    cd "$SCRIPT_DIR/event-automation"
    python main.py reset >/dev/null 2>&1 || true
    python main.py start &
    start_pid=$!
    sleep 5
    python main.py approve --reviewer run_all_examples
    wait "$start_pid"
    python main.py reset >/dev/null 2>&1 || true
  )
}

run_scheduled_agent() {
  (
    cd "$SCRIPT_DIR/scheduled-agent"
    python main.py setup --cron "* * * * *" --webhook "https://webhook.site/replace"
    python main.py run-now
    python main.py cancel
  )
}

run_example() {
  local name="$1"
  local fn="$2"

  if "$fn"; then
    PASS_COUNT=$((PASS_COUNT + 1))
    print_result "$name" "PASS"
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    print_result "$name" "FAIL"
  fi
}

setup_auth
run_example "memory-analyzer" run_memory_analyzer
run_example "event-automation" run_event_automation
run_example "scheduled-agent" run_scheduled_agent

echo
echo "Summary: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi

exit 0