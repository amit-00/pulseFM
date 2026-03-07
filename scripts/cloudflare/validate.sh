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
  "$ROOT_DIR/infra/cloudflare/env/playback-worker.secrets.example"
  "$ROOT_DIR/services/playback-worker/src/entry.py"
  "$ROOT_DIR/services/playback-worker/migrations/d1/0001_init.sql"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required Cloudflare playback-worker file: $file" >&2
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

for required_key in ("name", "main", "compatibility_date"):
    if required_key not in data:
        raise SystemExit(f"Missing required key in {config_path}: {required_key}")

if not isinstance(data.get("durable_objects"), dict):
    raise SystemExit("Missing durable_objects section")
if not data["durable_objects"].get("bindings"):
    raise SystemExit("Missing durable_objects.bindings")

if not data.get("d1_databases"):
    raise SystemExit("Missing d1_databases binding")
PY

required_patterns=(
  '^main\s*='
  '^compatibility_flags\s*=\s*\["python_workers"\]'
  '^\[\[durable_objects.bindings\]\]'
  '^class_name\s*=\s*"PlaybackStateDurableObject"'
  '^\[\[d1_databases\]\]'
  '^database_id\s*='
)

for pattern in "${required_patterns[@]}"; do
  if ! rg -n "$pattern" "$CONFIG_PATH" >/dev/null; then
    echo "Required playback-worker setting missing in $CONFIG_PATH: $pattern" >&2
    exit 1
  fi
done

if [[ "${SKIP_WRANGLER_VALIDATE:-0}" == "1" ]]; then
  echo "Skipping Wrangler CLI check (SKIP_WRANGLER_VALIDATE=1)."
else
  run_wrangler --version >/dev/null
fi

echo "Cloudflare playback-worker validation passed."
