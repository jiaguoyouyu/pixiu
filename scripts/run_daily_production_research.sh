#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
TRADING_DATE="$(date '+%Y-%m-%d')"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --trading-date)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for --trading-date" >&2
        exit 2
      fi
      TRADING_DATE="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--trading-date YYYY-MM-DD]" >&2
      exit 2
      ;;
  esac
done

LOG_DIR="${PROJECT_ROOT}/outputs/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/pixiu-production-${TRADING_DATE}.log"
SUMMARY_FILE="$(mktemp -t daily_production_research.XXXXXX)"

cd "${PROJECT_ROOT}" || exit 1
: > "${LOG_FILE}"

production_main() {
{
  echo "Pixiu Daily Production Research Run"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Trading date: ${TRADING_DATE}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
  echo "Security boundary: research-only; no brokerage connection; no orders; no automated trading; no credential storage."
  echo "Not financial advice"
  echo "Model output requires human review"
  echo "Data quality may affect results"
  echo
} > "${SUMMARY_FILE}"

DEFAULT_EXIT=0
EXPANDED_EXIT=0
WAREHOUSE_EXIT=0
DRIFT_EXIT=0

{
  echo "Running default daily ranker..."
  ./scripts/run_daily_report.sh
  DEFAULT_EXIT=$?
  echo "Default daily ranker exit code: ${DEFAULT_EXIT}"
  echo

  echo "Running expanded-universe daily ranker..."
  ./scripts/run_daily_report.sh --expanded-universe
  EXPANDED_EXIT=$?
  echo "Expanded daily ranker exit code: ${EXPANDED_EXIT}"
  echo

  REPLACE_ARGS=()
  EXISTING_PRODUCTION_ROWS="$(python3 - "${TRADING_DATE}" <<'PY'
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("0")
    raise SystemExit(0)

db_path = Path("data/pixiu.duckdb")
legacy_path = Path("data/investment_ranker.duckdb")
if not db_path.exists() and legacy_path.exists():
    db_path = legacy_path
if not db_path.exists():
    print("0")
    raise SystemExit(0)

conn = duckdb.connect(str(db_path), read_only=True)
try:
    count = conn.execute(
        """
        SELECT COUNT(*)
        FROM daily_ranker_scores
        WHERE run_type = 'production'
          AND trading_date = ?
        """,
        [sys.argv[1]],
    ).fetchone()[0]
    print(count)
finally:
    conn.close()
PY
)"
  if [[ "${EXISTING_PRODUCTION_ROWS}" != "0" ]]; then
    echo "Existing production rows found for ${TRADING_DATE}: ${EXISTING_PRODUCTION_ROWS}"
    echo "Replacing same-day production rows using explicit --replace-production to avoid duplicate production history."
    REPLACE_ARGS=("--replace-production")
  fi

  echo "Loading production warehouse rows..."
  if [[ "${#REPLACE_ARGS[@]}" -gt 0 ]]; then
    ./scripts/run_research_warehouse_update.sh --run-type production --trading-date "${TRADING_DATE}" "${REPLACE_ARGS[@]}"
  else
    ./scripts/run_research_warehouse_update.sh --run-type production --trading-date "${TRADING_DATE}"
  fi
  WAREHOUSE_EXIT=$?
  echo "Production warehouse update exit code: ${WAREHOUSE_EXIT}"
  echo

  echo "Generating action-bias drift report..."
  python3 scripts/query_research_warehouse.py action-bias-drift
  DRIFT_EXIT=$?
  echo "Action-bias drift query exit code: ${DRIFT_EXIT}"
  echo

  echo "Production latest:"
  python3 scripts/query_research_warehouse.py production-latest
  echo
  echo "Production action-bias summary:"
  python3 scripts/query_research_warehouse.py production-action-bias-summary
  echo
  echo "Duplicate production check:"
  python3 scripts/query_research_warehouse.py duplicate-production-check
}

FINAL_EXIT=0
if [[ "${DEFAULT_EXIT}" -ne 0 || "${EXPANDED_EXIT}" -ne 0 || "${WAREHOUSE_EXIT}" -ne 0 || "${DRIFT_EXIT}" -ne 0 ]]; then
  FINAL_EXIT=1
fi

{
  echo "Exit codes:"
  echo "- Default daily ranker: ${DEFAULT_EXIT}"
  echo "- Expanded daily ranker: ${EXPANDED_EXIT}"
  echo "- Production warehouse update: ${WAREHOUSE_EXIT}"
  echo "- Action-bias drift report: ${DRIFT_EXIT}"
  echo "- Final script exit: ${FINAL_EXIT}"
  echo
  echo "Output files:"
  echo "- ${PROJECT_ROOT}/outputs/daily_investment_scores.csv"
  echo "- ${PROJECT_ROOT}/outputs/expanded_daily_investment_scores.csv"
  echo "- ${PROJECT_ROOT}/outputs/action_bias_drift_report.md"
  echo "- ${LOG_FILE}"
} >> "${SUMMARY_FILE}"

cat "${SUMMARY_FILE}"

if command -v pbcopy >/dev/null 2>&1; then
  if pbcopy < "${SUMMARY_FILE}" >/dev/null 2>&1; then
    echo
    echo "Production summary copied to macOS clipboard."
  else
    echo
    echo "pbcopy is available but clipboard copy failed; summary printed above."
  fi
else
  echo
  echo "pbcopy is unavailable; summary printed above."
fi

return "${FINAL_EXIT}"
}

production_main 2>&1 | tee -a "${LOG_FILE}"
exit "${PIPESTATUS[0]}"
