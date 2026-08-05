#!/usr/bin/env bash
# Ensure report/cache/memory dirs are writable for the non-root app user.
# Railway volumes are often mounted as root:root — chown when we start as root.
set -euo pipefail

REPORTS_DIR="${TRADINGAGENTS_SERVICE_REPORTS_DIR:-/home/app/reports/api}"
CACHE_DIR="${TRADINGAGENTS_SERVICE_CACHE_DIR:-/home/app/cache}"
MEMORY_DIR="${TRADINGAGENTS_SERVICE_MEMORY_DIR:-/home/app/memory}"
FALLBACK_REPORTS_DIR="/home/app/reports/api"

ensure_dir() {
  local dir="$1"
  mkdir -p "$dir" 2>/dev/null || true
  if [ "$(id -u)" = "0" ]; then
    chown -R app:app "$dir" 2>/dev/null || true
  fi
}

dir_writable_by_app() {
  local dir="$1"
  if [ "$(id -u)" = "0" ]; then
    runuser -u app -- test -w "$dir" 2>/dev/null
  else
    test -w "$dir"
  fi
}

prepare_reports_dir() {
  local parent
  parent="$(dirname "$REPORTS_DIR")"
  ensure_dir "$parent"
  ensure_dir "$REPORTS_DIR"
  ensure_dir "${REPORTS_DIR}/_jobs"
  ensure_dir "${REPORTS_DIR}/_logs"

  if dir_writable_by_app "$REPORTS_DIR"; then
    echo "Reports dir ready: ${REPORTS_DIR}"
    return 0
  fi

  echo "WARNING: ${REPORTS_DIR} is not writable by user app."
  echo "         Falling back to ${FALLBACK_REPORTS_DIR} (set a volume mount owned by the app user, or mount at /home/app/reports)."
  export TRADINGAGENTS_SERVICE_REPORTS_DIR="${FALLBACK_REPORTS_DIR}"
  REPORTS_DIR="${FALLBACK_REPORTS_DIR}"
  ensure_dir "$REPORTS_DIR"
  ensure_dir "${REPORTS_DIR}/_jobs"
  ensure_dir "${REPORTS_DIR}/_logs"
  if ! dir_writable_by_app "$REPORTS_DIR"; then
    echo "ERROR: Fallback reports dir ${REPORTS_DIR} is also not writable."
    return 1
  fi
  echo "Reports dir ready (fallback): ${REPORTS_DIR}"
}

ensure_dir "$CACHE_DIR"
ensure_dir "$MEMORY_DIR"
prepare_reports_dir

if [ "$(id -u)" = "0" ]; then
  exec runuser -u app -- "$@"
fi

exec "$@"
