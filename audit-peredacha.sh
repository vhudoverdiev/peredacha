#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_PATH="${BASH_SOURCE[0]}"

if command -v readlink >/dev/null 2>&1; then
  RESOLVED_PATH="$(readlink -f "$SCRIPT_PATH" 2>/dev/null || true)"
  if [ -n "$RESOLVED_PATH" ]; then
    SCRIPT_PATH="$RESOLVED_PATH"
  fi
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "$SCRIPT_PATH")" >/dev/null 2>&1 && pwd)"
AUDIT_SCRIPT="$SCRIPT_DIR/deploy/server-audit.sh"

if [ ! -f "$AUDIT_SCRIPT" ]; then
  PROJECT_DIR="${PROJECT_DIR:-/opt/peredacha}"
  FALLBACK_AUDIT_SCRIPT="$PROJECT_DIR/deploy/server-audit.sh"
  if [ -f "$FALLBACK_AUDIT_SCRIPT" ]; then
    AUDIT_SCRIPT="$FALLBACK_AUDIT_SCRIPT"
  fi
fi

if [ ! -f "$AUDIT_SCRIPT" ]; then
  echo "Error: audit script not found: $AUDIT_SCRIPT"
  echo "Run this command from a full Peredacha project checkout."
  exit 1
fi

exec bash "$AUDIT_SCRIPT" "$@"
