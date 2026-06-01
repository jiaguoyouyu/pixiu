# Pixiu v2.2F.1 Dev Bridge Command Queue / Clipboard Bundle — Plan

## Implementation

Create:

```text
scripts/pixiu_dev_queue.py
scripts/run_pixiu_dev_queue.sh
scripts/verify_pixiu_dev_queue.sh
templates/pixiu_command_queue.template.json
docs/dev_bridge_command_queue.md
docs/v2_2F_1_dev_bridge_command_queue_spec.md
docs/v2_2F_1_dev_bridge_command_queue_plan.md
```

## Verification

Run:

```bash
./scripts/verify_pixiu_dev_queue.sh
./scripts/verify_pixiu_dev_bridge.sh
./scripts/verify_signal_outcomes.sh
./scripts/verify_daily_production_research.sh
```

## Stop Gate

Stop before:

```text
commit
push
snapshot
schema changes
scoring formula changes
provider/API integration
```
