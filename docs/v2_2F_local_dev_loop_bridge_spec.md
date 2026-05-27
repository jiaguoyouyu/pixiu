# Pixiu v2.2F Local Dev Loop Bridge — SPEC

## Problem Statement

Pixiu development currently uses a semi-automatic loop:

AI gives terminal commands.
User runs commands locally.
runlog saves and copies results.
User pastes results back.
AI validates and provides the next command.

This is reliable but still copy/paste heavy. v2.2F should create local bridge helpers that reduce friction while preserving safety checkpoints.

## Goal

Create a local dev-loop bridge scaffold that standardizes:

- command packets
- execution logs
- latest-result summaries
- Level 1/2/3 safety classification
- YES gates for high-risk actions

## Non-Goals

- No direct ChatGPT control from Terminal.
- No browser automation.
- No API calls to OpenAI, Anthropic, GitHub, Koyfin, Fiscal.ai, Quartr, brokerage, or paid providers.
- No background autonomous agent that commits/pushes/snapshots without user YES.
- No credential storage.
- No order/trading automation.
- No DuckDB schema change.
- No scoring formula change.

## Local-Only Scope

All v2.2F helpers are local shell/Python utilities.

They may:

- create command packets in local files
- execute approved command packets
- write runlog-compatible logs
- summarize latest command results
- identify Level 3 actions and stop

They must not:

- transmit data externally
- execute Level 3 actions automatically
- bypass human approval

## Proposed Files

- scripts/pixiu_dev_bridge.py
- scripts/run_pixiu_dev_bridge.sh
- scripts/verify_pixiu_dev_bridge.sh
- templates/pixiu_command_packet.template.json
- docs/local_dev_loop_bridge.md
- docs/v2_2F_local_dev_loop_bridge_spec.md
- docs/v2_2F_local_dev_loop_bridge_plan.md

## Command Packet Concept

A command packet is local JSON with:

- label
- level
- purpose
- command
- requires_yes
- expected_outputs
- safety_notes

Level 3 packets must not execute unless explicitly passed with --yes-level3.

## Acceptance Criteria

- Bridge script compiles.
- Runner/verifier shell syntax passes.
- Template command packet exists.
- Bridge can print status.
- Bridge can classify command packets.
- Bridge refuses Level 3 packet without explicit yes flag.
- Bridge can execute Level 1 sample packet and create a local log summary.
- No generated/sensitive files are tracked.
- No credential leakage markers.
- No forbidden brokerage/order automation.
- Existing v2.2E targeted verifier still passes.
- Production regression still passes before commit.

## Safety Boundary

Research-only. Human approval required for Level 3. No brokerage connection. No orders. No automated trading. No credential storage.
