#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <worker_base_url> <songs.jsonl>" >&2
  exit 1
fi

WORKER_BASE_URL="$1"
JSONL_PATH="$2"

if [[ ! -f "$JSONL_PATH" ]]; then
  echo "JSONL file not found: $JSONL_PATH" >&2
  exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" ]] && continue
  curl -sS -X POST "${WORKER_BASE_URL%/}/songs/upsert" \
    -H "Content-Type: application/json" \
    -d "$line" >/dev/null
  echo "Seeded song payload"
done < "$JSONL_PATH"

echo "D1 seed completed."
