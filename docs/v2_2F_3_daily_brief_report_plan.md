# Pixiu v2.2F.3 Daily Brief Report — Plan

## Phase 1 — Additive Files

Create:

```text
scripts/generate_daily_brief_report.py
scripts/run_pixiu_daily_brief.sh
scripts/verify_pixiu_daily_brief.sh
docs/daily_brief_report.md
docs/v2_2F_3_daily_brief_report_spec.md
docs/v2_2F_3_daily_brief_report_plan.md
```

## Phase 2 — Verification

Run:

```bash
./scripts/verify_pixiu_daily_brief.sh
./scripts/verify_pixiu_dev_queue.sh
./scripts/verify_pixiu_dev_bridge.sh
./scripts/verify_signal_outcomes.sh
```

## Phase 3 — Stop Gate

Stop before:

```text
commit
push
snapshot
provider/API integration
schema/migration changes
scoring formula changes
```
