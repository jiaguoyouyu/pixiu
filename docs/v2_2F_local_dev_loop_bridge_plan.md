# Pixiu v2.2F Local Dev Loop Bridge — IMPLEMENTATION PLAN

## Phase 1 — Scaffold

1. Add local command packet template.
2. Add pixiu_dev_bridge.py.
3. Add run_pixiu_dev_bridge.sh.
4. Add verify_pixiu_dev_bridge.sh.
5. Add docs/local_dev_loop_bridge.md.
6. Verify Level 1 packet execution.
7. Verify Level 3 packet refusal without explicit approval.

## Phase 2 — Future Expansion

Possible future work, not v2.2F initial scope:

- local clipboard bundle generation
- automatic latest-log summarization
- optional external AI API bridge only after explicit user approval
- richer command queue
- interactive TUI

## Level 3 YES Required

- commit
- push
- snapshot
- delete files
- DuckDB/schema changes
- scoring formula changes
- provider/API integration
- paid data integration
- .gitignore tracking rule changes
- brokerage/trading/order/credential boundary changes

## Required Verification

Targeted:
- ./scripts/verify_pixiu_dev_bridge.sh

Regression:
- ./scripts/verify_signal_outcomes.sh
- ./scripts/verify_daily_production_research.sh

## Stop Condition

Stop before commit/push/snapshot and request user YES.
