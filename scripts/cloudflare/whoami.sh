#!/usr/bin/env bash
set -euo pipefail

run_wrangler() {
  if command -v wrangler >/dev/null 2>&1; then
    wrangler "$@"
  else
    npx --yes wrangler@4 "$@"
  fi
}

run_wrangler whoami
