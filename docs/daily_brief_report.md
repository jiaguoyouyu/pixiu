# Pixiu Daily Brief Report

## Purpose

The daily brief converts Pixiu daily queue outputs into a concise Markdown report for human review.

## Run

```bash
./scripts/run_pixiu_daily_brief.sh
```

This runs the v2.2F.2 daily queue first, then generates:

```text
outputs/daily_brief_report.md
```

## Generate Brief Only

If daily queue outputs already exist:

```bash
./scripts/run_pixiu_daily_brief.sh brief-only
```

## Verify

```bash
./scripts/run_pixiu_daily_brief.sh verify
```

## Safety

The brief is research-only.

It does not:

- connect to brokerage
- place orders
- automate trading
- store credentials
- add provider/API integration
- change schema
- change scoring formulas

The report is not financial advice and requires human review.
