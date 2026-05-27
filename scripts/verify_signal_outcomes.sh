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

echo "Verifying Pixiu Signal Outcome Tracking..."

if python3 -m py_compile scripts/track_signal_outcomes.py; then
  pass "outcome tracker compiles"
else
  fail "outcome tracker compile failed"
fi

if bash -n scripts/verify_signal_outcomes.sh; then
  pass "verifier shell syntax passes"
else
  fail "verifier shell syntax failed"
fi

if [ -f data/manual_price_history.template.csv ]; then
  pass "manual price history template exists"
else
  fail "manual price history template missing"
fi

rm -f outputs/signal_outcomes.csv outputs/signal_outcomes_report.md

if python3 scripts/track_signal_outcomes.py; then
  pass "missing manual_price_history.csv handled gracefully"
else
  fail "missing manual_price_history.csv handling failed"
fi

if python3 scripts/track_signal_outcomes.py --allow-template; then
  pass "tracker runs with template price history"
else
  fail "tracker failed with template price history"
fi

if [ -f outputs/signal_outcomes.csv ]; then
  pass "signal outcomes CSV generated"
else
  fail "signal outcomes CSV missing"
fi

if [ -f outputs/signal_outcomes_report.md ]; then
  pass "signal outcomes report generated"
else
  fail "signal outcomes report missing"
fi

if grep -q "forward_return_5d" outputs/signal_outcomes.csv && grep -q "excess_return_vs_SPY_5d" outputs/signal_outcomes.csv; then
  pass "outcome CSV includes forward and excess return columns"
else
  fail "outcome CSV missing forward/excess return columns"
fi

if grep -q "Research-only. Not financial advice" outputs/signal_outcomes_report.md; then
  pass "report includes research-only disclaimer"
else
  fail "report missing research-only disclaimer"
fi

if git status --short outputs/signal_outcomes.csv outputs/signal_outcomes_report.md | grep -q .; then
  fail "generated signal outcome outputs are unignored"
else
  pass "generated signal outcome outputs are ignored or clean"
fi

if grep -R -E "api[_-]?key|password|credential value" scripts/track_signal_outcomes.py docs/v2_2E_signal_outcome_tracking_spec.md docs/v2_2E_signal_outcome_tracking_plan.md data/manual_price_history.template.csv >/tmp/pixiu_v22e_secret_scan.txt 2>/dev/null; then
  fail "possible credential leakage marker found"
  cat /tmp/pixiu_v22e_secret_scan.txt
else
  pass "no likely credential leakage markers found"
fi

if grep -R -E "PlaceOrder|CancelOrder|alpaca|ibkr|robinhood|koyfin.*login|selenium|playwright" scripts/track_signal_outcomes.py docs/v2_2E_signal_outcome_tracking_spec.md >/tmp/pixiu_v22e_forbidden_scan.txt 2>/dev/null; then
  fail "forbidden automation marker found"
  cat /tmp/pixiu_v22e_forbidden_scan.txt
else
  pass "no forbidden automation markers found"
fi

if grep -R -E "(^|[^A-Za-z])(gamma|skew|greeks)([^A-Za-z]|$)" scripts/track_signal_outcomes.py docs/v2_2E_signal_outcome_tracking_spec.md >/tmp/pixiu_v22e_options_scan.txt 2>/dev/null; then
  fail "unsupported options inference marker found"
  cat /tmp/pixiu_v22e_options_scan.txt
else
  pass "no unsupported options inference markers found"
fi

echo
echo "Summary: $PASS_COUNT PASS, $FAIL_COUNT FAIL"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
