# Pixiu Terminal Automation Loop

Pixiu development uses a human-in-the-loop terminal automation workflow.

## Goal

Automated commands + automated local logging + AI validation + staged progress.

The user only confirms Level 3 checkpoints.

## Current Mode

1. AI provides terminal command.
2. User runs command locally.
3. runlog saves stdout/stderr/exit code/git status.
4. runlog copies result to clipboard.
5. User pastes result back to AI.
6. AI validates and provides next command.

## Future Mode

A local bridge may execute approved command blocks, collect runlog output, and return summaries to the AI conversation.

## Level 1 — Auto OK

- inspect
- git status
- log tail
- query commands
- Python compile
- shell syntax
- targeted verifier
- generated output ignore check

## Level 2 — Auto OK With Caution

- create backup
- write docs
- create templates
- add normal scripts
- run production regression
- generate reports

## Level 3 — User YES Required

- commit
- push
- snapshot
- delete files
- DuckDB/schema changes
- scoring formula changes
- provider/API integration
- paid data integration
- .gitignore tracking rule changes
- anything touching brokerage/trading/order/credential boundaries

## Required Safety Gates

- targeted verifier must pass before regression
- production regression must pass before commit
- blocked tracked file check must pass before commit/push
- generated/sensitive files must not be tracked
- no API keys or credentials in logs/code/docs
- no brokerage/order automation
- no unsupported options inference

## Standard Loop

inspect → backup → spec/plan → implement → targeted verify → regression verify → git hygiene → YES gate → commit → push → YES gate → snapshot → final checkpoint
