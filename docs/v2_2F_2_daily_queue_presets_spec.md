# Pixiu v2.2F.2 Daily Queue Presets — Spec

## Goal

Turn the proven v2.2F.1 daily research workflow queue into reusable local presets.

The goal is one-command daily usage:

```bash
./scripts/run_pixiu_daily_queue.sh
```

## Scope

Add:

- reusable daily research queue template
- daily queue runner wrapper
- daily queue verifier
- documentation for queue presets

## Non-goals

Do not add:

- provider/API integration
- brokerage connection
- order execution
- automated trading
- credential storage
- schema/migration changes
- scoring formula changes
- commit/push/snapshot automation

## Daily Preset Commands

The default daily preset runs:

1. queue status
2. daily production research
3. signal outcomes sample tracking
4. production latest query
5. production action-bias summary query
6. action-bias drift query
7. duplicate production check
8. git clean check

## Safety Classification

The preset is expected to classify as:

```text
max_level: 2
requires_yes_level3: no
```

## Generated Outputs

Generated logs remain under:

```text
outputs/dev_loop_queue/
```

Generated outputs must remain ignored/untracked.

## Acceptance Criteria

- daily queue template exists and is valid JSON
- runner shell syntax passes
- verifier shell syntax passes
- daily queue classifies as Level 2
- no Level 3 approval is required
- dry-run mode works
- actual daily queue execution works
- latest AI bundle is created
- final git status is clean or only intended tracked files are changed during implementation
- generated/sensitive files are not tracked
