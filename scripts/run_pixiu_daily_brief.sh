#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:-run}"

case "$MODE" in
  run)
    ./scripts/run_pixiu_daily_queue.sh execute
    python3 scripts/generate_daily_brief_report.py
    ;;
  brief-only)
    python3 scripts/generate_daily_brief_report.py
    ;;
  verify)
    ./scripts/verify_pixiu_daily_brief.sh
    ;;
  status)
    python3 scripts/pixiu_dev_queue.py status
    ;;
  *)
    echo "Usage: $0 [run|brief-only|verify|status]"
    exit 2
    ;;
esac
