#!/usr/bin/env bash
set -euo pipefail

echo "Verifying Pixiu Daily Queue Presets..."

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

QUEUE="templates/pixiu_daily_research_queue.template.json"

check "daily queue template exists" test -f "$QUEUE"
check "daily queue runner shell syntax passes" bash -n scripts/run_pixiu_daily_queue.sh
check "daily queue verifier shell syntax passes" bash -n scripts/verify_pixiu_daily_queue.sh
check "daily queue docs exist" test -f docs/daily_queue_presets.md
check "daily queue spec exists" test -f docs/v2_2F_2_daily_queue_presets_spec.md
check "daily queue plan exists" test -f docs/v2_2F_2_daily_queue_presets_plan.md

if python3 -m json.tool "$QUEUE" >/dev/null; then
  pass "daily queue template is valid JSON"
else
  fail "daily queue template is valid JSON"
fi

CLASSIFY_OUTPUT="$(python3 scripts/pixiu_dev_queue.py classify --queue "$QUEUE")"
echo "$CLASSIFY_OUTPUT"

if echo "$CLASSIFY_OUTPUT" | grep -q "max_level: 2"; then
  pass "daily queue classifies as max Level 2"
else
  fail "daily queue classifies as max Level 2"
fi

if echo "$CLASSIFY_OUTPUT" | grep -q "requires_yes_level3: no"; then
  pass "daily queue does not require Level 3 approval"
else
  fail "daily queue does not require Level 3 approval"
fi

if ./scripts/run_pixiu_daily_queue.sh classify | grep -q "PIXIU DEV QUEUE CLASSIFICATION"; then
  pass "daily queue runner classify mode works"
else
  fail "daily queue runner classify mode works"
fi

echo "Running full daily queue preset. This may take a little while."
EXEC_OUTPUT="$(./scripts/run_pixiu_daily_queue.sh execute)"
echo "$EXEC_OUTPUT"

if echo "$EXEC_OUTPUT" | grep -q "overall_exit_code: 0"; then
  pass "daily queue preset executes successfully"
else
  fail "daily queue preset executes successfully"
fi

if echo "$EXEC_OUTPUT" | grep -q "Duplicate production check" && echo "$EXEC_OUTPUT" | grep -q "No duplicate production groups detected"; then
  pass "daily queue duplicate production check passes"
else
  fail "daily queue duplicate production check passes"
fi

if ./scripts/run_pixiu_daily_queue.sh bundle | grep -q "ai_bundle:"; then
  pass "daily queue bundle mode works"
else
  fail "daily queue bundle mode works"
fi

if git status --short outputs/dev_loop_queue | grep -q .; then
  fail "daily queue generated logs are ignored or clean"
else
  pass "daily queue generated logs are ignored or clean"
fi

if git ls-files | grep -E "(^outputs/|^backups/|^snapshots/|\.duckdb|\.env|\.tar\.gz|\.log$)" >/dev/null; then
  fail "no generated/sensitive files are tracked"
else
  pass "no generated/sensitive files are tracked"
fi

if grep -RInE "place_order|cancel_order|brokerage connection|automated trading|credential storage|Koyfin login|Fiscal.ai login|Quartr login" scripts/run_pixiu_daily_queue.sh templates/pixiu_daily_research_queue.template.json >/dev/null; then
  fail "no forbidden automation markers in daily queue preset implementation"
else
  pass "no forbidden automation markers in daily queue preset implementation"
fi

echo
echo "Summary: ${PASS_COUNT} PASS, ${FAIL_COUNT} FAIL"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
