#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
SUMMARY_FILE="$(mktemp -t research_warehouse_verify.XXXXXX)"
UPDATE_LOG="$(mktemp -t research_warehouse_update_verify.XXXXXX)"
PYCACHE_DIR="$(mktemp -d /private/tmp/research_warehouse_pycache.XXXXXX)"

PASS_COUNT=0
FAIL_COUNT=0

cd "${PROJECT_ROOT}" || exit 1

record_pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "PASS - $1" >> "${SUMMARY_FILE}"
}

record_fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  echo "FAIL - $1" >> "${SUMMARY_FILE}"
}

check_command() {
  label="$1"
  shift
  if "$@" >> "${SUMMARY_FILE}" 2>&1; then
    record_pass "${label}"
  else
    record_fail "${label}"
  fi
}

check_file_exists() {
  label="$1"
  path="$2"
  if [[ -f "${path}" ]]; then
    record_pass "${label}"
  else
    record_fail "${label}"
  fi
}

scan_pattern() {
  pattern="$1"
  shift

  if command -v rg >/dev/null 2>&1; then
    echo "Scanner: rg" >> "${SUMMARY_FILE}"
    rg -n "${pattern}" "$@" >> "${SUMMARY_FILE}" 2>&1
    return $?
  fi

  if command -v grep >/dev/null 2>&1; then
    echo "Scanner: grep -R fallback" >> "${SUMMARY_FILE}"
    grep -R -n -E "${pattern}" "$@" >> "${SUMMARY_FILE}" 2>&1
    return $?
  fi

  echo "No scanner available: neither rg nor grep was found." >> "${SUMMARY_FILE}"
  return 2
}

check_no_leaks() {
  scan_pattern 'FMP_API_KEY=|FINNHUB_API_KEY=|FISCAL_AI_API_KEY=|QUARTR_API_KEY=|apikey=|token=|Authorization:' scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/run_research_warehouse_update.sh docs/research_warehouse.md outputs/daily_wall_street_desk_brief.md outputs/fiscal_ai_research_questions.md outputs/research_desk_tasks.csv outputs/koyfin_watchlists.csv
  scan_status=$?
  if [[ "${scan_status}" -eq 0 ]]; then
    record_fail "Likely API key leakage marker found"
  elif [[ "${scan_status}" -eq 1 ]]; then
    record_pass "No likely API key leakage markers found"
  else
    record_fail "Could not scan for likely API key leakage markers"
  fi
}

check_no_forbidden_automation() {
  scan_pattern 'place_order|submit_order|brokerage_login|brokerage.*password|selenium|playwright|puppeteer|koyfin.com/login|captcha.*bypass|fiscal.ai/api|quartr.*api|FISCAL_AI_API_KEY|QUARTR_API_KEY' scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/run_research_warehouse_update.sh docs/research_warehouse.md
  scan_status=$?
  if [[ "${scan_status}" -eq 0 ]]; then
    record_fail "Forbidden brokerage, Koyfin automation, or Fiscal.ai/Quartr API marker found"
  elif [[ "${scan_status}" -eq 1 ]]; then
    record_pass "No forbidden brokerage, Koyfin automation, or Fiscal.ai/Quartr API markers found"
  else
    record_fail "Could not scan for forbidden brokerage, Koyfin automation, or Fiscal.ai/Quartr API markers"
  fi
}

check_tables() {
  python3 - >> "${SUMMARY_FILE}" 2>&1 <<'PY'
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("DuckDB Python package is required.")
    print("pip install duckdb")
    raise SystemExit(2)

db_path = Path("data/pixiu.duckdb")
legacy_path = Path("data/investment_ranker.duckdb")
if not db_path.exists() and legacy_path.exists():
    db_path = legacy_path
required = {
    "warehouse_runs",
    "daily_investment_scores",
    "daily_ranker_scores",
    "index_weekly_earnings_calendar",
    "research_desk_tasks",
    "koyfin_watchlists",
    "warehouse_load_errors",
}
conn = duckdb.connect(str(db_path), read_only=True)
try:
    found = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
finally:
    conn.close()
missing = sorted(required - found)
if missing:
    print("Missing tables: " + ", ".join(missing))
    raise SystemExit(1)
print("Required tables present: " + ", ".join(sorted(required)))
PY
  if [[ $? -eq 0 ]]; then
    record_pass "Required warehouse tables exist"
  else
    record_fail "Required warehouse tables exist"
  fi
}

{
  echo "Research Warehouse Verification"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
} > "${SUMMARY_FILE}"

check_command "Warehouse Python scripts compile" env PYTHONPYCACHEPREFIX="${PYCACHE_DIR}" python3 -m py_compile scripts/load_research_warehouse.py scripts/query_research_warehouse.py
check_command "Warehouse update runner shell syntax" bash -n scripts/run_research_warehouse_update.sh
check_command "Warehouse verifier shell syntax" bash -n scripts/verify_research_warehouse.sh

if ./scripts/run_research_warehouse_update.sh > "${UPDATE_LOG}" 2>&1; then
  record_pass "Warehouse update runner executes"
else
  record_fail "Warehouse update runner executes"
  {
    echo "Update runner output:"
    tail -n 120 "${UPDATE_LOG}"
  } >> "${SUMMARY_FILE}"
fi

check_file_exists "Warehouse DuckDB file exists" "${PROJECT_ROOT}/data/pixiu.duckdb"
check_tables
check_command "table-counts query works" python3 scripts/query_research_warehouse.py table-counts
check_command "latest-run query works" python3 scripts/query_research_warehouse.py latest-run
check_command "summary query works" python3 scripts/query_research_warehouse.py summary
check_no_leaks
check_no_forbidden_automation

{
  echo
  echo "Warehouse update excerpt:"
  tail -n 100 "${UPDATE_LOG}"
  echo
  echo "Summary: ${PASS_COUNT} PASS, ${FAIL_COUNT} FAIL"
} >> "${SUMMARY_FILE}"

cat "${SUMMARY_FILE}"

if command -v pbcopy >/dev/null 2>&1; then
  if pbcopy < "${SUMMARY_FILE}" >/dev/null 2>&1; then
    echo
    echo "Verification summary copied to macOS clipboard."
  else
    echo
    echo "pbcopy is available but clipboard copy failed; summary printed above."
  fi
else
  echo
  echo "pbcopy is unavailable; summary printed above."
fi

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  exit 1
fi
exit 0
