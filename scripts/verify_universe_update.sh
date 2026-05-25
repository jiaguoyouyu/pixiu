#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
SUMMARY_FILE="$(mktemp -t universe_verify_summary.XXXXXX)"
UPDATE_LOG="$(mktemp -t universe_verify_update.XXXXXX)"
PYCACHE_DIR="$(mktemp -d /private/tmp/universe_pycache.XXXXXX)"
PRESERVE_DIR="$(mktemp -d /private/tmp/universe_verify_preserve.XXXXXX)"
ORIGINAL_UNIVERSE="${PRESERVE_DIR}/index_universe.csv"
HAD_ORIGINAL_UNIVERSE=0
UPDATE_EXIT_CODE=0

PASS_COUNT=0
FAIL_COUNT=0

cd "${PROJECT_ROOT}" || exit 1

if [[ -f "data/index_universe.csv" ]]; then
  cp "data/index_universe.csv" "${ORIGINAL_UNIVERSE}"
  HAD_ORIGINAL_UNIVERSE=1
fi

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

check_csv_shape() {
  python3 - >> "${SUMMARY_FILE}" 2>&1 <<'PY'
import csv
from pathlib import Path

path = Path("data/index_universe.csv")
required = {
    "ticker",
    "company_name",
    "index_memberships",
    "sector",
    "industry",
    "theme",
    "source",
    "universe_tier",
    "active",
    "last_updated",
}
with path.open(newline="", encoding="utf-8") as handle:
    reader = csv.DictReader(handle)
    rows = list(reader)
header = set(reader.fieldnames or [])
missing = sorted(required - header)
if missing:
    print("Missing columns: " + ", ".join(missing))
    raise SystemExit(1)
tickers = {row.get("ticker", "").strip().upper() for row in rows if row.get("ticker")}
print(f"Unique ticker count: {len(tickers)}")
if len(tickers) < 100:
    print("Ticker count did not increase materially from the 35/38 baseline.")
    raise SystemExit(1)
memberships = " ".join(row.get("index_memberships", "") for row in rows)
for name in ["S&P 500", "Nasdaq-100", "Dow 30", "Local Watchlist"]:
    if name not in memberships:
        print(f"Missing membership coverage: {name}")
        raise SystemExit(1)
print("Required columns and membership coverage present.")
PY
  if [[ $? -eq 0 ]]; then
    record_pass "Expanded universe CSV shape is valid"
  else
    record_fail "Expanded universe CSV shape is valid"
  fi
}

check_no_leaks() {
  scan_pattern 'apikey=[A-Za-z0-9_./+%-]{8,}|token=[A-Za-z0-9_./+%-]{8,}|Authorization:[[:space:]]*(Bearer|Basic)[[:space:]]+[A-Za-z0-9_./+%-]{8,}|FMP_API_KEY=[A-Za-z0-9_./+%-]{8,}' scripts/update_index_universe.py scripts/run_universe_update.sh docs/universe_expansion.md outputs/universe_expansion_report.md outputs/universe_provider_capability_report.md data/index_universe.csv data/manual_index_constituents.csv
  status=$?
  if [[ "${status}" -eq 0 ]]; then
    record_fail "Likely API key leakage marker found"
  elif [[ "${status}" -eq 1 ]]; then
    record_pass "No likely API key leakage markers found"
  else
    record_fail "Could not scan for likely API key leakage markers"
  fi
}

check_no_forbidden_automation() {
  scan_pattern 'place_order|submit_order|brokerage_login|brokerage.*password|selenium|playwright|puppeteer|koyfin.com/login|captcha.*bypass|fiscal.ai/api|quartr.*api|FISCAL_AI_API_KEY|QUARTR_API_KEY' scripts/update_index_universe.py scripts/run_universe_update.sh docs/universe_expansion.md
  status=$?
  if [[ "${status}" -eq 0 ]]; then
    record_fail "Forbidden brokerage, Koyfin automation, or Fiscal.ai/Quartr API marker found"
  elif [[ "${status}" -eq 1 ]]; then
    record_pass "No forbidden brokerage, Koyfin automation, or Fiscal.ai/Quartr API markers found"
  else
    record_fail "Could not scan for forbidden automation markers"
  fi
}

