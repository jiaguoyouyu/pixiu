#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"

MODE="default"
for arg in "$@"; do
  case "${arg}" in
    --expanded-universe)
      MODE="expanded-universe"
      ;;
    *)
      echo "Unknown option: ${arg}" >&2
      echo "Usage: $0 [--expanded-universe]" >&2
      exit 2
      ;;
  esac
done

if [[ "${MODE}" == "expanded-universe" ]]; then
  SCORES_FILE="${PROJECT_ROOT}/outputs/expanded_daily_investment_scores.csv"
  REPORT_FILE="${PROJECT_ROOT}/outputs/expanded_daily_investment_report.md"
else
  SCORES_FILE="${PROJECT_ROOT}/outputs/daily_investment_scores.csv"
  REPORT_FILE="${PROJECT_ROOT}/outputs/daily_investment_report.md"
fi
SUMMARY_FILE="$(mktemp -t pixiu_summary.XXXXXX)"

cd "${PROJECT_ROOT}" || exit 1

if [[ "${MODE}" == "expanded-universe" ]]; then
  python3 scripts/pixiu.py --expanded-universe
else
  python3 scripts/pixiu.py
fi
RANKER_EXIT_CODE=$?

FINAL_EXIT_CODE=${RANKER_EXIT_CODE}
if [[ ! -f "${SCORES_FILE}" || ! -f "${REPORT_FILE}" ]]; then
  FINAL_EXIT_CODE=1
fi

{
  echo "Pixiu Daily Run"
  echo "Mode: ${MODE}"
  echo "Run timestamp: ${RUN_TIMESTAMP}"
  echo "Project root: ${PROJECT_ROOT}"
  echo "Ranker exit code: ${RANKER_EXIT_CODE}"
  echo "Script exit code: ${FINAL_EXIT_CODE}"
  echo
  echo "Output files:"
  if [[ -f "${SCORES_FILE}" ]]; then
    echo "- Scores CSV: ${SCORES_FILE}"
  else
    echo "- Scores CSV: MISSING (${SCORES_FILE})"
  fi
  if [[ -f "${REPORT_FILE}" ]]; then
    echo "- Markdown report: ${REPORT_FILE}"
  else
    echo "- Markdown report: MISSING (${REPORT_FILE})"
  fi
  echo
  echo "Security boundary: research-only; no brokerage connection; no orders; no private accounts; no naked options."
  echo "Not financial advice"
  echo "Model output requires human review"
  echo "Data quality may affect results"
  echo
} > "${SUMMARY_FILE}"

if [[ -f "${SCORES_FILE}" ]]; then
  python3 - "${SCORES_FILE}" >> "${SUMMARY_FILE}" <<'PY'
import csv
import sys
from collections import Counter

scores_path = sys.argv[1]
with open(scores_path, newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))

if rows and "action_bias" in rows[0]:
    print("Action bias counts:")
    counts = Counter(row.get("action_bias", "N/A") for row in rows)
    for action_bias, count in sorted(counts.items()):
        print(f"- {action_bias}: {count}")

    print()
    print("Top 20 expanded research tickers with CAD alternatives:")
    columns = [
        "ticker",
        "action_score",
        "action_bias",
        "confidence",
        "cad_alternative",
        "cad_note",
    ]
else:
    print("Strategy counts:")
    counts = Counter(row.get("strategy", "N/A") for row in rows)
    for strategy, count in sorted(counts.items()):
        print(f"- {strategy}: {count}")

    print()
    print("Top 20 ranked tickers with CAD alternatives:")
    columns = [
        "ticker",
        "final_score",
        "risk_penalty",
        "strategy",
        "confidence",
        "cad_alternative",
        "cad_note",
    ]
print(",".join(columns))
for row in rows[:20]:
    values = []
    for column in columns:
        value = str(row.get(column, "")).replace("\n", " ").replace(",", ";")
        values.append(value)
    print(",".join(values))
PY
else
  {
    echo "Strategy counts: unavailable because scores CSV is missing."
    echo
    echo "Top 20 ranked tickers with CAD alternatives: unavailable because scores CSV is missing."
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
