#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEMPLATE_PATH="$ROOT_DIR/cloudflare/wrangler.template.jsonc"

required_files=(
  "$ROOT_DIR/cloudflare/package.json"
  "$ROOT_DIR/cloudflare/wrangler.template.jsonc"
  "$ROOT_DIR/cloudflare/scripts/render-config.mjs"
  "$ROOT_DIR/cloudflare/src/index.ts"
  "$ROOT_DIR/cloudflare/src/station-control.ts"
  "$ROOT_DIR/cloudflare/src/workflow.ts"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required Cloudflare runtime file: $file" >&2
    exit 1
  fi
done

required_patterns=(
  'EXTERNAL_GENERATOR_TOKEN'
  'STATION_CONTROL'
  'GENERATE_SONG_WORKFLOW'
  'StationControl'
  'GenerateSongWorkflow'
)

for pattern in "${required_patterns[@]}"; do
  if ! rg -n "$pattern" "$ROOT_DIR/cloudflare" >/dev/null; then
    echo "Missing required Cloudflare runtime pattern: $pattern" >&2
    exit 1
  fi
done

python3 - "$TEMPLATE_PATH" <<'PY'
import json
import sys
from pathlib import Path

template_path = Path(sys.argv[1])
with template_path.open("r", encoding="utf-8") as f:
    data = json.load(f)

for required_key in ("name", "main", "compatibility_date", "durable_objects", "workflows"):
    if required_key not in data:
        raise SystemExit(f"Missing required key in {template_path}: {required_key}")
PY

echo "Cloudflare runtime validation passed."
