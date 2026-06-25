#!/usr/bin/env python3
"""
Generate Pixiu Daily Brief Quality Report.

Local-only research audit. This script reads existing local artifacts only; it
does not call providers, connect to private accounts, connect to brokers,
generate orders, place orders, or change scoring/ranking logic.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
DEFAULT_OUTPUT = OUTPUTS / "daily_brief_quality_report.md"

MAX_ARTIFACT_AGE_DAYS = 1
MIN_DEFAULT_SCORE_ROWS = 38
MIN_EXPANDED_SCORE_ROWS = 100
TOP_CANDIDATE_LIMIT = 10

VERDICT_USE = "USE"
VERDICT_REVIEW = "REVIEW CAREFULLY"
VERDICT_DO_NOT_USE = "DO NOT USE"

REQUIRED_BRIEF_MARKERS = [
    "Safety: research-only",
    "Not financial advice",
    "Default Watchlist Top Candidates",
    "Expanded-Universe Top Candidates",
    "Human Review Queue",
    "Data Quality / Risk Notes",
    "Output References",
    "Next Human Checklist",
    "Do not treat any row as an order",
]

BENIGN_UNAVAILABLE_PHRASES = [
    "options analysis unavailable",
    "options_analysis_status=unavailable",
    "options_analysis_status is unavailable",
]


class AuditConfig:
    def __init__(
        self,
        root: Path = ROOT,
        as_of_date: date | None = None,
        output_path: Path | None = None,
        default_scores: Path | None = None,
        expanded_scores: Path | None = None,
        daily_brief: Path | None = None,
        drift_report: Path | None = None,
        signal_outcomes_csv: Path | None = None,
        signal_outcomes_report: Path | None = None,
        production_log_dir: Path | None = None,
    ) -> None:
        self.root = Path(root)
        self.outputs = self.root / "outputs"
        self.as_of_date = as_of_date or date.today()
        self.output_path = output_path or self.outputs / "daily_brief_quality_report.md"
        self.default_scores = default_scores or self.outputs / "daily_investment_scores.csv"
        self.expanded_scores = expanded_scores or self.outputs / "expanded_daily_investment_scores.csv"
        self.daily_brief = daily_brief or self.outputs / "daily_brief_report.md"
        self.drift_report = drift_report or self.outputs / "action_bias_drift_report.md"
        self.signal_outcomes_csv = signal_outcomes_csv or self.outputs / "signal_outcomes.csv"
        self.signal_outcomes_report = signal_outcomes_report or self.outputs / "signal_outcomes_report.md"
        self.production_log_dir = production_log_dir or self.outputs / "logs"


class AuditReport:
    def __init__(
        self,
        verdict: str,
        hard_failures: list[str],
        warnings: list[str],
        checks: list[dict[str, str]],
        details: dict[str, object],
    ) -> None:
        self.verdict = verdict
        self.hard_failures = hard_failures
        self.warnings = warnings
        self.checks = checks
        self.details = details


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def top_rows(rows: Iterable[dict[str, str]], score_key: str, limit: int = TOP_CANDIDATE_LIMIT) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: as_float(row.get(score_key)), reverse=True)[:limit]


def artifact_date(path: Path) -> date:
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def artifact_age_days(path: Path, as_of_date: date) -> int:
    return (as_of_date - artifact_date(path)).days


def add_check(checks: list[dict[str, str]], dimension: str, status: str, evidence: str) -> None:
    checks.append({"dimension": dimension, "status": status, "evidence": evidence})


def git_status(root: Path) -> str:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return "git status unavailable"
    return proc.stdout.strip() or "clean"


def status_from_fail_warn(hard_failures: list[str], warnings: list[str], hard_start: int, warn_start: int) -> str:
    if len(hard_failures) > hard_start:
        return "FAIL"
    if len(warnings) > warn_start:
        return "WARN"
    return "PASS"


def check_freshness(config: AuditConfig, hard_failures: list[str], checks: list[dict[str, str]]) -> None:
    required = [
        ("default scores", config.default_scores),
        ("expanded scores", config.expanded_scores),
        ("daily brief", config.daily_brief),
        ("action-bias drift report", config.drift_report),
        ("signal outcomes CSV", config.signal_outcomes_csv),
        ("signal outcomes report", config.signal_outcomes_report),
    ]
    evidence: list[str] = []
    start = len(hard_failures)
    for label, path in required:
        display = rel(path, config.root)
        if not path.exists():
            hard_failures.append(f"Missing required artifact: {display}")
            evidence.append(f"{label}: missing")
            continue
        age = artifact_age_days(path, config.as_of_date)
        evidence.append(f"{label}: mdate={artifact_date(path).isoformat()}, age_days={age}")
        if age > MAX_ARTIFACT_AGE_DAYS:
            hard_failures.append(
                f"Required artifact is stale: {display} age_days={age}, max_age_days={MAX_ARTIFACT_AGE_DAYS}"
            )
    add_check(
        checks,
        "Freshness of required daily artifacts",
        "FAIL" if len(hard_failures) > start else "PASS",
        "; ".join(evidence),
    )


def check_row_counts(
    config: AuditConfig,
    default_rows: list[dict[str, str]],
    expanded_rows: list[dict[str, str]],
    hard_failures: list[str],
    checks: list[dict[str, str]],
) -> None:
    start = len(hard_failures)
    default_count = len(default_rows)
    expanded_count = len(expanded_rows)
    if config.default_scores.exists() and default_count < MIN_DEFAULT_SCORE_ROWS:
        hard_failures.append(f"Default score rows too low: {default_count} < {MIN_DEFAULT_SCORE_ROWS}")
    if config.expanded_scores.exists() and expanded_count < MIN_EXPANDED_SCORE_ROWS:
        hard_failures.append(f"Expanded score rows too low: {expanded_count} < {MIN_EXPANDED_SCORE_ROWS}")
    add_check(
        checks,
        "Expected row-count sanity",
        "FAIL" if len(hard_failures) > start else "PASS",
        (
            f"default_rows={default_count}, min_default={MIN_DEFAULT_SCORE_ROWS}; "
            f"expanded_rows={expanded_count}, min_expanded={MIN_EXPANDED_SCORE_ROWS}"
        ),
    )


def check_git_cleanliness(config: AuditConfig, warnings: list[str], checks: list[dict[str, str]]) -> None:
    status = git_status(config.root)
    if status not in {"clean", "git status unavailable"}:
        warnings.append("Repository has changes; reported as evidence only, not a quality hard failure.")
    add_check(checks, "Repository cleanliness evidence", "EVIDENCE", status)


def latest_production_log(log_dir: Path) -> Path | None:
    logs = [path for path in log_dir.glob("pixiu-production-*.log") if path.is_file()]
    if not logs:
        return None
    return sorted(logs, key=lambda path: (path.stat().st_mtime, path.name))[-1]


def check_duplicate_and_run_status(
    config: AuditConfig,
    hard_failures: list[str],
    warnings: list[str],
    checks: list[dict[str, str]],
) -> None:
    hard_start = len(hard_failures)
    warn_start = len(warnings)
    evidence: list[str] = []

    drift_text = read_text(config.drift_report)
    if "- Duplicate production groups found" in drift_text or "Duplicate production groups found:" in drift_text:
        hard_failures.append("Duplicate production groups reported by action-bias drift evidence.")
        evidence.append("duplicate_status=duplicate_groups_found")
    elif "No duplicate production groups detected" in drift_text:
        evidence.append("duplicate_status=none_detected")
    elif "No production run found" in drift_text:
        warnings.append("No production run found in drift evidence; review production history before use.")
        evidence.append("duplicate_status=no_production_run_found")
    else:
        warnings.append("Duplicate-production status is unclear in existing drift evidence.")
        evidence.append("duplicate_status=unclear")

    log_path = latest_production_log(config.production_log_dir)
    if log_path is None:
        warnings.append("No production log found; run-status evidence is unavailable.")
        evidence.append("run_status=production_log_missing")
    else:
        log_text = read_text(log_path)
        match = re.search(r"Final script exit:\s*(\d+)", log_text)
        if not match:
            warnings.append(f"Latest production log lacks final exit status: {rel(log_path, config.root)}")
            evidence.append(f"run_status=missing_final_exit in {rel(log_path, config.root)}")
        elif match.group(1) != "0":
            hard_failures.append(f"Latest production run final exit was non-zero: {match.group(1)}")
            evidence.append(f"run_status=final_exit_{match.group(1)} in {rel(log_path, config.root)}")
        else:
            evidence.append(f"run_status=final_exit_0 in {rel(log_path, config.root)}")

    add_check(
        checks,
        "Duplicate-production and run-status detection",
        status_from_fail_warn(hard_failures, warnings, hard_start, warn_start),
        "; ".join(evidence),
    )


def section_text(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.find(marker)
    if start == -1:
        return ""
    next_start = markdown.find("\n## ", start + len(marker))
    return markdown[start:] if next_start == -1 else markdown[start:next_start]


def check_top_candidate_consistency(
    daily_brief_text: str,
    default_top: list[dict[str, str]],
    expanded_top: list[dict[str, str]],
    hard_failures: list[str],
    warnings: list[str],
    checks: list[dict[str, str]],
) -> None:
    hard_start = len(hard_failures)
    warn_start = len(warnings)
    evidence: list[str] = []

    top_default = (default_top[0].get("ticker") or "").strip() if default_top else ""
    top_expanded = (expanded_top[0].get("ticker") or "").strip() if expanded_top else ""
    evidence.append(f"top_default={top_default or 'N/A'}")
    evidence.append(f"top_expanded={top_expanded or 'N/A'}")

    if not top_default:
        hard_failures.append("Top default candidate unavailable because default score rows are empty.")
    elif f"Top default watchlist candidate: **{top_default}**" not in daily_brief_text:
        hard_failures.append(f"Daily Brief top default candidate does not match score CSV top default: {top_default}")

    if not top_expanded:
        hard_failures.append("Top expanded candidate unavailable because expanded score rows are empty.")
    elif f"Top expanded-universe candidate: **{top_expanded}**" not in daily_brief_text:
        hard_failures.append(f"Daily Brief top expanded candidate does not match score CSV top expanded: {top_expanded}")

    default_section = section_text(daily_brief_text, "2. Default Watchlist Top Candidates")
    expanded_section = section_text(daily_brief_text, "3. Expanded-Universe Top Candidates")
    missing_default = [
        row.get("ticker", "")
        for row in default_top
        if row.get("ticker") and f"| {row.get('ticker')} |" not in default_section
    ]
    missing_expanded = [
        row.get("ticker", "")
        for row in expanded_top
        if row.get("ticker") and f"| {row.get('ticker')} |" not in expanded_section
    ]
    if missing_default:
        warnings.append("Daily Brief default top table omits score CSV top tickers: " + ", ".join(missing_default[:10]))
    if missing_expanded:
        warnings.append("Daily Brief expanded top table omits score CSV top tickers: " + ", ".join(missing_expanded[:10]))

    add_check(
        checks,
        "Top-candidate consistency",
        status_from_fail_warn(hard_failures, warnings, hard_start, warn_start),
        "; ".join(evidence),
    )


def material_gap_text(row: dict[str, str]) -> str:
    text = " ".join([row.get("primary_reason", ""), row.get("risk_flags", "")]).lower()
    for phrase in BENIGN_UNAVAILABLE_PHRASES:
        text = text.replace(phrase, "")
    return text


def is_data_gap_row(row: dict[str, str]) -> bool:
    if (row.get("action_bias") or "").strip() == "Data Gap Review":
        return True
    if "low" in (row.get("confidence") or "").lower():
        return True
    if as_float(row.get("data_quality_score"), 100.0) < 70:
        return True
    text = material_gap_text(row)
    return any(marker in text for marker in ["data gap", "missing", "insufficient", "unavailable"])


def check_data_gap_ratio(
    expanded_rows: list[dict[str, str]],
    hard_failures: list[str],
    warnings: list[str],
    checks: list[dict[str, str]],
) -> None:
    hard_start = len(hard_failures)
    warn_start = len(warnings)
    if not expanded_rows:
        hard_failures.append("Data-gap ratio unavailable because expanded score rows are empty.")
        ratio = 1.0
        gap_count = 0
    else:
        gap_count = sum(1 for row in expanded_rows if is_data_gap_row(row))
        ratio = gap_count / len(expanded_rows)
        if gap_count == len(expanded_rows):
            hard_failures.append("All expanded score rows meet existing data-gap semantics.")
        elif gap_count > 0:
            warnings.append(f"Expanded-universe data-gap ratio is non-zero: {gap_count}/{len(expanded_rows)}")
    add_check(
        checks,
        "Data-gap ratio",
        status_from_fail_warn(hard_failures, warnings, hard_start, warn_start),
        f"expanded_gap_rows={gap_count}, expanded_rows={len(expanded_rows)}, ratio={ratio:.4f}",
    )


def check_signal_outcomes(
    signal_rows: list[dict[str, str]],
    default_top: list[dict[str, str]],
    expanded_top: list[dict[str, str]],
    hard_failures: list[str],
    warnings: list[str],
    checks: list[dict[str, str]],
) -> None:
    hard_start = len(hard_failures)
    warn_start = len(warnings)

    if not signal_rows:
        hard_failures.append("Signal-outcome rows are missing or empty.")
        add_check(checks, "Missing signal-outcome coverage", "FAIL", "outcome_rows=0")
        return

    bad_status = [
        row.get("ticker", "UNKNOWN")
        for row in signal_rows
        if (row.get("outcome_status") or "").strip().lower() != "ok"
    ]
    if bad_status:
        hard_failures.append("Signal-outcome rows have non-ok status: " + ", ".join(bad_status[:20]))

    covered = {
        (row.get("ticker") or "").strip().upper()
        for row in signal_rows
        if (row.get("ticker") or "").strip()
    }
    required_top = []
    if default_top:
        required_top.append((default_top[0].get("ticker") or "").strip().upper())
    if expanded_top:
        required_top.append((expanded_top[0].get("ticker") or "").strip().upper())
    missing = sorted({ticker for ticker in required_top if ticker and ticker not in covered})
    if missing:
        warnings.append("Missing signal-outcome coverage for current top candidates: " + ", ".join(missing))

    add_check(
        checks,
        "Missing signal-outcome coverage",
        status_from_fail_warn(hard_failures, warnings, hard_start, warn_start),
        f"outcome_rows={len(signal_rows)}, covered_top={sorted(set(required_top) - set(missing))}, missing_top={missing}",
    )


def check_brief_usefulness(
    daily_brief_text: str,
    hard_failures: list[str],
    checks: list[dict[str, str]],
) -> None:
    start = len(hard_failures)
    missing = [marker for marker in REQUIRED_BRIEF_MARKERS if marker not in daily_brief_text]
    if missing:
        hard_failures.append("Daily Brief is missing required human-review content: " + ", ".join(missing))
    add_check(
        checks,
        "Human-review usefulness",
        "FAIL" if len(hard_failures) > start else "PASS",
        "missing_markers=" + (", ".join(missing) if missing else "none"),
    )


def choose_verdict(hard_failures: list[str], warnings: list[str]) -> str:
    if hard_failures:
        return VERDICT_DO_NOT_USE
    if warnings:
        return VERDICT_REVIEW
    return VERDICT_USE


def build_quality_audit(config: AuditConfig) -> AuditReport:
    hard_failures: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    check_freshness(config, hard_failures, checks)

    default_rows = read_csv(config.default_scores)
    expanded_rows = read_csv(config.expanded_scores)
    signal_rows = read_csv(config.signal_outcomes_csv)
    daily_brief_text = read_text(config.daily_brief)
    default_top = top_rows(default_rows, "final_score")
    expanded_top = top_rows(expanded_rows, "action_score")

    check_row_counts(config, default_rows, expanded_rows, hard_failures, checks)
    check_git_cleanliness(config, warnings, checks)
    check_duplicate_and_run_status(config, hard_failures, warnings, checks)
    check_top_candidate_consistency(daily_brief_text, default_top, expanded_top, hard_failures, warnings, checks)
    check_data_gap_ratio(expanded_rows, hard_failures, warnings, checks)
    check_signal_outcomes(signal_rows, default_top, expanded_top, hard_failures, warnings, checks)
    check_brief_usefulness(daily_brief_text, hard_failures, checks)

    details = {
        "as_of_date": config.as_of_date.isoformat(),
        "thresholds": {
            "MAX_ARTIFACT_AGE_DAYS": MAX_ARTIFACT_AGE_DAYS,
            "MIN_DEFAULT_SCORE_ROWS": MIN_DEFAULT_SCORE_ROWS,
            "MIN_EXPANDED_SCORE_ROWS": MIN_EXPANDED_SCORE_ROWS,
            "TOP_CANDIDATE_LIMIT": TOP_CANDIDATE_LIMIT,
        },
        "default_rows": len(default_rows),
        "expanded_rows": len(expanded_rows),
        "signal_outcome_rows": len(signal_rows),
        "default_top_tickers": [row.get("ticker", "") for row in default_top],
        "expanded_top_tickers": [row.get("ticker", "") for row in expanded_top],
        "expanded_action_bias_counts": dict(Counter(row.get("action_bias", "Unknown") or "Unknown" for row in expanded_rows)),
    }

    return AuditReport(
        verdict=choose_verdict(hard_failures, warnings),
        hard_failures=hard_failures,
        warnings=warnings,
        checks=checks,
        details=details,
    )


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        cleaned = [
            str(cell).replace("\n", "<br>").replace("|", "/")
            for cell in row
        ]
        lines.append("| " + " | ".join(cleaned) + " |")
    return "\n".join(lines)


def render_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f"- {empty_text}"
    return "\n".join(f"- {item}" for item in items)


def render_report(report: AuditReport, config: AuditConfig) -> str:
    thresholds = report.details["thresholds"]
    threshold_lines = [f"- {key}: {value}" for key, value in thresholds.items()]
    check_rows = [
        [check["dimension"], check["status"], check["evidence"]]
        for check in report.checks
    ]
    default_top = report.details["default_top_tickers"]
    expanded_top = report.details["expanded_top_tickers"]
    bias_counts = report.details["expanded_action_bias_counts"]
    bias_lines = [f"- {label}: {count}" for label, count in sorted(bias_counts.items())] or ["- None"]

    lines = [
        "# Pixiu Daily Brief Quality Report",
        "",
        f"Final verdict: **{report.verdict}**",
        "",
        "Research-only quality audit. Not financial advice. No broker connectivity, order generation, order placement, provider call, or scoring change is performed.",
        "",
        "## Audit Scope",
        "",
        f"- Project: `{config.root}`",
        f"- As-of date: {config.as_of_date.isoformat()}",
        f"- Output: `{rel(config.output_path, config.root)}`",
        "",
        "## Thresholds",
        "",
        *threshold_lines,
        "",
        "## Dimension Results",
        "",
        md_table(["Dimension", "Status", "Evidence"], check_rows),
        "",
        "## Hard Failures",
        "",
        render_list(report.hard_failures, "None"),
        "",
        "## Warnings",
        "",
        render_list(report.warnings, "None"),
        "",
        "## Candidate Evidence",
        "",
        "- Top default score tickers: " + (", ".join(default_top) if default_top else "None"),
        "- Top expanded score tickers: " + (", ".join(expanded_top) if expanded_top else "None"),
        "",
        "## Expanded Action-Bias Counts",
        "",
        *bias_lines,
        "",
        "## Verdict Semantics",
        "",
        "- USE: no hard failures and no warnings.",
        "- REVIEW CAREFULLY: no hard failures, but at least one warning.",
        "- DO NOT USE: at least one hard failure.",
        "",
        "Missing or stale required daily artifacts never produce USE.",
        "",
    ]
    return "\n".join(lines)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Pixiu daily brief quality audit report.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--as-of-date", help="YYYY-MM-DD; defaults to local current date.")
    parser.add_argument("--default-scores", type=Path)
    parser.add_argument("--expanded-scores", type=Path)
    parser.add_argument("--daily-brief", type=Path)
    parser.add_argument("--drift-report", type=Path)
    parser.add_argument("--signal-outcomes-csv", type=Path)
    parser.add_argument("--signal-outcomes-report", type=Path)
    args = parser.parse_args()

    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    config = AuditConfig(
        root=ROOT,
        as_of_date=parse_date(args.as_of_date),
        output_path=output_path,
        default_scores=args.default_scores if args.default_scores is None or args.default_scores.is_absolute() else ROOT / args.default_scores,
        expanded_scores=args.expanded_scores if args.expanded_scores is None or args.expanded_scores.is_absolute() else ROOT / args.expanded_scores,
        daily_brief=args.daily_brief if args.daily_brief is None or args.daily_brief.is_absolute() else ROOT / args.daily_brief,
        drift_report=args.drift_report if args.drift_report is None or args.drift_report.is_absolute() else ROOT / args.drift_report,
        signal_outcomes_csv=(
            args.signal_outcomes_csv
            if args.signal_outcomes_csv is None or args.signal_outcomes_csv.is_absolute()
            else ROOT / args.signal_outcomes_csv
        ),
        signal_outcomes_report=(
            args.signal_outcomes_report
            if args.signal_outcomes_report is None or args.signal_outcomes_report.is_absolute()
            else ROOT / args.signal_outcomes_report
        ),
    )
    report = build_quality_audit(config)
    rendered = render_report(report, config)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(rendered, encoding="utf-8")

    print(f"Daily brief quality report: {config.output_path}")
    print(f"final_verdict: {report.verdict}")
    print(f"hard_failures: {len(report.hard_failures)}")
    print(f"warnings: {len(report.warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
