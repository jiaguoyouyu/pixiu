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

REPORT_DIR="outputs/partnership_catalyst_reports"
REPORT_PATH="$REPORT_DIR/2026-05-26-sample-partnership-catalyst-report.md"

echo "Verifying Pixiu Partnership Catalyst Report Generator..."

if python3 -m py_compile scripts/generate_partnership_catalyst_report.py; then
  pass "generator compiles"
else
  fail "generator compile failed"
fi

if bash -n scripts/verify_partnership_catalyst_report.sh; then
  pass "verifier shell syntax passes"
else
  fail "verifier shell syntax failed"
fi

mkdir -p "$REPORT_DIR"
rm -f "$REPORT_PATH"

if python3 scripts/generate_partnership_catalyst_report.py --input templates/major_partnership_catalyst_input_template.md; then
  pass "generator runs on template input"
else
  fail "generator failed on template input"
fi

if [ -f "$REPORT_PATH" ]; then
  pass "report output exists"
else
  fail "report output missing"
fi

for section in \
  "Executive Summary" \
  "Ticker and Thesis Date" \
  "Observed Evidence" \
  "Catalyst Hypothesis" \
  "Evidence Table" \
  "Probability Band" \
  "Scenario Table" \
  "Contradictions and Invalidation Triggers" \
  "Source Hygiene" \
  "Monitoring Checklist" \
  "Research-only Disclaimer"
do
  if grep -q "## $section" "$REPORT_PATH"; then
    pass "report includes section: $section"
  else
    fail "report missing section: $section"
  fi
done

if grep -q "This is probabilistic research based on public/user-provided information and is not investment advice." "$REPORT_PATH"; then
  pass "report includes required disclaimer"
else
  fail "report missing required disclaimer"
fi

if git status --short "$REPORT_DIR" | grep -q .; then
  fail "generated report directory has tracked/staged/unignored changes"
else
  pass "generated reports are ignored or clean"
fi

if grep -R -E "api[_-]?key|secret|token|password" scripts/generate_partnership_catalyst_report.py templates/major_partnership_catalyst_input_template.md templates/major_partnership_catalyst_report_template.md docs/v2_2D_partnership_catalyst_report_generator_spec.md docs/v2_2D_partnership_catalyst_report_generator_plan.md >/tmp/pixiu_secret_scan.txt 2>/dev/null; then
  fail "possible secret markers found"
  cat /tmp/pixiu_secret_scan.txt
else
  pass "no likely API key leakage markers found"
fi

if grep -R -E "PlaceOrder|CancelOrder|alpaca|ibkr|robinhood|koyfin.*login|selenium|playwright" scripts/generate_partnership_catalyst_report.py templates docs/v2_2D_partnership_catalyst_report_generator_spec.md >/tmp/pixiu_forbidden_scan.txt 2>/dev/null; then
  fail "forbidden automation marker found"
  cat /tmp/pixiu_forbidden_scan.txt
else
  pass "no forbidden automation markers found"
fi

if grep -R -E "gamma|delta|skew|greeks" scripts/generate_partnership_catalyst_report.py templates docs/v2_2D_partnership_catalyst_report_generator_spec.md >/tmp/pixiu_options_scan.txt 2>/dev/null; then
  fail "unsupported options inference marker found"
  cat /tmp/pixiu_options_scan.txt
else
  pass "no unsupported options inference markers found"
fi

echo
echo "Summary: $PASS_COUNT PASS, $FAIL_COUNT FAIL"

if [ "$FAIL_COUNT" -ne 0 ]; then
  exit 1
fi
