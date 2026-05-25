#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

DEFAULT_SCORES="${PROJECT_ROOT}/outputs/daily_investment_scores.csv"
DEFAULT_REPORT="${PROJECT_ROOT}/outputs/daily_investment_report.md"
EXPANDED_SCORES="${PROJECT_ROOT}/outputs/expanded_daily_investment_scores.csv"
EXPANDED_REPORT="${PROJECT_ROOT}/outputs/expanded_daily_investment_report.md"
ACTION_EXPLANATION="${PROJECT_ROOT}/outputs/action_bias_explanation.md"

SUMMARY_FILE="$(mktemp -t daily_ranker_expanded_verify.XXXXXX)"
DEFAULT_LOG="$(mktemp -t daily_ranker_default.XXXXXX)"
EXPANDED_LOG="$(mktemp -t daily_ranker_expanded.XXXXXX)"
PYCACHE_DIR="$(mktemp -d /private/tmp/daily_ranker_pycache.XXXXXX)"

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

check_expanded_rows_and_labels() {
  python3 - "${EXPANDED_SCORES}" >> "${SUMMARY_FILE}" 2>&1 <<'PY'
import csv
import sys

allowed = {
    "Buy/Add Watch",
    "Pullback Buy Watch",
    "Hold / Monitor",
    "Avoid Chase",
    "Reduce Risk Watch",
    "Sell Review",
    "Data Gap Review",
    "Earnings Event Risk",
}
path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
if len(rows) <= 38:
    print(f"Expanded output has {len(rows)} rows; expected more than 38.")
    raise SystemExit(1)
bad_labels = sorted({row.get("action_bias", "") for row in rows} - allowed)
if bad_labels:
    print("Unexpected action_bias labels: " + ", ".join(bad_labels))
    raise SystemExit(1)
bad_options = [
    row.get("ticker", "")
    for row in rows
    if row.get("options_analysis_status") != "unavailable"
    or row.get("options_bias") != "No Options Analysis"
]
if bad_options:
    print("Rows with unsupported options status: " + ", ".join(bad_options[:20]))
    raise SystemExit(1)
print(f"Expanded rows: {len(rows)}")
print("All action_bias labels are allowed.")
print("Options analysis is unavailable for all expanded rows.")
PY
  if [[ $? -eq 0 ]]; then
    record_pass "Expanded output rows, action_bias labels, and options status are valid"
  else
    record_fail "Expanded output rows, action_bias labels, and options status are valid"
  fi
}

check_default_compatibility() {
  python3 - "${DEFAULT_SCORES}" >> "${SUMMARY_FILE}" 2>&1 <<'PY'
import csv
import sys

path = sys.argv[1]
with open(path, newline="", encoding="utf-8") as handle:
    reader = csv.reader(handle)
    header = next(reader, [])
    rows = list(reader)
required = {"ticker", "final_score", "risk_penalty", "strategy", "confidence", "cad_alternative", "cad_note"}
missing = sorted(required - set(header))
if missing:
    print("Missing default columns: " + ", ".join(missing))
    raise SystemExit(1)
if "action_bias" in header:
    print("Default output unexpectedly includes expanded action_bias column.")
    raise SystemExit(1)
if len(rows) < 38:
    print(f"Default output has {len(rows)} rows; expected at least 38.")
    raise SystemExit(1)
print(f"Default rows: {len(rows)}")
print("Default daily output remains compatible.")
PY
  if [[ $? -eq 0 ]]; then
    record_pass "Default daily output remains compatible"
  else
    record_fail "Default daily output remains compatible"
  fi
}

check_no_leaks() {
  if grep -R -n -E 'FMP_API_KEY=|FINNHUB_API_KEY=|FISCAL_AI_API_KEY=|QUARTR_API_KEY=|apikey=|token=|Authorization:' \
    scripts/pixiu.py scripts/investment_ranker.py scripts/run_daily_report.sh \
    outputs/daily_investment_scores.csv outputs/daily_investment_report.md \
    outputs/expanded_daily_investment_scores.csv outputs/expanded_daily_investment_report.md \
    outputs/action_bias_explanation.md >> "${SUMMARY_FILE}" 2>&1; then
    record_fail "Likely API key leakage marker found"
  else
    record_pass "No likely API key leakage markers found"
  fi
}

check_no_forbidden_automation() {
  if grep -R -n -E 'place_order|submit_order|brokerage_login|brokerage.*password|selenium|playwright|puppeteer|koyfin.com/login|captcha.*bypass|fiscal.ai/api|quartr.*api' \
    scripts/pixiu.py scripts/investment_ranker.py scripts/run_daily_report.sh \
    outputs/expanded_daily_investment_report.md outputs/action_bias_explanation.md >> "${SUMMARY_FILE}" 2>&1; then
    record_fail "Forbidden brokerage, Koyfin, Fiscal.ai, or Quartr automation marker found"
  else
    record_pass "No forbidden brokerage, Koyfin, Fiscal.ai, or Quartr automation markers found"
  fi
}

{
  echo "Expanded Daily Ranker Verification"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
} > "${SUMMARY_FILE}"

check_command "Daily ranker Python compiles" env PYTHONPYCACHEPREFIX="${PYCACHE_DIR}" python3 -m py_compile scripts/pixiu.py scripts/investment_ranker.py
check_command "Daily runner shell syntax" bash -n scripts/run_daily_report.sh
check_command "Expanded verifier shell syntax" bash -n scripts/verify_daily_ranker_expanded.sh

if ./scripts/run_daily_report.sh > "${DEFAULT_LOG}" 2>&1; then
  record_pass "Default daily runner executes"
else
  record_fail "Default daily runner executes"
  {
    echo "Default runner output:"
    tail -n 100 "${DEFAULT_LOG}"
  } >> "${SUMMARY_FILE}"
fi

if ./scripts/run_daily_report.sh --expanded-universe > "${EXPANDED_LOG}" 2>&1; then
  record_pass "Expanded daily runner executes"
else
  record_fail "Expanded daily runner executes"
  {
    echo "Expanded runner output:"
    tail -n 100 "${EXPANDED_LOG}"
  } >> "${SUMMARY_FILE}"
fi

check_file_exists "Default scores CSV exists" "${DEFAULT_SCORES}"
check_file_exists "Default Markdown report exists" "${DEFAULT_REPORT}"
check_file_exists "Expanded scores CSV exists" "${EXPANDED_SCORES}"
check_file_exists "Expanded Markdown report exists" "${EXPANDED_REPORT}"
check_file_exists "Action bias explanation exists" "${ACTION_EXPLANATION}"

check_csv_columns "Expanded action-bias columns exist" "${EXPANDED_SCORES}" "quality_score,valuation_score,momentum_score,earnings_risk_score,data_quality_score,market_regime_score,action_score,action_bias,confidence,primary_reason,risk_flags,invalidation_check,backtest_status,options_analysis_status,options_bias"
check_contains "Expanded report includes research-only disclaimer" "${EXPANDED_REPORT}" "Research-only output"
check_contains "Expanded report includes deterministic prefilter section" "${EXPANDED_REPORT}" "## Deterministic Prefilter"
check_contains "Action bias explanation includes options unavailable note" "${ACTION_EXPLANATION}" "options_analysis_status=unavailable"

check_default_compatibility
check_expanded_rows_and_labels
check_no_leaks
check_no_forbidden_automation

{
  echo
  echo "Default runner excerpt:"
  tail -n 60 "${DEFAULT_LOG}"
  echo
  echo "Expanded runner excerpt:"
  tail -n 80 "${EXPANDED_LOG}"
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
