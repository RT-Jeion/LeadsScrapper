#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILE_DIR="$SCRIPT_DIR/BraveDebug"
mkdir -p "$PROFILE_DIR"

if command -v brave-browser >/dev/null 2>&1; then
  BROWSER_BIN="brave-browser"
elif command -v brave >/dev/null 2>&1; then
  BROWSER_BIN="brave"
else
  echo "Brave browser executable not found. Install Brave or update the script path." >&2
  exit 1
fi

exec "$BROWSER_BIN" --remote-debugging-port=9222 --user-data-dir="$PROFILE_DIR" --no-first-run --no-default-browser-check
