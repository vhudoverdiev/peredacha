#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
AUDIT_SCRIPT="$SCRIPT_DIR/deploy/server-audit.sh"

if [ ! -f "$AUDIT_SCRIPT" ]; then
  echo "Error: audit script not found: $AUDIT_SCRIPT"
  echo "Run this command from a full Peredacha project checkout."
  exit 1
fi

exec bash "$AUDIT_SCRIPT" "$@"
