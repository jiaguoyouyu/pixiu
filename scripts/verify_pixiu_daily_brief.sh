#!/usr/bin/env bash
set -euo pipefail

echo "Verifying Pixiu Daily Brief Report..."

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

REPORT="outputs/daily_brief_report.md"

check "daily brief generator compiles" python3 -m py_compile scripts/generate_daily_brief_report.py
check "daily brief runner shell syntax passes" bash -n scripts/run_pixiu_daily_brief.sh
check "daily brief verifier shell syntax passes" bash -n scripts/verify_pixiu_daily_brief.sh
check "daily brief docs exist" test -f docs/daily_brief_report.md
check "daily brief spec exists" test -f docs/v2_2F_3_daily_brief_report_spec.md
check "daily brief plan exists" test -f docs/v2_2F_3_daily_brief_report_plan.md

echo "Running daily brief workflow. This runs the daily queue first."
RUN_OUTPUT="$(./scripts/run_pixiu_daily_brief.sh run)"
echo "$RUN_OUTPUT"

if echo "$RUN_OUTPUT" | grep -q "Daily brief report:"; then
  pass "daily brief runner generates report"
else
  fail "daily brief runner generates report"
fi

check "daily brief report exists" test -f "$REPORT"

if grep -q "Not financial advice" "$REPORT"; then
  pass "daily brief includes financial-advice disclaimer"
else
  fail "daily brief includes financial-advice disclaimer"
fi

if grep -q "Default Watchlist Top Candidates" "$REPORT"; then
  pass "daily brief includes default watchlist section"
else
  fail "daily brief includes default watchlist section"
fi

if grep -q "Expanded-Universe Top Candidates" "$REPORT"; then
  pass "daily brief includes expanded universe section"
else
  fail "daily brief includes expanded universe section"
fi

if grep -q "Human Review Queue" "$REPORT"; then
  pass "daily brief includes human review section"
else
  fail "daily brief includes human review section"
fi

if git status --short outputs/dev_loop_queue outputs/daily_brief_report.md | grep -q .; then
  fail "daily brief generated outputs are ignored or clean"
else
  pass "daily brief generated outputs are ignored or clean"
fi

if git ls-files | grep -E "(^outputs/|^backups/|^snapshots/|\.duckdb|\.env|\.tar\.gz|\.log$)" >/dev/null; then
  fail "no generated/sensitive files are tracked"
else
  pass "no generated/sensitive files are tracked"
fi

if grep -RInE "place_order|cancel_order|brokerage connection|automated trading|credential storage|Koyfin login|Fiscal.ai login|Quartr login" scripts/generate_daily_brief_report.py scripts/run_pixiu_daily_brief.sh >/dev/null; then
  fail "no forbidden automation markers in daily brief implementation"
else
  pass "no forbidden automation markers in daily brief implementation"
fi

echo
echo "Summary: ${PASS_COUNT} PASS, ${FAIL_COUNT} FAIL"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
