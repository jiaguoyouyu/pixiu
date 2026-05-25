#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

CALENDAR_FILE="${PROJECT_ROOT}/outputs/weekly_earnings_calendar.csv"
REPORT_FILE="${PROJECT_ROOT}/outputs/weekly_earnings_report.md"
SUMMARY_FILE="$(mktemp -t weekly_earnings_radar_summary.XXXXXX)"

cd "${PROJECT_ROOT}" || exit 1

python3 scripts/weekly_earnings_radar.py
RADAR_EXIT_CODE=$?

FINAL_EXIT_CODE=${RADAR_EXIT_CODE}
if [[ ! -f "${CALENDAR_FILE}" || ! -f "${REPORT_FILE}" ]]; then
  FINAL_EXIT_CODE=1
fi

{
  echo "Weekly Earnings Radar Run"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo "Radar exit code: ${RADAR_EXIT_CODE}"
  echo "Script exit code: ${FINAL_EXIT_CODE}"
  echo
  echo "Output files:"
  if [[ -f "${CALENDAR_FILE}" ]]; then
    echo "- Weekly earnings CSV: ${CALENDAR_FILE}"
  else
    echo "- Weekly earnings CSV: MISSING (${CALENDAR_FILE})"
  fi
  if [[ -f "${REPORT_FILE}" ]]; then
    echo "- Weekly Markdown report: ${REPORT_FILE}"
  else
    echo "- Weekly Markdown report: MISSING (${REPORT_FILE})"
  fi
  echo
  echo "Security boundary: research-only; no brokerage connection; no orders; no private accounts; no naked options."
  echo "Not financial advice"
  echo "Model output requires human review"
  echo "Data quality may affect results"
  echo
} > "${SUMMARY_FILE}"

if [[ -f "${CALENDAR_FILE}" ]]; then
  python3 - "${CALENDAR_FILE}" >> "${SUMMARY_FILE}" <<'PY'
import csv
import sys

calendar_path = sys.argv[1]
with open(calendar_path, newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))

def as_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None

confirmed_next_7 = []
for row in rows:
    days = as_int(row.get("days_until_earnings"))
    if days is not None and 0 <= days <= 7:
        confirmed_next_7.append(row)

data_gap_count = sum(
    1
    for row in rows
    if row.get("earnings_date") in {"", "N/A", None}
    or row.get("importance_bucket") == "Data Gap / Watch"
)

print("Top earnings list:")
if not confirmed_next_7:
    print("- None confirmed in next 7 calendar days")
else:
    columns = [
        "ticker",
        "company_name",
        "earnings_date",
        "report_timing",
        "days_until_earnings",
        "importance_score",
        "importance_bucket",
        "cad_alternative",
    ]
    print(",".join(columns))
    for row in confirmed_next_7[:10]:
        values = []
        for column in columns:
            value = str(row.get(column, "")).replace("\n", " ").replace(",", ";")
            values.append(value)
        print(",".join(values))

print()
print(f"Confirmed earnings in next 7 calendar days: {len(confirmed_next_7)}")
print(f"No confirmed earnings date / data gaps: {data_gap_count}")
PY
else
  {
    echo "Top earnings list: unavailable because weekly earnings CSV is missing."
    echo
    echo "No confirmed earnings date / data gaps: unavailable because weekly earnings CSV is missing."
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
