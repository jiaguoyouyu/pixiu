#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

SUMMARY_FILE="$(mktemp -t daily_ranker_warehouse_verify.XXXXXX)"
DEFAULT_LOG="$(mktemp -t daily_ranker_warehouse_default.XXXXXX)"
EXPANDED_LOG="$(mktemp -t daily_ranker_warehouse_expanded.XXXXXX)"
WAREHOUSE_LOG="$(mktemp -t daily_ranker_warehouse_update.XXXXXX)"
PYCACHE_DIR="$(mktemp -d /private/tmp/daily_ranker_warehouse_pycache.XXXXXX)"

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

check_warehouse_contract() {
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
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }
    if "daily_ranker_scores" not in tables:
        print("daily_ranker_scores table missing")
        raise SystemExit(1)

    columns = {
        row[0]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'daily_ranker_scores'"
        ).fetchall()
    }
    required = {
        "run_id",
        "run_timestamp",
        "source_file",
        "ranker_mode",
        "ticker",
        "quality_score",
        "valuation_score",
        "momentum_score",
        "earnings_risk_score",
        "data_quality_score",
        "market_regime_score",
        "action_score",
        "action_bias",
        "confidence",
        "primary_reason",
        "risk_flags",
        "invalidation_check",
        "backtest_status",
        "options_analysis_status",
        "options_bias",
        "loaded_at",
    }
    missing = sorted(required - columns)
    if missing:
        print("Missing columns: " + ", ".join(missing))
        raise SystemExit(1)

    latest = conn.execute(
        "SELECT run_id FROM daily_ranker_scores ORDER BY loaded_at DESC LIMIT 1"
    ).fetchone()
    if not latest:
        print("No daily_ranker_scores rows found")
        raise SystemExit(1)
    run_id = latest[0]

    default_count = conn.execute(
        "SELECT COUNT(*) FROM daily_ranker_scores WHERE run_id = ? AND ranker_mode = 'default_watchlist'",
        [run_id],
    ).fetchone()[0]
    expanded_count = conn.execute(
        "SELECT COUNT(*) FROM daily_ranker_scores WHERE run_id = ? AND ranker_mode = 'expanded_universe'",
        [run_id],
    ).fetchone()[0]
    non_empty_action_bias = conn.execute(
        """
        SELECT COUNT(*)
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND ranker_mode = 'expanded_universe'
          AND COALESCE(NULLIF(action_bias, ''), '') <> ''
        """,
        [run_id],
    ).fetchone()[0]
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

    if default_count < 38:
        print(f"Latest default rows too low: {default_count}")
        raise SystemExit(1)
    if expanded_count < 100:
        print(f"Latest expanded rows too low: {expanded_count}")
        raise SystemExit(1)
    if non_empty_action_bias != expanded_count:
        print(f"Expanded action_bias populated rows {non_empty_action_bias} != expanded rows {expanded_count}")
        raise SystemExit(1)
    if unsupported_options:
        print(f"Expanded rows with unsupported options status: {unsupported_options}")
        raise SystemExit(1)

    print(f"Latest run_id: {run_id}")
    print(f"Default rows loaded: {default_count}")
    print(f"Expanded rows loaded: {expanded_count}")
    print("Expanded action_bias populated for all expanded rows.")
    print("Expanded options analysis remains unavailable.")
finally:
    conn.close()
PY
  if [[ $? -eq 0 ]]; then
    record_pass "Daily ranker warehouse table contract is valid"
  else
    record_fail "Daily ranker warehouse table contract is valid"
  fi
}

check_no_leaks() {
  if grep -R -n -E 'FMP_API_KEY=|FINNHUB_API_KEY=|FISCAL_AI_API_KEY=|QUARTR_API_KEY=|apikey=|token=|Authorization:' \
    scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/run_research_warehouse_update.sh \
    outputs/expanded_daily_investment_scores.csv \
    outputs/expanded_daily_investment_report.md outputs/action_bias_explanation.md >> "${SUMMARY_FILE}" 2>&1; then
    record_fail "Likely API key leakage marker found"
  else
    record_pass "No likely API key leakage markers found"
  fi
}

check_no_forbidden_automation() {
  if grep -R -n -E 'place_order|submit_order|brokerage_login|brokerage.*password|selenium|playwright|puppeteer|koyfin.com/login|captcha.*bypass|fiscal.ai/api|quartr.*api|options_edge|calculate_greeks|infer_skew' \
    scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/run_research_warehouse_update.sh \
    outputs/expanded_daily_investment_report.md \
    outputs/action_bias_explanation.md >> "${SUMMARY_FILE}" 2>&1; then
    record_fail "Forbidden automation or unsupported options inference marker found"
  else
    record_pass "No forbidden automation or unsupported options inference markers found"
  fi
}

{
  echo "Daily Ranker Warehouse Verification"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo
} > "${SUMMARY_FILE}"

check_command "Changed Python scripts compile" env PYTHONPYCACHEPREFIX="${PYCACHE_DIR}" python3 -m py_compile scripts/load_research_warehouse.py scripts/query_research_warehouse.py scripts/pixiu.py scripts/investment_ranker.py
check_command "Warehouse runner shell syntax" bash -n scripts/run_research_warehouse_update.sh
check_command "Warehouse verifier shell syntax" bash -n scripts/verify_research_warehouse.sh
check_command "Expanded daily ranker verifier shell syntax" bash -n scripts/verify_daily_ranker_expanded.sh
check_command "Daily ranker warehouse verifier shell syntax" bash -n scripts/verify_daily_ranker_warehouse.sh

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

if ./scripts/run_research_warehouse_update.sh > "${WAREHOUSE_LOG}" 2>&1; then
  record_pass "Research warehouse update executes"
else
  record_fail "Research warehouse update executes"
  tail -n 120 "${WAREHOUSE_LOG}" >> "${SUMMARY_FILE}"
fi

check_file_exists "DuckDB warehouse exists" "${PROJECT_ROOT}/data/pixiu.duckdb"
check_warehouse_contract
check_command "daily-ranker-expanded-latest query works" python3 scripts/query_research_warehouse.py daily-ranker-expanded-latest
check_command "action-bias-summary query works" python3 scripts/query_research_warehouse.py action-bias-summary
check_command "ticker-daily-ranker-history query works" python3 scripts/query_research_warehouse.py ticker-daily-ranker-history NVDA
check_no_leaks
check_no_forbidden_automation

{
  echo
  echo "Warehouse update excerpt:"
  tail -n 100 "${WAREHOUSE_LOG}"
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
