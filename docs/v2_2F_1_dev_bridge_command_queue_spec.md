# Pixiu v2.2F.1 Dev Bridge Command Queue / Clipboard Bundle — Spec

## Goal

Add a local command queue and AI-paste bundle workflow on top of the v2.2F Local Dev Loop Bridge.

## Scope

This feature adds:

- JSON command queue template
- queue classifier
- queue executor
- per-command local logs
- AI_BUNDLE.txt summary
- latest-log bundle command
- optional local macOS clipboard copy with pbcopy
- targeted verifier

## Boundaries

This remains local-only and research/dev-loop-only.

Do not add:

- brokerage connection
- order execution
- automated trading
- credential storage
- provider/API integration
- private website scraping
- automatic Level 3 execution

## Safety Model

Each command has a declared level and an inferred level.

The effective level is the stricter of the two.

Level 3 queues are refused unless `--yes-level3` is passed after explicit user approval.

## Generated Outputs

Generated logs live under:

```text
outputs/dev_loop_queue/
```

Generated outputs must remain ignored/untracked.

## Acceptance Criteria

- Queue script compiles.
- Runner and verifier shell syntax pass.
- Template exists.
- Status works.
- Classify works.
- Level 1 queue executes.
- AI_BUNDLE.txt is created.
- Latest-log bundle works.
- Level 3 queue is refused without `--yes-level3`.
- Generated logs are ignored or clean.
- No generated/sensitive files are tracked.
