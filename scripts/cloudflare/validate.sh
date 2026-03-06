#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_PATH="$ROOT_DIR/infra/cloudflare/wrangler.toml"

run_wrangler() {
  if command -v wrangler >/dev/null 2>&1; then
    wrangler "$@"
  else
    npx --yes wrangler@4 "$@"
  fi
}

required_files=(
  "$ROOT_DIR/infra/cloudflare/wrangler.toml"
  "$ROOT_DIR/infra/cloudflare/.dev.vars.example"
  "$ROOT_DIR/infra/cloudflare/env/common.secrets.example"
  "$ROOT_DIR/infra/cloudflare/env/vote-api.secrets.example"
  "$ROOT_DIR/infra/cloudflare/env/playback-service.secrets.example"
  "$ROOT_DIR/infra/cloudflare/env/playback-stream.secrets.example"
  "$ROOT_DIR/infra/cloudflare/env/encoder.secrets.example"
  "$ROOT_DIR/infra/cloudflare/env/modal-dispatch-service.secrets.example"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required Cloudflare boilerplate file: $file" >&2
    exit 1
  fi
done

# Keep phase 1 boilerplate non-deploying and resource-free.
forbidden_patterns=(
  '^main\\s*='
  '^assets\\s*='
  '^workers_dev\\s*='
  '^route\\s*='
  '^routes\\s*='
  '^\\[\\[kv_namespaces\\]\\]'
  '^\\[\\[d1_databases\\]\\]'
  '^\\[\\[r2_buckets\\]\\]'
  '^\\[\\[queues.producers\\]\\]'
  '^\\[\\[queues.consumers\\]\\]'
  '^\\[\\[durable_objects.bindings\\]\\]'
)

for pattern in "${forbidden_patterns[@]}"; do
  if rg -n "$pattern" "$CONFIG_PATH" >/dev/null; then
    echo "Forbidden phase 1 setting found in $CONFIG_PATH: $pattern" >&2
    exit 1
  fi
done

python3 - "$CONFIG_PATH" <<'PY'
import sys
import tomllib
from pathlib import Path

config_path = Path(sys.argv[1])
with config_path.open("rb") as f:
    data = tomllib.load(f)

for required_key in ("name", "compatibility_date"):
    if required_key not in data:
        raise SystemExit(f"Missing required key in {config_path}: {required_key}")
PY

if [[ "${SKIP_WRANGLER_VALIDATE:-0}" == "1" ]]; then
  echo "Skipping Wrangler CLI check (SKIP_WRANGLER_VALIDATE=1)."
else
  run_wrangler --version >/dev/null
fi

echo "Cloudflare boilerplate validation passed."
