#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = BASE_DIR / "templates" / "major_partnership_catalyst_input_template.md"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs" / "partnership_catalyst_reports"

DISCLAIMER = "This is probabilistic research based on public/user-provided information and is not investment advice."

REQUIRED_SECTIONS = [
    "Executive Summary",
    "Ticker and Thesis Date",
    "Observed Evidence",
    "Catalyst Hypothesis",
    "Evidence Table",
    "Probability Band",
    "Scenario Table",
    "Contradictions and Invalidation Triggers",
    "Source Hygiene",
    "Monitoring Checklist",
    "Research-only Disclaimer",
]


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    allowed = {
        "ticker",
        "company_name",
        "thesis_date",
        "suspected_catalyst_type",
        "expected_window",
    }
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        if key in allowed:
            fields[key] = value.strip()
    return fields


def section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$([\s\S]*?)(?=^## |\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        return "Not provided."
    body = match.group(1).strip()
    return body or "Not provided."


def probability_band(text: str) -> str:
    lowered = text.lower()
    strong = sum(
        marker in lowered
        for marker in [
            "confirmed",
            "8-k",
            "material agreement",
            "contract",
            "customer",
            "joint venture",
            "strategic investment",
            "lease",
        ]
    )
    weak = sum(
        marker in lowered
        for marker in [
            "no verified",
            "unavailable",
            "rumor",
            "speculative",
            "not provided",
        ]
    )
    if strong >= 4 and weak <= 2:
        return "65-79% strong convergence, still unconfirmed"
    if strong >= 2:
        return "50-64% plausible but missing key proof"
    if weak >= 4:
        return "30-49% speculative or data-limited"
    return "50-64% plausible but requires verification"


def build_report(input_text: str) -> tuple[str, str, str]:
    fields = parse_fields(input_text)
    ticker = fields.get("ticker", "UNKNOWN").upper()
    company = fields.get("company_name", "Unknown Company")
    thesis_date = fields.get("thesis_date", dt.date.today().isoformat())
    catalyst_type = fields.get("suspected_catalyst_type", "Not specified")
    expected_window = fields.get("expected_window", "Not specified")

    observed = section(input_text, "Observed Signal")
    options = section(input_text, "Option Flow Summary")
    institutional = section(input_text, "Institutional Evidence")
    operational = section(input_text, "Operational Evidence")
    filings = section(input_text, "SEC or Filing Evidence")
    calendar = section(input_text, "Catalyst Calendar")
    sources = section(input_text, "Source Links or Notes")
    contradictions = section(input_text, "Known Contradictions")
    notes = section(input_text, "Analyst Notes")
    prob = probability_band(input_text)

    report = f"""# Major Partnership Catalyst Radar Report - {ticker}

## Executive Summary

{company} ({ticker}) is flagged for research-only catalyst review based on submitted evidence. The current thesis type is: {catalyst_type}. This report separates observed evidence from inference and requires human review.

## Ticker and Thesis Date

- Ticker: {ticker}
- Company: {company}
- Thesis date: {thesis_date}
- Suspected catalyst type: {catalyst_type}
- Expected window: {expected_window}

## Observed Evidence

{observed}

## Catalyst Hypothesis

The working hypothesis is that {company} may have a major catalyst related to {catalyst_type}. This is an inference from the provided evidence, not a confirmed event.

## Evidence Table

| Evidence Area | Observed Fact | Strength | Gap / Caveat |
|---|---|---:|---|
| Options / derivatives | {options} | Data-dependent | Do not infer IV or unusual flow unless verified data is provided. |
| Institutional | {institutional} | Data-dependent | Ownership data can be delayed or incomplete. |
| Operational | {operational} | Data-dependent | Hiring, capex, customer, or supply-chain evidence may be circumstantial. |
| SEC / filings | {filings} | Data-dependent | Material agreement evidence is strongest when directly filed or disclosed. |
| Catalyst calendar | {calendar} | Data-dependent | Dates require monitoring and may shift. |

## Probability Band

{prob}

Never treat this as certainty. Pixiu should not output 100% probability for catalyst research.

## Scenario Table

| Scenario | Description | Probability Band | Key Confirmation | Key Invalidation |
|---|---|---:|---|---|
| Bull case | Catalyst is confirmed or evidence strengthens materially. | {prob} | Official filing, company confirmation, credible customer or partner disclosure. | No confirmation after expected window or contradictory filings. |
| Base case | Evidence remains plausible but incomplete. | 30-64% | More source convergence or timeline clarity. | Weak follow-through or stale evidence. |
| Bear case | Signal was noise or misread. | below 30% | N/A | Direct contradiction, failed event window, no operational support. |

## Contradictions and Invalidation Triggers

{contradictions}

## Source Hygiene

{sources}

Rules:
- Public or user-provided information only.
- Do not fabricate sources.
- Separate observed facts from inference.
- Treat missing data as a data gap.

## Monitoring Checklist

- Track official SEC filings and company press releases.
- Track earnings call language and investor presentation updates.
- Track credible partner or customer announcements.
- Track contradiction signals and missed windows.
- Revisit thesis after the expected window: {expected_window}.

## Analyst Notes

{notes}

## Research-only Disclaimer

{DISCLAIMER}
"""
    return ticker, thesis_date, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: input file not found: {args.input}")
        return 1

    input_text = args.input.read_text(encoding="utf-8")
    ticker, thesis_date, report = build_report(input_text)

    missing = [name for name in REQUIRED_SECTIONS if f"## {name}" not in report]
    if DISCLAIMER not in report:
        missing.append("required disclaimer")
    if missing:
        print("ERROR: generated report missing required content:")
        for item in missing:
            print(f"- {item}")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"{thesis_date}-{slugify(ticker)}-partnership-catalyst-report.md"
    output_path.write_text(report, encoding="utf-8")

    if args.stdout:
        print(report)
    print(f"Generated report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
