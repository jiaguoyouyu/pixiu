#!/usr/bin/env bash
set -euo pipefail

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS - $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL - $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Verifying Pixiu Local Dev Loop Bridge..."

if python3 -m py_compile scripts/pixiu_dev_bridge.py; then
  pass "bridge script compiles"
else
  fail "bridge script compile failed"
fi

if bash -n scripts/run_pixiu_dev_bridge.sh && bash -n scripts/verify_pixiu_dev_bridge.sh; then
  pass "runner/verifier shell syntax passes"
else
  fail "runner/verifier shell syntax failed"
fi

if [ -f templates/pixiu_command_packet.template.json ]; then
  pass "command packet template exists"
else
  fail "command packet template missing"
fi

if python3 scripts/pixiu_dev_bridge.py status; then
  pass "bridge status works"
else
  fail "bridge status failed"
fi

if python3 scripts/pixiu_dev_bridge.py classify --packet templates/pixiu_command_packet.template.json | grep -q "effective_level: 1"; then
  pass "bridge classifies Level 1 packet"
else
  fail "bridge failed to classify Level 1 packet"
fi

mkdir -p /tmp/pixiu_dev_bridge_verify
cat > /tmp/pixiu_dev_bridge_verify/level3_packet.json <<EOF
{
  "label": "danger sample commit",
  "level": 3,
  "purpose": "Verifier should refuse this without yes.",
  "command": "git commit -m verifier-should-not-run",
  "requires_yes": true,
  "expected_outputs": [],
  "safety_notes": ["must refuse without yes"]
}
EOF

set +e
python3 scripts/pixiu_dev_bridge.py execute --packet /tmp/pixiu_dev_bridge_verify/level3_packet.json >/tmp/pixiu_level3_refusal.txt 2>&1
LEVEL3_CODE=$?
set -e

if [ "$LEVEL3_CODE" -eq 2 ] && grep -q "REFUSED" /tmp/pixiu_level3_refusal.txt; then
  pass "bridge refuses Level 3 packet without yes"
else
  fail "bridge did not refuse Level 3 packet"
  cat /tmp/pixiu_level3_refusal.txt
fi

if python3 scripts/pixiu_dev_bridge.py execute --packet templates/pixiu_command_packet.template.json; then
  pass "bridge executes Level 1 sample packet"
else
  fail "bridge failed to execute Level 1 sample packet"
fi

if ls outputs/dev_loop_bridge/*.txt >/dev/null 2>&1; then
  pass "bridge writes local execution log"
else
  fail "bridge execution log missing"
fi

if git status --short outputs/dev_loop_bridge 2>/dev/null | grep -q .; then
  fail "bridge generated logs are unignored"
else
  pass "bridge generated logs are ignored or clean"
fi

if grep -R -E "api[_-]?key|password|credential value" scripts/pixiu_dev_bridge.py scripts/run_pixiu_dev_bridge.sh docs/v2_2F_local_dev_loop_bridge_spec.md docs/v2_2F_local_dev_loop_bridge_plan.md templates/pixiu_command_packet.template.json >/tmp/pixiu_v22f_secret_scan.txt 2>/dev/null; then
  fail "possible credential leakage marker found"
  cat /tmp/pixiu_v22f_secret_scan.txt
else
  pass "no likely credential leakage markers found"
fi

if grep -R -E "PlaceOrder|CancelOrder|alpaca|ibkr|robinhood|koyfin.*login|selenium|playwright" scripts/pixiu_dev_bridge.py docs/v2_2F_local_dev_loop_bridge_spec.md >/tmp/pixiu_v22f_forbidden_scan.txt 2>/dev/null; then
  fail "forbidden automation marker found"
  cat /tmp/pixiu_v22f_forbidden_scan.txt
else
  pass "no forbidden automation markers found"
fi

echo
echo "Summary: $PASS_COUNT PASS, $FAIL_COUNT FAIL"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
