# Pixiu Signal Outcome Tracking

This module measures forward returns after Pixiu research signals using local price-history CSV files.

## Command

python3 scripts/track_signal_outcomes.py --allow-template

## Local Data Source

data/manual_price_history.csv

Template:

data/manual_price_history.template.csv

Required columns:

ticker,date,close,source

## Outputs

outputs/signal_outcomes.csv
outputs/signal_outcomes_report.md

Generated outputs are ignored by Git.

## Boundary

Research-only. Not financial advice. No brokerage connection. No orders. No automated trading. No credential storage. No live provider dependency in the initial version.
