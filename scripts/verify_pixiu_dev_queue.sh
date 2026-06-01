#!/usr/bin/env bash
set -euo pipefail

echo "Verifying Pixiu Dev Bridge Command Queue / Clipboard Bundle..."

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

check "queue script compiles" python3 -m py_compile scripts/pixiu_dev_queue.py
check "queue runner shell syntax passes" bash -n scripts/run_pixiu_dev_queue.sh
check "queue verifier shell syntax passes" bash -n scripts/verify_pixiu_dev_queue.sh
check "queue template exists" test -f templates/pixiu_command_queue.template.json
check "queue docs exist" test -f docs/dev_bridge_command_queue.md
check "queue spec exists" test -f docs/v2_2F_1_dev_bridge_command_queue_spec.md
check "queue plan exists" test -f docs/v2_2F_1_dev_bridge_command_queue_plan.md

if python3 scripts/pixiu_dev_queue.py status | grep -q "PIXIU DEV QUEUE STATUS"; then
  pass "queue status works"
else
  fail "queue status works"
fi

CLASSIFY_OUTPUT="$(python3 scripts/pixiu_dev_queue.py classify --queue templates/pixiu_command_queue.template.json)"
echo "$CLASSIFY_OUTPUT"
if echo "$CLASSIFY_OUTPUT" | grep -q "max_level: 1"; then
  pass "queue classifies safe Level 1 template"
else
  fail "queue classifies safe Level 1 template"
fi

EXEC_OUTPUT="$(python3 scripts/pixiu_dev_queue.py execute --queue templates/pixiu_command_queue.template.json --no-copy)"
echo "$EXEC_OUTPUT"
if echo "$EXEC_OUTPUT" | grep -q "ai_bundle:" && echo "$EXEC_OUTPUT" | grep -q "overall_exit_code: 0"; then
  pass "queue executes Level 1 template and creates AI bundle"
else
  fail "queue executes Level 1 template and creates AI bundle"
fi

if python3 scripts/pixiu_dev_queue.py bundle --limit 1 --no-copy | grep -q "ai_bundle:"; then
  pass "latest log bundle command works"
else
  fail "latest log bundle command works"
fi

TMP_QUEUE="outputs/dev_loop_queue/tmp-level3-refusal-queue.json"
mkdir -p "$(dirname "$TMP_QUEUE")"
cat > "$TMP_QUEUE" <<'JSON'
{
  "queue_label": "temporary Level 3 refusal queue",
  "commands": [
    { "label": "forbidden push sample", "level": 3, "command": "git push origin main" }
  ]
}
JSON

set +e
LEVEL3_OUTPUT="$(python3 scripts/pixiu_dev_queue.py execute --queue "$TMP_QUEUE" --no-copy 2>&1)"
LEVEL3_CODE=$?
set -e
echo "$LEVEL3_OUTPUT"
rm -f "$TMP_QUEUE"

if [ "$LEVEL3_CODE" -ne 0 ] && echo "$LEVEL3_OUTPUT" | grep -q "REFUSED"; then
  pass "queue refuses Level 3 without explicit approval"
else
  fail "queue refuses Level 3 without explicit approval"
fi

if git status --short outputs/dev_loop_queue | grep -q .; then
  fail "queue generated logs are ignored or clean"
else
  pass "queue generated logs are ignored or clean"
fi

if git ls-files | grep -E "(^outputs/|^backups/|^snapshots/|\.duckdb|\.env|\.tar\.gz|\.log$)" >/dev/null; then
  fail "no generated/sensitive files are tracked"
else
  pass "no generated/sensitive files are tracked"
fi

if grep -RInE "place_order|cancel_order|brokerage connection|automated trading|credential storage|Koyfin login|Fiscal.ai login|Quartr login" scripts/pixiu_dev_queue.py templates/pixiu_command_queue.template.json >/dev/null; then
  fail "no forbidden automation markers in queue implementation"
else
  pass "no forbidden automation markers in queue implementation"
fi

echo
echo "Summary: ${PASS_COUNT} PASS, ${FAIL_COUNT} FAIL"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
