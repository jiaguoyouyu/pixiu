# Pixiu Research Warehouse

v2.0 adds a minimal DuckDB historical research warehouse for Pixiu outputs.

Required notices:

- Not financial advice
- Model output requires human review
- Data quality may affect results
- Research-only. No brokerage connection, no order execution, no credential storage, and no API key storage.

## Purpose

The warehouse persists daily Pixiu outputs so ranking buckets, earnings-risk signals, data-gap signals, CAD alternatives, and research desk tasks can be reviewed over time.

This is the foundation for future research validation. It is not a trading system and does not make direct buy/sell decisions.

## Why DuckDB

DuckDB is a small local analytical database that works well with CSV-style research outputs. It gives the project durable local history and SQL queries without needing a server, cloud database, pandas, or a brokerage connection.

## Database

Default path:

```bash
data/pixiu.duckdb
```

The database is local to this project.

## Tables

### warehouse_runs

One row per load run. Tracks `run_id`, `loaded_at`, row counts, status, and notes.

### daily_investment_scores

Stores rows from `outputs/daily_investment_scores.csv` with normalized fields:

- `run_id`
- `loaded_at`
- `source_file`
- `ticker`
- `company_name`
- `strategy`
- `final_score`
- `sector`
- `theme`
- `cad_alternative`
- `raw_json`

### index_weekly_earnings_calendar

Stores rows from `outputs/index_weekly_earnings_calendar.csv` with normalized provider/data-gap fields.

### research_desk_tasks

Stores rows from `outputs/research_desk_tasks.csv`.

### koyfin_watchlists

Stores rows from `outputs/koyfin_watchlists.csv`. Koyfin remains manual visual review only. This table is not Koyfin automation.

### warehouse_load_errors

Stores missing or malformed input issues for each warehouse run.

## Daily Update

Run:

```bash
./scripts/run_research_warehouse_update.sh
```

The runner:

1. Runs `./scripts/run_research_desk_exports.sh` if present.
2. Loads available CSV outputs into DuckDB.
3. Prints the latest warehouse summary.
4. Copies the summary to macOS clipboard when `pbcopy` works.

If `duckdb` is missing, install it manually:

```bash
pip install duckdb
```

The project does not auto-install dependencies.

## Query Commands

Latest run:

```bash
python3 scripts/query_research_warehouse.py latest-run
```

Summary:

```bash
python3 scripts/query_research_warehouse.py summary
```

Top ranked latest names:

```bash
python3 scripts/query_research_warehouse.py top-ranked
```

Current high-impact data gaps:

```bash
python3 scripts/query_research_warehouse.py data-gaps
```

Ticker history:

```bash
python3 scripts/query_research_warehouse.py ticker-history NVDA
```

Table counts:

```bash
python3 scripts/query_research_warehouse.py table-counts
```

## Verification

Run:

```bash
./scripts/verify_research_warehouse.sh
```

The verifier checks Python compilation, shell syntax, warehouse load execution, required tables, core queries, likely API key leakage markers, and forbidden brokerage/Koyfin/Fiscal.ai/Quartr automation markers.

## Intentionally Not Included

v2.0 intentionally does not include:

- Brokerage connections.
- Order execution.
- Direct buy/sell instructions.
- Koyfin import automation.
- Koyfin scraping.
- Koyfin login automation.
- Fiscal.ai API integration.
- Quartr API integration.
- API key, password, token, session, or cookie storage.

## Future Path

- v2.1 Fiscal.ai optional fundamentals integration.
- v2.2 Quartr post-earnings transcript intelligence.
- v2.3 performance attribution and bucket validation.
- v2.4 local dashboard.
