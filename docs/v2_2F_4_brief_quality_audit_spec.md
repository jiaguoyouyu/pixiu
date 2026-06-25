# Pixiu v2.2F.4 Brief Quality Audit - Spec

## Goal

Add a deterministic quality audit for the existing Pixiu Daily Brief. The audit must make the brief easier to trust or reject without changing ranking, scoring, provider behavior, schemas, universes, or action-bias semantics.

## Scope

Add:

- a local-only quality report generator
- a shell verifier for F.4
- documentation for the generated quality report
- minimal Daily Brief runner wiring for `quality` and `quality-verify`
- focused fixture-based regression tests

## Inputs

Required local artifacts:

```text
outputs/daily_investment_scores.csv
outputs/expanded_daily_investment_scores.csv
outputs/daily_brief_report.md
outputs/action_bias_drift_report.md
outputs/signal_outcomes.csv
outputs/signal_outcomes_report.md
```

Optional local evidence:

```text
outputs/logs/pixiu-production-*.log
git status --short
```

The generator must not call providers, private accounts, paid APIs, brokers, or the network.

## Output

Generated report:

```text
outputs/daily_brief_quality_report.md
```

The report is ignored by Git through the existing `outputs/` ignore rule.

## Verdict Semantics

The final verdict is exactly one of:

- `USE`
- `REVIEW CAREFULLY`
- `DO NOT USE`

Verdict rules:

- `DO NOT USE`: at least one hard failure exists.
- `REVIEW CAREFULLY`: no hard failures exist, but at least one warning exists.
- `USE`: no hard failures and no warnings exist.

Hard failures include:

- missing required artifact
- stale daily score, Daily Brief, or action-bias drift artifact
- default score rows below `MIN_DEFAULT_SCORE_ROWS`
- expanded score rows below `MIN_EXPANDED_SCORE_ROWS`
- Daily Brief top candidate mismatch
- missing required Daily Brief safety or review section
- duplicate production groups reported by existing drift evidence
- non-zero latest production run final exit status when a production log is available
- missing or invalid signal-outcome artifact

Warnings include:

- repository has tracked or untracked changes; this is evidence only and must not make verification fail by itself
- non-zero expanded-universe data-gap ratio that is below hard-failure conditions
- incomplete signal-outcome coverage for current top candidates
- production log unavailable while drift evidence is otherwise clean

## Centralized Operational Thresholds

```text
MAX_ARTIFACT_AGE_DAYS = 1
MIN_DEFAULT_SCORE_ROWS = 38
MIN_EXPANDED_SCORE_ROWS = 100
TOP_CANDIDATE_LIMIT = 10
```

These are operational and data-quality thresholds. They do not encode investment recommendations.

## Data-Gap Semantics

The audit uses existing expanded-universe fields and labels:

- `action_bias == "Data Gap Review"`
- `confidence` containing `Low`
- `data_quality_score < 70`
- material gap markers in `primary_reason` or `risk_flags`

The existing expanded-mode phrase `options analysis unavailable` is not counted as a material data gap by itself because expanded mode intentionally marks options unavailable.

## Signal-Outcome Coverage Semantics

The audit reads existing signal-outcome rows and uses `outcome_status`.

- Missing outcome artifacts or no outcome rows are hard failures.
- Old signal-outcome artifact modification dates are evidence only, not hard freshness failures.
- Non-`ok` outcome rows are hard failures.
- Top daily candidates without an outcome row are warnings, because existing outcome tracking is sample/local-history based and does not promise full coverage.

## Non-Goals

Do not add:

- provider/API integration
- brokerage connection
- order generation or placement
- automated trading
- credential handling
- schema changes
- ranking or scoring changes
- new financial thresholds
