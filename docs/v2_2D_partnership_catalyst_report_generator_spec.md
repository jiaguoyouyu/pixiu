# Pixiu v2.2D Partnership Catalyst Report Generator — SPEC

## Problem Statement

Pixiu has a Major Partnership Catalyst Radar skill, but the skill is currently documentation-first. The next step is to turn it into a repeatable local report generator that can create structured catalyst research reports from public or user-provided evidence.

## Goals

- Generate deterministic Markdown reports for major partnership / anchor customer / strategic alliance / JV / M&A / restructuring / business-model transformation catalyst research.
- Preserve Pixiu research-only boundary.
- Separate observed facts from inference.
- Require source hygiene, contradictions, invalidation triggers, probability band, and monitoring checklist.
- Support repeatable local workflow without live provider dependency.
- Keep generated reports out of Git tracking.

## Non-Goals

- No brokerage connection.
- No order placement or cancellation.
- No automated buy/sell execution.
- No credential storage.
- No Koyfin/Fiscal.ai/Quartr login automation.
- No scraping.
- No fabricated options analytics or source data.
- No accusation of insider trading.
- No certainty claims.

## Inputs

Template input file:

- ticker
- company_name
- thesis_date
- suspected_catalyst_type
- observed_signal
- option_flow_summary
- institutional_evidence
- operational_evidence
- SEC_or_filing_evidence
- catalyst_calendar
- source_links_or_notes
- known_contradictions
- expected_window
- analyst_notes

## Outputs

Generated Markdown report under:

outputs/partnership_catalyst_reports/

Required report sections:

- Executive Summary
- Ticker and Thesis Date
- Observed Evidence
- Catalyst Hypothesis
- Evidence Table
- Probability Band
- Scenario Table
- Contradictions and Invalidation Triggers
- Source Hygiene
- Monitoring Checklist
- Research-only disclaimer

Required disclaimer:

This is probabilistic research based on public/user-provided information and is not investment advice.

## Acceptance Criteria

- Generator compiles.
- Generator runs on a sample input.
- Markdown report is created.
- Report includes all required sections.
- Report includes research-only disclaimer.
- Verifier passes.
- Existing production verifier still passes.
- No generated reports are tracked by Git.
- No credential exposure or forbidden automation is added.
