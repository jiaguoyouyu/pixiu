#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

SUMMARY_FILE="$(mktemp -t daily_production_research_verify.XXXXXX)"
DEFAULT_LOG="$(mktemp -t daily_production_default.XXXXXX)"
EXPANDED_LOG="$(mktemp -t daily_production_expanded.XXXXXX)"
PRODUCTION_LOG="$(mktemp -t daily_production_runner.XXXXXX)"
PYCACHE_DIR="$(mktemp -d /private/tmp/daily_production_pycache.XXXXXX)"

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

check_production_schema_and_rows() {
  python3 - >> "${SUMMARY_FILE}" 2>&1 <<'PY'
from pathlib import Path

try:
    import duckdb
except ImportError:
    print("DuckDB Python package is required.")
    print("pip install duckdb")
    raise SystemExit(2)

db_path = Path("data/pixiu.duckdb")
legacy_path = Path("data/investment_ranker.duckdb")
if not db_path.exists() and legacy_path.exists():
    db_path = legacy_path
conn = duckdb.connect(str(db_path), read_only=True)
try:
    columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'daily_ranker_scores'"
        ).fetchall()
    }
    required = {"trading_date", "run_type", "ranker_mode", "source_file", "loaded_at", "action_bias"}
    missing = sorted(required - columns)
    if missing:
        print("Missing daily_ranker_scores columns: " + ", ".join(missing))
        raise SystemExit(1)

    run_columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'warehouse_runs'"
        ).fetchall()
    }
    run_required = {"trading_date", "run_type"}
    run_missing = sorted(run_required - run_columns)
    if run_missing:
        print("Missing warehouse_runs columns: " + ", ".join(run_missing))
        raise SystemExit(1)

    latest = conn.execute(
        """
        SELECT run_id, trading_date
        FROM warehouse_runs
        WHERE run_type = 'production'
        ORDER BY loaded_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not latest:
        print("No production warehouse run found")
        raise SystemExit(1)
    run_id, trading_date = latest

    counts = dict(
        conn.execute(
            """
            SELECT ranker_mode, COUNT(*)
            FROM daily_ranker_scores
            WHERE run_id = ? AND run_type = 'production'
            GROUP BY ranker_mode
            """,
            [run_id],
        ).fetchall()
    )
    if counts.get("default_watchlist", 0) < 38:
        print(f"Production default rows too low: {counts.get('default_watchlist', 0)}")
        raise SystemExit(1)
    if counts.get("expanded_universe", 0) < 100:
        print(f"Production expanded rows too low: {counts.get('expanded_universe', 0)}")
        raise SystemExit(1)

    verification_rows = conn.execute(
        "SELECT COUNT(*) FROM daily_ranker_scores WHERE run_type = 'verification'"
    ).fetchone()[0]
    if verification_rows <= 0:
        print("No verification rows found; verification/test rows are not distinguishable")
        raise SystemExit(1)

    unsupported_options = conn.execute(
        """
        SELECT COUNT(*)
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND ranker_mode = 'expanded_universe'
          AND (
              options_analysis_status <> 'unavailable'
              OR options_bias <> 'No Options Analysis'
          )
        """,
        [run_id],
    ).fetchone()[0]
    if unsupported_options:
        print(f"Unsupported expanded options rows: {unsupported_options}")
        raise SystemExit(1)

    print(f"Production run_id: {run_id}")
    print(f"Production trading_date: {trading_date}")
    print(f"Production counts: {counts}")
    print(f"Verification rows found: {verification_rows}")
finally:
    conn.close()
PY
  if [[ $? -eq 0 ]]; then
    record_pass "Production schema and row marking are valid"
  else
    record_fail "Production schema and row marking are valid"
  fi
}

check_no_leaks() {
  if grep -R -n -E 'FMP_API_KEY=|FINNHUB_API_KEY=|FISCAL_AI_API_KEY=|QUARTR_API_KEY=|apikey=|token=|Authorization:' \
    scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/run_research_warehouse_update.sh \
    scripts/run_daily_production_research.sh outputs/action_bias_drift_report.md >> "${SUMMARY_FILE}" 2>&1; then
    record_fail "Likely API key leakage marker found"
  else
    record_pass "No likely API key leakage markers found"
  fi
}

check_no_forbidden_automation() {
  if grep -R -n -E 'place_order|submit_order|brokerage_login|brokerage.*password|selenium|playwright|puppeteer|koyfin.com/login|captcha.*bypass|fiscal.ai/api|quartr.*api|options_edge|calculate_greeks|infer_skew' \
    scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/run_research_warehouse_update.sh \
    scripts/run_daily_production_research.sh outputs/action_bias_drift_report.md >> "${SUMMARY_FILE}" 2>&1; then
    record_fail "Forbidden automation or unsupported options inference marker found"
  else
    record_pass "No forbidden automation or unsupported options inference markers found"
  fi
}

check_low_confidence_cleanup() {
  local query_log
  query_log="$(mktemp -t low_confidence_latest.XXXXXX)"
  if ! python3 scripts/query_research_warehouse.py low-confidence-latest > "${query_log}" 2>&1; then
    cat "${query_log}" >> "${SUMMARY_FILE}"
    record_fail "low-confidence-latest cleanup query runs"
    return
  fi
  if grep -E 'Buy/Add Watch|Pullback Buy Watch' "${query_log}" | grep -Fq 'Medium-High'; then
    cat "${query_log}" >> "${SUMMARY_FILE}"
    record_fail "low-confidence-latest excludes constructive Medium-High rows"
  else
    record_pass "low-confidence-latest excludes constructive Medium-High rows"
  fi

  if awk '
    /^## Low Confidence \/ Data Gap Watch/ {inside=1; next}
    /^## / && inside {inside=0}
    inside {print}
  ' outputs/action_bias_drift_report.md | grep -E 'Buy/Add Watch|Pullback Buy Watch' | grep -Fq 'Medium-High'; then
    record_fail "Drift report low-confidence section excludes constructive Medium-High rows"
  else
    record_pass "Drift report low-confidence section excludes constructive Medium-High rows"
  fi
}

{
  echo "Daily Production Research Verification"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
} > "${SUMMARY_FILE}"

check_command "Changed Python scripts compile" env PYTHONPYCACHEPREFIX="${PYCACHE_DIR}" python3 -m py_compile scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/pixiu.py scripts/investment_ranker.py
check_command "Daily runner shell syntax" bash -n scripts/run_daily_report.sh
check_command "Warehouse update runner shell syntax" bash -n scripts/run_research_warehouse_update.sh
check_command "Production runner shell syntax" bash -n scripts/run_daily_production_research.sh
check_command "Production verifier shell syntax" bash -n scripts/verify_daily_production_research.sh

if ./scripts/run_daily_report.sh > "${DEFAULT_LOG}" 2>&1; then
  record_pass "Default daily runner executes"
else
  record_fail "Default daily runner executes"
  tail -n 100 "${DEFAULT_LOG}" >> "${SUMMARY_FILE}"
fi

if ./scripts/run_daily_report.sh --expanded-universe > "${EXPANDED_LOG}" 2>&1; then
  record_pass "Expanded daily runner executes"
else
  record_fail "Expanded daily runner executes"
  tail -n 100 "${EXPANDED_LOG}" >> "${SUMMARY_FILE}"
fi

if ./scripts/run_daily_production_research.sh > "${PRODUCTION_LOG}" 2>&1; then
  record_pass "Production daily research runner executes"
else
  record_fail "Production daily research runner executes"
  tail -n 160 "${PRODUCTION_LOG}" >> "${SUMMARY_FILE}"
fi

check_file_exists "Action bias drift report exists" "${PROJECT_ROOT}/outputs/action_bias_drift_report.md"
check_contains "Drift report has summary heading" "${PROJECT_ROOT}/outputs/action_bias_drift_report.md" "## Action Bias Counts"
check_contains "Drift report has duplicate guard note" "${PROJECT_ROOT}/outputs/action_bias_drift_report.md" "## Duplicate Production Guard"
check_contains "Drift report has research-only disclaimer" "${PROJECT_ROOT}/outputs/action_bias_drift_report.md" "Research-only"
check_production_schema_and_rows
check_command "production-latest query works" python3 scripts/query_research_warehouse.py production-latest
check_command "production-action-bias-summary query works" python3 scripts/query_research_warehouse.py production-action-bias-summary
check_command "action-bias-drift query works" python3 scripts/query_research_warehouse.py action-bias-drift
check_command "production-ticker-history query works" python3 scripts/query_research_warehouse.py production-ticker-history NVDA
check_command "low-confidence-latest query works" python3 scripts/query_research_warehouse.py low-confidence-latest
check_command "duplicate-production-check query works" python3 scripts/query_research_warehouse.py duplicate-production-check
check_low_confidence_cleanup
check_no_leaks
check_no_forbidden_automation

{
  echo
  echo "Production runner excerpt:"
  tail -n 140 "${PRODUCTION_LOG}"
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
