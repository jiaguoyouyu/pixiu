#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

CALENDAR_FILE="${PROJECT_ROOT}/outputs/index_weekly_earnings_calendar.csv"
REPORT_FILE="${PROJECT_ROOT}/outputs/index_weekly_earnings_report.md"
SUMMARY_FILE="$(mktemp -t index_earnings_verify_summary.XXXXXX)"
NO_KEY_LOG="$(mktemp -t index_earnings_no_key.XXXXXX)"
NO_KEY_PROVIDER_EXCERPT="$(mktemp -t index_earnings_no_key_provider.XXXXXX)"
PYCACHE_DIR="$(mktemp -d /private/tmp/index_earnings_pycache.XXXXXX)"
PRESERVE_DIR="$(mktemp -d /private/tmp/index_earnings_outputs.XXXXXX)"
ORIGINAL_CALENDAR="${PRESERVE_DIR}/index_weekly_earnings_calendar.csv"
ORIGINAL_REPORT="${PRESERVE_DIR}/index_weekly_earnings_report.md"
HAD_ORIGINAL_CALENDAR=0
HAD_ORIGINAL_REPORT=0
RESTORE_STATUS="no prior outputs existed; kept verification outputs"
RESTORE_DONE=0

PASS_COUNT=0
FAIL_COUNT=0

cd "${PROJECT_ROOT}" || exit 1

if [[ -f "${CALENDAR_FILE}" ]]; then
  cp "${CALENDAR_FILE}" "${ORIGINAL_CALENDAR}"
  HAD_ORIGINAL_CALENDAR=1
fi
if [[ -f "${REPORT_FILE}" ]]; then
  cp "${REPORT_FILE}" "${ORIGINAL_REPORT}"
  HAD_ORIGINAL_REPORT=1
fi

restore_outputs() {
  if [[ "${RESTORE_DONE}" -eq 1 ]]; then
    return
  fi

  if [[ "${HAD_ORIGINAL_CALENDAR}" -eq 1 ]]; then
    cp "${ORIGINAL_CALENDAR}" "${CALENDAR_FILE}"
  fi
  if [[ "${HAD_ORIGINAL_REPORT}" -eq 1 ]]; then
    cp "${ORIGINAL_REPORT}" "${REPORT_FILE}"
  fi

  if [[ "${HAD_ORIGINAL_CALENDAR}" -eq 1 || "${HAD_ORIGINAL_REPORT}" -eq 1 ]]; then
    RESTORE_STATUS="restored original outputs"
  fi
  RESTORE_DONE=1
}

trap restore_outputs EXIT

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

check_report_contains() {
  pattern="$1"
  if grep -Fq "${pattern}" "${REPORT_FILE}"; then
    record_pass "Report contains ${pattern}"
  else
    record_fail "Report missing ${pattern}"
  fi
}

check_no_secret_leakage() {
  if grep -Eq 'FMP_API_KEY=|FINNHUB_API_KEY=|apikey=|token=' "${REPORT_FILE}" "${CALENDAR_FILE}" 2>/dev/null; then
    record_fail "Report/CSV contain likely API key leakage marker"
  else
    record_pass "No likely API key leakage markers in report/CSV"
  fi
}

check_csv_header() {
  python3 - "${CALENDAR_FILE}" >> "${SUMMARY_FILE}" 2>&1 <<'PY'
import csv
import sys

required = {
    "eps_estimate",
    "revenue_estimate",
    "provider",
    "earnings_date_source",
    "provider_status",
}
with open(sys.argv[1], newline="", encoding="utf-8") as handle:
    reader = csv.reader(handle)
    header = next(reader, [])
missing = sorted(required - set(header))
if missing:
    print("Missing CSV columns: " + ", ".join(missing))
    raise SystemExit(1)
print("CSV provider columns present")
PY
  if [[ $? -eq 0 ]]; then
    record_pass "CSV header contains provider columns"
  else
    record_fail "CSV header missing provider columns"
  fi
}

check_output_restoration() {
  restore_outputs
  echo "Output preservation: ${RESTORE_STATUS}" >> "${SUMMARY_FILE}"
  if [[ "${HAD_ORIGINAL_REPORT}" -eq 1 ]]; then
    if cmp -s "${ORIGINAL_REPORT}" "${REPORT_FILE}"; then
      record_pass "Restored original index weekly report"
    else
      record_fail "Restored index weekly report differs from original"
    fi
  fi
  if [[ "${HAD_ORIGINAL_CALENDAR}" -eq 1 ]]; then
    if cmp -s "${ORIGINAL_CALENDAR}" "${CALENDAR_FILE}"; then
      record_pass "Restored original index weekly CSV"
    else
      record_fail "Restored index weekly CSV differs from original"
    fi
  fi
}

{
  echo "Index Earnings Pipeline Verification"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
} > "${SUMMARY_FILE}"

check_command "Compile provider and index scripts" env PYTHONPYCACHEPREFIX="${PYCACHE_DIR}" python3 -m py_compile scripts/earnings_providers.py scripts/index_universe_earnings_radar.py

if env -u FMP_API_KEY -u FINNHUB_API_KEY ./scripts/run_index_earnings_report.sh > "${NO_KEY_LOG}" 2>&1; then
  record_pass "No-key index earnings run"
else
  record_fail "No-key index earnings run"
  {
    echo "No-key run output:"
    tail -n 40 "${NO_KEY_LOG}"
  } >> "${SUMMARY_FILE}"
fi

check_file_exists "Index weekly earnings CSV exists" "${CALENDAR_FILE}"
check_file_exists "Index weekly earnings report exists" "${REPORT_FILE}"

if [[ -f "${REPORT_FILE}" ]]; then
  check_report_contains "## Provider Status"
  check_report_contains "## Daily Earnings Brief"
  check_report_contains "## Top 20 Market-Moving Earnings"
fi

if [[ -f "${CALENDAR_FILE}" ]]; then
  check_csv_header
fi

if [[ -f "${REPORT_FILE}" && -f "${CALENDAR_FILE}" ]]; then
  check_no_secret_leakage
fi

if [[ -f "${REPORT_FILE}" ]]; then
  awk '
    /^## Provider Status/ { in_section=1; print; next }
    /^## / && in_section { exit }
    in_section { print }
  ' "${REPORT_FILE}" > "${NO_KEY_PROVIDER_EXCERPT}"
else
  echo "Report missing." > "${NO_KEY_PROVIDER_EXCERPT}"
fi

check_output_restoration

{
  echo
  echo "No-key provider status excerpt:"
  cat "${NO_KEY_PROVIDER_EXCERPT}"
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
