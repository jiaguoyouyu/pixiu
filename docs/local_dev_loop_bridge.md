# Pixiu Local Dev Loop Bridge

This module provides local-only helper utilities for Pixiu terminal automation.

It does not connect to ChatGPT directly and does not transmit data externally.

## Commands

Status:

python3 scripts/pixiu_dev_bridge.py status

Classify a command packet:

python3 scripts/pixiu_dev_bridge.py classify --packet templates/pixiu_command_packet.template.json

Execute a safe packet:

python3 scripts/pixiu_dev_bridge.py execute --packet templates/pixiu_command_packet.template.json

## Level 3 Gate

Level 3 packets are refused unless explicitly run with:

--yes-level3

Level 3 includes commit, push, snapshot, delete, schema changes, scoring formula changes, provider/API integration, and brokerage/trading/order/credential boundary changes.

## Boundary

Research-only. Human approval is required for Level 3. No brokerage connection. No orders. No automated trading. No credential storage.
