#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="panda-trace-collector.service"
ENV_FILE="/etc/panda-trace-collector.env"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
DOCKER_BIN="${PANDA_TRACE_DOCKER_BIN:-$(command -v docker || true)}"

run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

prompt_value() {
  local name="$1"
  local default="$2"
  local value

  read -r -p "${name} [${default}]: " value
  printf '%s' "${value:-$default}"
}

prompt_secret() {
  local name="$1"
  local value="${!name:-}"

  if [[ -n "$value" ]]; then
    printf '%s' "$value"
    return
  fi

  while [[ -z "$value" ]]; do
    read -r -s -p "${name}: " value
    printf '\n' >&2
  done
  printf '%s' "$value"
}

require_no_whitespace() {
  local name="$1"
  local value="$2"

  if [[ "$value" =~ [[:space:]] ]]; then
    printf '%s must not contain whitespace.\n' "$name" >&2
    exit 1
  fi
}

if [[ -z "$PYTHON_BIN" ]]; then
  printf 'python3 is required.\n' >&2
  exit 1
fi

if [[ -z "$DOCKER_BIN" ]]; then
  printf 'docker is required.\n' >&2
  exit 1
fi

case "$REPO_DIR" in
  *[[:space:]]*)
    printf 'Repo path contains whitespace; systemd setup expects a simple path: %s\n' "$REPO_DIR" >&2
    exit 1
    ;;
esac

DEFAULT_BASE_URL="${PANDA_TRACE_BASE_URL:-https://trace.patrikmojzis.com}"
BASE_URL="$(prompt_value "PANDA_TRACE_BASE_URL" "$DEFAULT_BASE_URL")"
API_KEY="$(prompt_secret "PANDA_TRACE_KEY")"

case "$BASE_URL" in
  http://* | https://*) ;;
  *)
    printf 'PANDA_TRACE_BASE_URL must start with http:// or https://.\n' >&2
    exit 1
    ;;
esac

require_no_whitespace "PANDA_TRACE_BASE_URL" "$BASE_URL"
require_no_whitespace "PANDA_TRACE_KEY" "$API_KEY"

ENV_TMP="$(mktemp)"
UNIT_TMP="$(mktemp)"
cleanup() {
  rm -f "$ENV_TMP" "$UNIT_TMP"
}
trap cleanup EXIT

chmod 600 "$ENV_TMP"
cat >"$ENV_TMP" <<EOF
PANDA_TRACE_BASE_URL=${BASE_URL}
PANDA_TRACE_KEY=${API_KEY}
PANDA_TRACE_BATCH_SIZE=${PANDA_TRACE_BATCH_SIZE:-50}
PANDA_TRACE_FLUSH_SECONDS=${PANDA_TRACE_FLUSH_SECONDS:-2}
PANDA_TRACE_DISCOVERY_INTERVAL_SECONDS=${PANDA_TRACE_DISCOVERY_INTERVAL_SECONDS:-5}
PANDA_TRACE_DEFAULT_SEVERITY=${PANDA_TRACE_DEFAULT_SEVERITY:-info}
PANDA_TRACE_DOCKER_BIN=${DOCKER_BIN}
EOF

cat >"$UNIT_TMP" <<EOF
[Unit]
Description=Panda Trace Docker log collector
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${PYTHON_BIN} -m panda_trace_collector
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

run_root install -m 600 -o root -g root "$ENV_TMP" "$ENV_FILE"
run_root install -m 644 -o root -g root "$UNIT_TMP" "$UNIT_FILE"
run_root systemctl daemon-reload
run_root systemctl enable "$SERVICE_NAME"
run_root systemctl restart "$SERVICE_NAME"

printf '\nInstalled %s\n' "$SERVICE_NAME"
printf 'Env file: %s\n' "$ENV_FILE"
printf 'Unit file: %s\n' "$UNIT_FILE"
printf '\nCheck it with:\n'
printf '  sudo systemctl status %s\n' "$SERVICE_NAME"
printf '  sudo journalctl -u %s -f\n' "$SERVICE_NAME"
