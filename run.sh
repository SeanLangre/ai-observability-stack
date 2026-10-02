#!/usr/bin/env bash
# Start the monitoring stack, then llama-server in the foreground (Ctrl+C stops it).
# Paths come from .env (copy .env.example). Tuning flags can be overridden per run
# without editing this file, e.g.:
#   N_CPU_MOE=9 ./run.sh
#   EXTRA_ARGS="-ctk q8_0 -ctv q8_0" ./run.sh
#   EXTRA_ARGS="-np 1" ./run.sh
# The slots exporter reads the flags from the process, so each run shows up with
# its own llamacpp_config_info labels in Grafana.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -f "$STACK_DIR/.env" ]]; then
  echo "Missing $STACK_DIR/.env (copy .env.example and set the paths)" >&2
  exit 1
fi
set -a; source "$STACK_DIR/.env"; set +a
MODEL_PATH="${MODEL_PATH/#\~/$HOME}"

NGL="${NGL:-99}"
N_CPU_MOE="${N_CPU_MOE:-10}"
CTX="${CTX:-64000}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

# 1. Docker and the stack
systemctl is-active --quiet docker || sudo systemctl enable --now docker
docker compose --project-directory "$STACK_DIR" up -d

# 2. llama-server. Dashboard: http://localhost:3000/d/llama-server/llama-server
#    (login admin / GRAFANA_ADMIN_PASSWORD, otherwise admin)
cd "$LLAMA_CPP_DIR"
# shellcheck disable=SC2086  # EXTRA_ARGS is meant to word-split
exec ./build/bin/llama-server \
  -m "$MODEL_PATH" \
  -ngl "$NGL" \
  --n-cpu-moe "$N_CPU_MOE" \
  -c "$CTX" \
  --no-reasoning-preserve \
  --host 127.0.0.1 \
  --port 8080 \
  --metrics \
  $EXTRA_ARGS
