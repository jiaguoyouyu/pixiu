#!/usr/bin/env python3
"""
Generate Pixiu Daily Brief Report.

Local-only research report generator.
Local research output only; no broker connectivity, order placement, trade automation, or secret handling.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
DEFAULT_CSV = OUTPUTS / "daily_investment_scores.csv"
EXPANDED_CSV = OUTPUTS / "expanded_daily_investment_scores.csv"
DRIFT_REPORT = OUTPUTS / "action_bias_drift_report.md"
SIGNAL_REPORT = OUTPUTS / "signal_outcomes_report.md"
DEFAULT_OUTPUT = OUTPUTS / "daily_brief_report.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def top_rows(rows: Iterable[dict[str, str]], score_key: str, limit: int = 10) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: as_float(row.get(score_key)), reverse=True)[:limit]


def count_key(rows: Iterable[dict[str, str]], key: str) -> Counter[str]:
    return Counter((row.get(key) or "Unknown").strip() or "Unknown" for row in rows)


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_No rows available._"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        cleaned = [str(cell).replace("|", "/") for cell in row]
        lines.append("| " + " | ".join(cleaned) + " |")
    return "\n".join(lines)


def copy_clipboard(text: str) -> str:
    if not shutil.which("pbcopy"):
        return "pbcopy unavailable"
    proc = subprocess.run(["pbcopy"], input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return "copied to clipboard" if proc.returncode == 0 else "pbcopy failed"


def git_status() -> str:
    proc = subprocess.run(["git", "status", "--short"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return "git status unavailable"
    return proc.stdout.strip() or "clean"


def file_line(path: Path) -> str:
    return f"`{path.relative_to(ROOT)}`" if path.exists() else f"`{path.relative_to(ROOT)}` missing"


def build_report(output_path: Path) -> str:
    daily = read_csv(DEFAULT_CSV)
    expanded = read_csv(EXPANDED_CSV)

    daily_top = top_rows(daily, "final_score", 10)
    expanded_top = top_rows(expanded, "action_score", 10)

    daily_counts = count_key(daily, "strategy")
    expanded_counts = count_key(expanded, "action_bias")

    top_default_rows = [
        [
            row.get("ticker", ""),
            f"{as_float(row.get('final_score')):.2f}",
            row.get("strategy", ""),
            row.get("confidence", ""),
            row.get("cad_alternative", ""),
        ]
        for row in daily_top
    ]

    top_expanded_rows = [
        [
            row.get("ticker", ""),
            f"{as_float(row.get('action_score')):.2f}",
            row.get("action_bias", ""),
            row.get("confidence", ""),
            row.get("cad_alternative", ""),
        ]
        for row in expanded_top
    ]

    daily_count_rows = [[key, str(value)] for key, value in daily_counts.most_common()]
    expanded_count_rows = [[key, str(value)] for key, value in expanded_counts.most_common()]

    buy_watch = [
        row for row in daily
        if (row.get("strategy") or "") in {"Ranked Buy Candidate", "Pullback Buy", "ETF Trend Candidate", "High-Quality Watch"}
    ]
    buy_watch = top_rows(buy_watch, "final_score", 8)

    human_review_rows = [
        [
            row.get("ticker", ""),
            f"{as_float(row.get('final_score')):.2f}",
            row.get("strategy", ""),
            row.get("cad_note", "")[:100],
        ]
        for row in buy_watch
    ]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    lines = [
        "# Pixiu Daily Brief Report",
        "",
        f"- Generated: {now}",
        f"- Project: `{ROOT}`",
        f"- Git status: `{git_status()}`",
        "- Safety: research-only; no broker connectivity, order placement, trade automation, or secret handling.",
        "- Disclaimer: Not financial advice. Model output requires human review. Data quality may affect results.",
        "",
        "## 1. Executive Summary / 今日摘要",
        "",
        f"- Default watchlist rows: **{len(daily)}**",
        f"- Expanded universe rows: **{len(expanded)}**",
        f"- Top default watchlist candidate: **{daily_top[0].get('ticker', 'N/A') if daily_top else 'N/A'}**",
        f"- Top expanded-universe candidate: **{expanded_top[0].get('ticker', 'N/A') if expanded_top else 'N/A'}**",
        "- Use this brief as a research queue, not as a trading instruction.",
        "",
        "## 2. Default Watchlist Top Candidates",
        "",
        md_table(["Ticker", "Score", "Strategy", "Confidence", "CAD Alternative"], top_default_rows),
        "",
        "## 3. Expanded-Universe Top Candidates",
        "",
        md_table(["Ticker", "Action Score", "Action Bias", "Confidence", "CAD Alternative"], top_expanded_rows),
        "",
        "## 4. Action / Strategy Distribution",
        "",
        "### Default Watchlist Strategy Counts",
        "",
        md_table(["Strategy", "Rows"], daily_count_rows),
        "",
        "### Expanded Universe Action-Bias Counts",
        "",
        md_table(["Action Bias", "Rows"], expanded_count_rows),
        "",
        "## 5. Human Review Queue / 人工复核队列",
        "",
        "These are candidates worth manual review before any real-world decision.",
        "",
        md_table(["Ticker", "Score", "Strategy", "Review Note"], human_review_rows),
        "",
        "## 6. Data Quality / Risk Notes",
        "",
        "- CAD alternatives are convenience mappings only; verify liquidity, spread, CDR ratio, fees, holdings, hedge status, and tax implications manually.",
        "- Options analysis is unavailable unless explicitly supported by a future verified data pipeline.",
        "- Missing manual price history is acceptable for sample-mode signal outcome verification but limits real outcome tracking.",
        "- Duplicate production check should remain clean before trusting daily production history.",
        "",
        "## 7. Output References",
        "",
        f"- Daily scores: {file_line(DEFAULT_CSV)}",
        f"- Expanded scores: {file_line(EXPANDED_CSV)}",
        f"- Action-bias drift report: {file_line(DRIFT_REPORT)}",
        f"- Signal outcomes report: {file_line(SIGNAL_REPORT)}",
        f"- Daily brief: `{output_path.relative_to(ROOT)}`",
        "",
        "## 8. Next Human Checklist",
        "",
        "- Review top candidates against current news, earnings calendar, valuation, and position/risk constraints.",
        "- Confirm whether any Data Gap names require manual research before being promoted.",
        "- Do not treat any row as an order or recommendation without independent review.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Pixiu daily brief Markdown report.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()

    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    report = build_report(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    copy_status = "copy skipped (--no-copy)" if args.no_copy else copy_clipboard(report)
    print(f"Daily brief report: {output_path}")
    print(f"copy_status: {copy_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
