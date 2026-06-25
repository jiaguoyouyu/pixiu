#!/usr/bin/env bash
set -euo pipefail

echo "Verifying Pixiu Daily Brief Quality Audit..."

PASS_COUNT=0
FAIL_COUNT=0

pass() { echo "PASS - $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo "FAIL - $1"; FAIL_COUNT=$((FAIL_COUNT + 1)); }

check() {
  local label="$1"
  shift
  if "$@"; then
    pass "$label"
  else
    fail "$label"
  fi
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REPORT="outputs/daily_brief_quality_report.md"
PYCACHE_DIR="$(mktemp -d /private/tmp/pixiu_quality_pycache.XXXXXX)"

check "quality generator compiles" env PYTHONPYCACHEPREFIX="$PYCACHE_DIR" python3 -m py_compile scripts/generate_daily_brief_quality_report.py
check "daily brief generator still compiles" env PYTHONPYCACHEPREFIX="$PYCACHE_DIR" python3 -m py_compile scripts/generate_daily_brief_report.py
check "quality verifier shell syntax passes" bash -n scripts/verify_pixiu_daily_brief_quality.sh
check "daily brief runner shell syntax passes" bash -n scripts/run_pixiu_daily_brief.sh
check "quality docs exist" test -f docs/daily_brief_quality_report.md
check "quality spec exists" test -f docs/v2_2F_4_brief_quality_audit_spec.md
check "quality plan exists" test -f docs/v2_2F_4_brief_quality_audit_plan.md

if python3 -m unittest tests/test_daily_brief_quality_report.py; then
  pass "quality unit tests pass"
else
  fail "quality unit tests pass"
fi

if python3 scripts/generate_daily_brief_quality_report.py; then
  pass "quality generator runs"
else
  fail "quality generator runs"
fi

check "quality report exists" test -f "$REPORT"

if grep -Eq "Final verdict: \\*\\*(USE|REVIEW CAREFULLY|DO NOT USE)\\*\\*" "$REPORT"; then
  pass "quality report has exact allowed verdict"
else
  fail "quality report has exact allowed verdict"
fi

if grep -q "Freshness of required daily artifacts" "$REPORT" &&
  grep -q "Expected row-count sanity" "$REPORT" &&
  grep -q "Repository cleanliness evidence" "$REPORT" &&
  grep -q "Duplicate-production and run-status detection" "$REPORT" &&
  grep -q "Top-candidate consistency" "$REPORT" &&
  grep -q "Data-gap ratio" "$REPORT" &&
  grep -q "Missing signal-outcome coverage" "$REPORT" &&
  grep -q "Human-review usefulness" "$REPORT"; then
  pass "quality report includes all required dimensions"
else
  fail "quality report includes all required dimensions"
fi

python3 scripts/generate_daily_brief_quality_report.py >/tmp/pixiu_quality_hash_1.txt
HASH1="$(shasum -a 256 "$REPORT" | awk '{print $1}')"
python3 scripts/generate_daily_brief_quality_report.py >/tmp/pixiu_quality_hash_2.txt
HASH2="$(shasum -a 256 "$REPORT" | awk '{print $1}')"
if [[ "$HASH1" == "$HASH2" ]]; then
  pass "quality report rerun is deterministic"
else
  fail "quality report rerun is deterministic"
fi

if git status --short outputs/daily_brief_quality_report.md | grep -q .; then
  fail "quality generated output is ignored or clean"
else
  pass "quality generated output is ignored or clean"
fi

if git ls-files | grep -E "(^outputs/|^backups/|^snapshots/|\\.duckdb|\\.env|\\.tar\\.gz|\\.log$)" >/dev/null; then
  fail "no generated/sensitive files are tracked"
else
  pass "no generated/sensitive files are tracked"
fi

if grep -RInE "place_order|cancel_order|submit_order|brokerage connection|automated trading|credential storage|Koyfin login|Fiscal.ai login|Quartr login|urlopen|urllib.request|requests\\." \
  scripts/generate_daily_brief_quality_report.py scripts/run_pixiu_daily_brief.sh >/dev/null; then
  fail "no forbidden automation or provider markers in quality implementation"
else
  pass "no forbidden automation or provider markers in quality implementation"
fi

echo
echo "Summary: ${PASS_COUNT} PASS, ${FAIL_COUNT} FAIL"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
