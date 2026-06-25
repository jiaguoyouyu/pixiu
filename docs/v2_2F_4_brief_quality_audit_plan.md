# Pixiu v2.2F.4 Brief Quality Audit - Plan

## Phase 1 - Additive Files

Create:

```text
scripts/generate_daily_brief_quality_report.py
scripts/verify_pixiu_daily_brief_quality.sh
docs/daily_brief_quality_report.md
docs/v2_2F_4_brief_quality_audit_spec.md
docs/v2_2F_4_brief_quality_audit_plan.md
tests/test_daily_brief_quality_report.py
```

Update:

```text
scripts/run_pixiu_daily_brief.sh
```

## Phase 2 - Quality Dimensions

The audit reads existing local artifacts only:

```text
outputs/daily_investment_scores.csv
outputs/expanded_daily_investment_scores.csv
outputs/daily_brief_report.md
outputs/action_bias_drift_report.md
outputs/signal_outcomes.csv
outputs/signal_outcomes_report.md
outputs/logs/pixiu-production-*.log
```

It reports:

- freshness of required daily artifacts
- row-count sanity for default and expanded score CSVs
- repository cleanliness as evidence only
- duplicate-production and production run-status evidence
- top-candidate consistency between score CSVs and the Daily Brief
- expanded-universe data-gap ratio using existing action-bias and data-quality semantics
- missing signal-outcome coverage using existing signal outcome rows and statuses
- Daily Brief usefulness checks for required sections and safety content
- final verdict: `USE`, `REVIEW CAREFULLY`, or `DO NOT USE`

## Phase 3 - Operational Thresholds

Centralize conservative operational thresholds in the generator:

```text
MAX_ARTIFACT_AGE_DAYS = 1
MIN_DEFAULT_SCORE_ROWS = 38
MIN_EXPANDED_SCORE_ROWS = 100
TOP_CANDIDATE_LIMIT = 10
```

These thresholds are not investment thresholds. The row minimums come from existing daily-ranker and warehouse verifier expectations. Freshness is an operational daily-artifact check.

## Phase 4 - Verification

Run:

```bash
python3 -m unittest tests/test_daily_brief_quality_report.py
env PYTHONPYCACHEPREFIX=/private/tmp/pixiu_quality_pycache python3 -m py_compile scripts/generate_daily_brief_quality_report.py scripts/generate_daily_brief_report.py
bash -n scripts/verify_pixiu_daily_brief_quality.sh
bash -n scripts/run_pixiu_daily_brief.sh
./scripts/verify_pixiu_daily_brief_quality.sh
./scripts/run_pixiu_daily_brief.sh quality
./scripts/run_pixiu_daily_brief.sh quality-verify
./scripts/verify_pixiu_daily_brief.sh
git diff --check
git status --short
git ls-files | grep -E "(^outputs/|^backups/|^snapshots/|\\.duckdb|\\.env|\\.tar\\.gz|\\.log$)"
```

Run `./scripts/verify_pixiu_daily_queue.sh` only if the daily brief wiring changes daily queue execution behavior.

## Phase 5 - Stop Gate

Stop before:

```text
commit
push
deploy
provider/API access
private-account access
broker connection
order generation
order placement
real-capital action
schema or ranking/scoring changes
```
