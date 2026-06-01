# Pixiu v2.2F.3 Daily Brief Report — Spec

## Goal

Generate a concise daily research brief from the v2.2F.2 daily queue outputs.

The target daily command is:

```bash
./scripts/run_pixiu_daily_brief.sh
```

## Scope

Add:

- daily brief Markdown generator
- daily brief runner
- daily brief verifier
- documentation/spec/plan

## Inputs

The generator reads local Pixiu outputs:

```text
outputs/daily_investment_scores.csv
outputs/expanded_daily_investment_scores.csv
outputs/action_bias_drift_report.md
outputs/signal_outcomes_report.md
```

## Outputs

Generated report:

```text
outputs/daily_brief_report.md
```

The report is local-only and generated output remains ignored by Git.

## Non-goals

Do not add:

- provider/API integration
- brokerage connection
- order execution
- automated trading
- credential storage
- schema/migration changes
- scoring formula changes
- financial advice or trade instructions

## Required Report Sections

- research-only safety banner
- executive summary
- default watchlist top candidates
- expanded-universe top candidates
- action-bias distribution
- risk/data-quality notes
- output file references
- next human review checklist

## Acceptance Criteria

- generator compiles
- runner shell syntax passes
- verifier shell syntax passes
- docs/spec/plan exist
- runner can execute daily queue and generate report
- report exists
- report includes research-only disclaimer
- report includes watchlist and expanded-universe sections
- generated report/logs remain ignored or clean
- no generated/sensitive files are tracked
