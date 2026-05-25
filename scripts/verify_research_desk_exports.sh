#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

KOYFIN_CSV="${PROJECT_ROOT}/outputs/koyfin_watchlists.csv"
KOYFIN_MD="${PROJECT_ROOT}/outputs/koyfin_watchlists.md"
FISCAL_MD="${PROJECT_ROOT}/outputs/fiscal_ai_research_questions.md"
DESK_BRIEF_MD="${PROJECT_ROOT}/outputs/daily_wall_street_desk_brief.md"
TASKS_CSV="${PROJECT_ROOT}/outputs/research_desk_tasks.csv"

SUMMARY_FILE="$(mktemp -t research_desk_verify_summary.XXXXXX)"
RUN_LOG="$(mktemp -t research_desk_run.XXXXXX)"
INDEX_VERIFY_LOG="$(mktemp -t research_desk_index_verify.XXXXXX)"
PYCACHE_DIR="$(mktemp -d /private/tmp/research_desk_pycache.XXXXXX)"

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

check_contains() {
  label="$1"
  path="$2"
  pattern="$3"
  if [[ -f "${path}" ]] && grep -Fq "${pattern}" "${path}"; then
    record_pass "${label}"
  else
    record_fail "${label}"
  fi
}

check_csv_columns() {
  label="$1"
  path="$2"
  columns_csv="$3"
  python3 - "${path}" "${columns_csv}" >> "${SUMMARY_FILE}" 2>&1 <<'PY'
import csv
import sys

path = sys.argv[1]
required = {column.strip() for column in sys.argv[2].split(",") if column.strip()}
with open(path, newline="", encoding="utf-8") as handle:
    header = next(csv.reader(handle), [])
missing = sorted(required - set(header))
if missing:
    print("Missing columns: " + ", ".join(missing))
    raise SystemExit(1)
print("Required columns present: " + ", ".join(sorted(required)))
PY
  if [[ $? -eq 0 ]]; then
    record_pass "${label}"
  else
    record_fail "${label}"
  fi
}

check_no_secret_leakage() {
  if grep -Eq 'FMP_API_KEY=|FINNHUB_API_KEY=|FISCAL_AI_API_KEY=|apikey=|token=|Authorization:' "${KOYFIN_CSV}" "${KOYFIN_MD}" "${FISCAL_MD}" "${DESK_BRIEF_MD}" "${TASKS_CSV}" 2>/dev/null; then
    record_fail "Generated research desk outputs contain likely API key leakage marker"
  else
    record_pass "No likely API key leakage markers in research desk outputs"
  fi
}

{
  echo "Research Desk Exports Verification"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
} > "${SUMMARY_FILE}"

check_command "Research desk generator compiles" env PYTHONPYCACHEPREFIX="${PYCACHE_DIR}" python3 -m py_compile scripts/generate_research_desk_exports.py
check_command "Research desk runner shell syntax" bash -n scripts/run_research_desk_exports.sh
check_command "Research desk verifier shell syntax" bash -n scripts/verify_research_desk_exports.sh

if ./scripts/run_research_desk_exports.sh > "${RUN_LOG}" 2>&1; then
  record_pass "Research desk runner executes"
else
  record_fail "Research desk runner executes"
  {
    echo "Runner output:"
    tail -n 80 "${RUN_LOG}"
  } >> "${SUMMARY_FILE}"
fi

check_file_exists "Koyfin watchlist CSV exists" "${KOYFIN_CSV}"
check_file_exists "Koyfin watchlist Markdown exists" "${KOYFIN_MD}"
check_file_exists "Fiscal.ai research questions Markdown exists" "${FISCAL_MD}"
check_file_exists "Daily Wall Street Desk Brief exists" "${DESK_BRIEF_MD}"
check_file_exists "Research desk tasks CSV exists" "${TASKS_CSV}"

check_contains "Koyfin Markdown heading present" "${KOYFIN_MD}" "# Koyfin Watchlists"
check_contains "Fiscal.ai Markdown heading present" "${FISCAL_MD}" "# Fiscal.ai Research Questions"
check_contains "Desk brief Markdown heading present" "${DESK_BRIEF_MD}" "# Daily Wall Street Desk Brief"
check_contains "Desk brief notices present" "${DESK_BRIEF_MD}" "Not financial advice"
check_contains "Fiscal.ai disabled/stubbed note present" "${FISCAL_MD}" "Fiscal.ai API integration is disabled and stubbed."
check_contains "Koyfin no-scrape note present" "${KOYFIN_MD}" "Do not scrape Koyfin."

check_csv_columns "Koyfin CSV required columns" "${KOYFIN_CSV}" "watchlist_name,ticker,company_name,sector,theme,strategy,final_score,importance_score,earnings_date,days_until_earnings,cad_alternative,cad_note,notes"
check_csv_columns "Research desk tasks CSV required columns" "${TASKS_CSV}" "priority,task_type,ticker,company_name,due_date,source,action,status,notes"

check_no_secret_leakage

if ./scripts/verify_index_earnings_pipeline.sh > "${INDEX_VERIFY_LOG}" 2>&1; then
  record_pass "Existing v1.6.1 index earnings verifier still passes"
else
  record_fail "Existing v1.6.1 index earnings verifier still passes"
  {
    echo "Index verifier output:"
    tail -n 100 "${INDEX_VERIFY_LOG}"
  } >> "${SUMMARY_FILE}"
fi

{
  echo
  echo "Runner output excerpt:"
  tail -n 60 "${RUN_LOG}"
  echo
  echo "Index verifier output excerpt:"
  tail -n 40 "${INDEX_VERIFY_LOG}"
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
