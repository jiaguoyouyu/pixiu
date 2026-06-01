#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

QUEUE="templates/pixiu_daily_research_queue.template.json"
MODE="${1:-execute}"

case "$MODE" in
  classify)
    python3 scripts/pixiu_dev_queue.py classify --queue "$QUEUE"
    ;;
  execute)
    python3 scripts/pixiu_dev_queue.py execute --queue "$QUEUE"
    ;;
  bundle)
    python3 scripts/pixiu_dev_queue.py bundle --limit 5
    ;;
  status)
    python3 scripts/pixiu_dev_queue.py status
    ;;
  verify)
    ./scripts/verify_pixiu_daily_queue.sh
    ;;
  *)
    echo "Usage: $0 [execute|classify|bundle|status|verify]"
    exit 2
    ;;
esac