check_provider_capability_report() {
  if [[ ! -f "outputs/universe_provider_capability_report.md" ]]; then
    record_fail "Provider capability report exists"
    return
  fi
  record_pass "Provider capability report exists"

  if grep -Eq 'Status: (BLOCKED_BY_PROVIDER_PERMISSION|MISSING_PROVIDER_KEY|PROVIDER_RETURNED_ZERO_ROWS|PROVIDER_UNAVAILABLE)' "outputs/universe_provider_capability_report.md"; then
    record_fail "Provider capability blocked"
  elif grep -Eq 'Status: (success|manual_import_success)' "outputs/universe_provider_capability_report.md"; then
    record_pass "Provider capability ok"
  else
    record_fail "Provider capability status is unclear"
  fi
}

check_no_destructive_overwrite_on_failure() {
  if [[ "${UPDATE_EXIT_CODE}" -eq 0 ]]; then
    record_pass "No destructive overwrite check not needed after successful update"
    return
  fi
  if [[ "${HAD_ORIGINAL_UNIVERSE}" -eq 1 ]] && cmp -s "${ORIGINAL_UNIVERSE}" "data/index_universe.csv"; then
    record_pass "No destructive overwrite when provider/manual update failed"
  else
    record_fail "No destructive overwrite when provider/manual update failed"
  fi
}

{
  echo "Index Universe Expansion Verification"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
} > "${SUMMARY_FILE}"

check_command "Universe updater compiles" env PYTHONPYCACHEPREFIX="${PYCACHE_DIR}" python3 -m py_compile scripts/update_index_universe.py
check_command "Universe update runner shell syntax" bash -n scripts/run_universe_update.sh
check_command "Universe verifier shell syntax" bash -n scripts/verify_universe_update.sh

if ./scripts/run_universe_update.sh --public-bootstrap > "${UPDATE_LOG}" 2>&1; then
  UPDATE_EXIT_CODE=0
  record_pass "Universe update runner executes"
else
  UPDATE_EXIT_CODE=$?
  if grep -Eq 'BLOCKED_BY_PROVIDER_PERMISSION|MISSING_PROVIDER_KEY|PROVIDER_RETURNED_ZERO_ROWS|PROVIDER_UNAVAILABLE' "${UPDATE_LOG}"; then
    record_fail "Universe update blocked by provider capability"
  else
    record_fail "Universe update runner executes"
  fi
  {
    echo "Universe update output:"
    tail -n 120 "${UPDATE_LOG}"
  } >> "${SUMMARY_FILE}"
fi

if [[ -f "data/index_universe.csv" ]]; then
  record_pass "Output CSV exists"
else
  record_fail "Output CSV exists"
fi

if [[ -f "data/manual_index_constituents.csv" ]]; then
  record_pass "Manual constituents CSV exists"
else
  record_fail "Manual constituents CSV exists"
fi

if ls data/index_universe_snapshot_*.csv >/dev/null 2>&1; then
  record_pass "Index universe snapshot exists"
else
  record_fail "Index universe snapshot exists"
fi

if [[ -f "outputs/universe_expansion_report.md" ]]; then
  record_pass "Universe expansion report exists"
  if grep -Fq "public_bootstrap" "outputs/universe_expansion_report.md"; then
    record_pass "Universe expansion report says public bootstrap"
  else
    record_fail "Universe expansion report says public bootstrap"
  fi
else
  record_fail "Universe expansion report exists"
fi
check_provider_capability_report
check_no_destructive_overwrite_on_failure

check_csv_shape
check_no_leaks
check_no_forbidden_automation
check_command "Existing v2.0 warehouse verifier still passes" ./scripts/verify_research_warehouse.sh

{
  echo
  echo "Universe update excerpt:"
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
