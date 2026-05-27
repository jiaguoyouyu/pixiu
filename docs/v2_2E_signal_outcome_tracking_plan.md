# Pixiu v2.2E Signal Outcome Tracking / Forward Return Review — IMPLEMENTATION PLAN

## Phase 1 — Scaffold

1. Add local price history template.
2. Add outcome tracking script.
3. Add targeted verifier.
4. Generate sample outputs from local data only.
5. Confirm generated outputs are ignored.

## Phase 2 — Warehouse Integration Later

Initial v2.2E should not modify DuckDB schema unless explicitly approved.
If later needed, add a signal_outcomes table only after user confirmation.

## Files Expected to Add

- data/manual_price_history.template.csv
- scripts/track_signal_outcomes.py
- scripts/verify_signal_outcomes.sh
- docs/signal_outcome_tracking.md
- docs/v2_2E_signal_outcome_tracking_spec.md
- docs/v2_2E_signal_outcome_tracking_plan.md

## Generated Outputs

- outputs/signal_outcomes.csv
- outputs/signal_outcomes_report.md

## Verifiers

Targeted:
- ./scripts/verify_signal_outcomes.sh

Regression before commit:
- ./scripts/verify_daily_production_research.sh

## Level 3 Actions Requiring User Confirmation

- commit
- push
- snapshot
- DuckDB schema changes
- scoring formula changes
- provider/API integration
- deleting files

## Stop Condition

Stop after targeted verifier result and ask for validation before commit/push/snapshot.
