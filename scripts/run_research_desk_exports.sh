#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

KOYFIN_CSV="${PROJECT_ROOT}/outputs/koyfin_watchlists.csv"
KOYFIN_MD="${PROJECT_ROOT}/outputs/koyfin_watchlists.md"
FISCAL_MD="${PROJECT_ROOT}/outputs/fiscal_ai_research_questions.md"
DESK_BRIEF_MD="${PROJECT_ROOT}/outputs/daily_wall_street_desk_brief.md"
TASKS_CSV="${PROJECT_ROOT}/outputs/research_desk_tasks.csv"
SUMMARY_FILE="$(mktemp -t research_desk_exports_summary.XXXXXX)"
GENERATOR_LOG="$(mktemp -t research_desk_generator.XXXXXX)"

cd "${PROJECT_ROOT}" || exit 1

python3 scripts/generate_research_desk_exports.py > "${GENERATOR_LOG}" 2>&1
GENERATOR_EXIT_CODE=$?

FINAL_EXIT_CODE=${GENERATOR_EXIT_CODE}
for path in "${KOYFIN_CSV}" "${KOYFIN_MD}" "${FISCAL_MD}" "${DESK_BRIEF_MD}" "${TASKS_CSV}"; do
  if [[ ! -f "${path}" ]]; then
    FINAL_EXIT_CODE=1
  fi
done

{
  echo "Research Desk Exports Run"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo "Generator exit code: ${GENERATOR_EXIT_CODE}"
  echo "Script exit code: ${FINAL_EXIT_CODE}"
  echo
  echo "Security boundary: research-only; no brokerage connection; no orders; no private accounts; no Koyfin scraping; no Koyfin login automation; no Fiscal.ai API call."
  echo "Not financial advice"
  echo "Model output requires human review"
  echo "Data quality may affect results"
  echo
  echo "Output files:"
  for path in "${KOYFIN_CSV}" "${KOYFIN_MD}" "${FISCAL_MD}" "${DESK_BRIEF_MD}" "${TASKS_CSV}"; do
    if [[ -f "${path}" ]]; then
      echo "- ${path}"
    else
      echo "- MISSING: ${path}"
    fi
  done
  echo
} > "${SUMMARY_FILE}"

if [[ -f "${KOYFIN_CSV}" && -f "${TASKS_CSV}" ]]; then
  python3 - "${KOYFIN_CSV}" "${TASKS_CSV}" >> "${SUMMARY_FILE}" <<'PY'
import csv
import sys
from collections import Counter

koyfin_path, tasks_path = sys.argv[1], sys.argv[2]

with open(koyfin_path, newline="", encoding="utf-8") as handle:
    koyfin_rows = list(csv.DictReader(handle))
with open(tasks_path, newline="", encoding="utf-8") as handle:
    task_rows = list(csv.DictReader(handle))

groups = Counter(row.get("watchlist_name", "N/A") for row in koyfin_rows)
task_types = Counter(row.get("task_type", "N/A") for row in task_rows)

print(f"Koyfin watchlist rows: {len(koyfin_rows)}")
print("Koyfin watchlist groups:")
if not groups:
    print("- None")
else:
    for name, count in sorted(groups.items()):
        print(f"- {name}: {count}")

print()
print(f"Research desk tasks: {len(task_rows)}")
print("Task types:")
if not task_types:
    print("- None")
else:
    for name, count in sorted(task_types.items()):
        print(f"- {name}: {count}")

print()
print("Top 10 research desk tasks:")
columns = ["priority", "task_type", "ticker", "action", "status"]
if not task_rows:
    print("- None")
else:
    print(",".join(columns))
    for row in sorted(task_rows, key=lambda item: (item.get("priority", "9"), item.get("ticker", "")))[:10]:
        values = []
        for column in columns:
            values.append(str(row.get(column, "")).replace("\n", " ").replace(",", ";"))
        print(",".join(values))
PY
else
  {
    echo "Koyfin/task summary unavailable because one or more CSV outputs are missing."
  } >> "${SUMMARY_FILE}"
fi

{
  echo
  echo "Generator log excerpt:"
  tail -n 40 "${GENERATOR_LOG}"
} >> "${SUMMARY_FILE}"

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
