# Pixiu v2.2F.2 Daily Queue Presets — Plan

## Phase 1 — Additive Preset Files

Create:

```text
templates/pixiu_daily_research_queue.template.json
scripts/run_pixiu_daily_queue.sh
scripts/verify_pixiu_daily_queue.sh
docs/daily_queue_presets.md
docs/v2_2F_2_daily_queue_presets_spec.md
docs/v2_2F_2_daily_queue_presets_plan.md
```

## Phase 2 — Verification

Run:

```bash
./scripts/verify_pixiu_daily_queue.sh
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
