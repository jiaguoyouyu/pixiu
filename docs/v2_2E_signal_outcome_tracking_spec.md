# Pixiu v2.2E Signal Outcome Tracking / Forward Return Review — SPEC

## Problem Statement

Pixiu can generate daily action-bias signals and partnership catalyst research reports, but it does not yet measure whether those signals actually produce forward returns or excess returns over time.

Without outcome tracking, Pixiu can look intelligent but cannot prove whether Buy/Add Watch, Pullback Buy Watch, Avoid Chase, Earnings Event Risk, Data Gap Review, or catalyst probability bands have real alpha.

## Goal

Build a local-data-first outcome tracking foundation that measures forward returns after Pixiu signals.

## Core Questions

- What happens after Buy/Add Watch signals over 1D / 5D / 10D / 20D / 60D?
- Does Pullback Buy Watch have better risk/reward than direct Buy/Add Watch?
- Does Avoid Chase help avoid short-term drawdowns?
- Does Earnings Event Risk identify higher-volatility windows?
- Do catalyst reports with higher probability bands perform better?
- Which signal categories produce positive excess return vs SPY / QQQ / SMH?

## Non-Goals

- No brokerage connection.
- No order placement.
- No automated trading.
- No credential storage.
- No live provider dependency in v2.2E initial version.
- No scoring formula changes.
- No portfolio allocation recommendation.
- No financial advice.

## Initial Data Source

Local CSV only:

data/manual_price_history.csv

Template:

data/manual_price_history.template.csv

Required columns:

ticker,date,close,source

Optional columns:

open,high,low,volume,adjusted_close

## Output Files

outputs/signal_outcomes.csv
outputs/signal_outcomes_report.md

Generated outputs must remain ignored by Git.

## Proposed Script

scripts/track_signal_outcomes.py

## Proposed Verifier

scripts/verify_signal_outcomes.sh

## Acceptance Criteria

- Script compiles.
- Verifier shell syntax passes.
- Template price history exists.
- Missing manual_price_history.csv is handled gracefully.
- Sample/manual price history can produce signal outcome rows.
- outputs/signal_outcomes.csv is generated.
- outputs/signal_outcomes_report.md is generated.
- No generated outputs are tracked by Git.
- No API key leakage.
- No brokerage/order automation.
- No unsupported options inference.
- Existing production verifier still passes before commit.

## Safety Boundary

Research-only. Not financial advice. Model output requires human review.
