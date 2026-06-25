# Pixiu Daily Brief Quality Report

## Purpose

The quality report audits whether the latest local Daily Brief artifacts are fresh, internally consistent, and useful for human review.

## Run

```bash
./scripts/run_pixiu_daily_brief.sh quality
```

This generates:

```text
outputs/daily_brief_quality_report.md
```

## Verify

```bash
./scripts/run_pixiu_daily_brief.sh quality-verify
```

## Verdicts

- `USE`: no hard failures and no warnings.
- `REVIEW CAREFULLY`: no hard failures, but at least one warning.
- `DO NOT USE`: at least one hard failure.

Missing or stale required daily artifacts always prevent `USE`.

## Safety

The audit is local-only and research-only.

It does not:

- connect to providers
- connect to brokerage
- place or generate orders
- automate trading
- store credentials
- change schemas
- change scoring formulas
