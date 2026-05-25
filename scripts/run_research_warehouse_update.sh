#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
SUMMARY_FILE="$(mktemp -t research_warehouse_update.XXXXXX)"
LOAD_LOG="$(mktemp -t research_warehouse_load.XXXXXX)"
DESK_LOG="$(mktemp -t research_warehouse_desk.XXXXXX)"
LOAD_ARGS=()

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --run-type)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for --run-type" >&2
        exit 2
      fi
      case "$2" in
        production|verification|manual_test)
          LOAD_ARGS+=("--run-type" "$2")
          shift 2
          ;;
        *)
          echo "Invalid --run-type: $2" >&2
          exit 2
          ;;
      esac
      ;;
    --trading-date)
      if [[ "$#" -lt 2 ]]; then
        echo "Missing value for --trading-date" >&2
        exit 2
      fi
      LOAD_ARGS+=("--trading-date" "$2")
      shift 2
      ;;
    --replace-production)
      LOAD_ARGS+=("--replace-production")
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--run-type production|verification|manual_test] [--trading-date YYYY-MM-DD] [--replace-production]" >&2
      exit 2
      ;;
  esac
done

if [[ "${#LOAD_ARGS[@]}" -eq 0 ]]; then
  LOAD_ARGS=("--run-type" "verification")
fi

cd "${PROJECT_ROOT}" || exit 1

DESK_EXIT_CODE=0
if [[ -x "./scripts/run_research_desk_exports.sh" ]]; then
  ./scripts/run_research_desk_exports.sh > "${DESK_LOG}" 2>&1
  DESK_EXIT_CODE=$?
else
  echo "Research desk export runner not found; loading existing outputs only." > "${DESK_LOG}"
fi

python3 scripts/load_research_warehouse.py "${LOAD_ARGS[@]}" > "${LOAD_LOG}" 2>&1
LOAD_EXIT_CODE=$?

FINAL_EXIT_CODE=${LOAD_EXIT_CODE}
if [[ ! -f "${PROJECT_ROOT}/data/pixiu.duckdb" && -f "${PROJECT_ROOT}/data/investment_ranker.duckdb" ]]; then
  cp "${PROJECT_ROOT}/data/investment_ranker.duckdb" "${PROJECT_ROOT}/data/pixiu.duckdb"
fi
if [[ ! -f "${PROJECT_ROOT}/data/pixiu.duckdb" ]]; then
  FINAL_EXIT_CODE=1
fi

{
  echo "Pixiu Research Warehouse Update"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo "Research desk export exit code: ${DESK_EXIT_CODE}"
  echo "Warehouse load exit code: ${LOAD_EXIT_CODE}"
  echo "Script exit code: ${FINAL_EXIT_CODE}"
  echo
  echo "Security boundary: research-only; no brokerage connection; no orders; no API key storage; no credential storage."
  echo "Not financial advice"
  echo "Model output requires human review"
  echo "Data quality may affect results"
  echo
  echo "Warehouse database:"
  if [[ -f "${PROJECT_ROOT}/data/pixiu.duckdb" ]]; then
    echo "- ${PROJECT_ROOT}/data/pixiu.duckdb"
  else
    echo "- MISSING: ${PROJECT_ROOT}/data/pixiu.duckdb"
  fi
  echo
  echo "Warehouse load output:"
  cat "${LOAD_LOG}"
  echo
} > "${SUMMARY_FILE}"

if [[ "${LOAD_EXIT_CODE}" -eq 0 ]]; then
  {
    echo "Latest warehouse summary:"
    python3 scripts/query_research_warehouse.py summary
  } >> "${SUMMARY_FILE}" 2>&1
else
  {
    echo "Latest warehouse summary unavailable because warehouse load failed."
    echo
    echo "Research desk export output excerpt:"
    tail -n 60 "${DESK_LOG}"
  } >> "${SUMMARY_FILE}"
fi

cat "${SUMMARY_FILE}"

if command -v pbcopy >/dev/null 2>&1; then
  if pbcopy < "${SUMMARY_FILE}" >/dev/null 2>&1; then
    echo
    echo "Summary copied to macOS clipboard."
  else
    echo
    echo "pbcopy is available but clipboard copy failed; summary printed above."
  fi
else
  echo
  echo "pbcopy is unavailable; summary printed above."
fi

exit "${FINAL_EXIT_CODE}"
