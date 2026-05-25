#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
SUMMARY_FILE="$(mktemp -t universe_update_summary.XXXXXX)"
UPDATE_LOG="$(mktemp -t universe_update.XXXXXX)"

cd "${PROJECT_ROOT}" || exit 1

python3 scripts/update_index_universe.py "$@" > "${UPDATE_LOG}" 2>&1
UPDATE_EXIT_CODE=$?

FINAL_EXIT_CODE=${UPDATE_EXIT_CODE}
if [[ "${UPDATE_EXIT_CODE}" -eq 0 && ! -f "${PROJECT_ROOT}/data/index_universe.csv" ]]; then
  FINAL_EXIT_CODE=1
fi

{
  echo "Index Universe Update"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo "Update exit code: ${UPDATE_EXIT_CODE}"
  echo "Script exit code: ${FINAL_EXIT_CODE}"
  echo
  echo "Security boundary: research-only; no brokerage connection; no orders; no API key persistence."
  echo "Not financial advice"
  echo "Model output requires human review"
  echo "Data quality may affect results"
  echo
  cat "${UPDATE_LOG}"
  echo
  if [[ -f "${PROJECT_ROOT}/outputs/universe_expansion_report.md" ]]; then
    echo "Report: ${PROJECT_ROOT}/outputs/universe_expansion_report.md"
  fi
} > "${SUMMARY_FILE}"

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
