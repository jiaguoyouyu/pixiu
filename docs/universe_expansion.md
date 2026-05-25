# Index Universe Expansion

v2.1 expands `data/index_universe.csv` from a small manually seeded universe into a broader local research universe.

Required notices:

- Not financial advice
- Model output requires human review
- Data quality may affect results
- Research-only. No brokerage connection, no orders, no API key persistence, and no credential storage.

## Scope

The universe update merges:

- Public Wikipedia tables when `--public-bootstrap` is used.
- S&P 500 constituents from FMP.
- Nasdaq-100 or Nasdaq constituent endpoint rows from FMP.
- Dow Jones Industrial Average constituents from FMP.
- Optional local `data/manual_index_constituents.csv` rows.
- Existing local `data/watchlist.csv` tickers.
- Existing `data/index_universe.csv` rows.

Tickers are de-duplicated and index memberships are preserved.

## Command

Set `FMP_API_KEY` in the current terminal only:

```bash
export FMP_API_KEY="..."
./scripts/run_universe_update.sh
```

Do not store the key in project files.

For the v2.1B no-key public bootstrap:

```bash
./scripts/run_universe_update.sh --public-bootstrap
```

This fetches public Wikipedia constituent tables, generates `data/manual_index_constituents.csv`, validates the merged universe, and overwrites `data/index_universe.csv` only if validation passes.

## Verification

```bash
./scripts/verify_universe_update.sh
```

The verifier checks compilation, shell syntax, CSV output, required columns, material ticker-count expansion, membership coverage, API key leakage markers, and the existing v2.0 warehouse verifier.

## Output Files

- `data/index_universe.csv`
- `data/index_universe_snapshot_YYYYMMDD-HHMMSS.csv`
- `data/manual_index_constituents.csv`
- `data/manual_index_constituents.template.csv`
- `outputs/universe_expansion_report.md`
- `outputs/universe_provider_capability_report.md`

## Columns

- `ticker`
- `company_name`
- `index_memberships`
- `sector`
- `industry`
- `theme`
- `source`
- `universe_tier`
- `active`
- `last_updated`
- `source_updated_at` compatibility alias for the existing earnings radar

## Missing API Key Behavior

If `FMP_API_KEY` is missing, the updater does not overwrite `data/index_universe.csv`. It writes a report explaining that the provider key is missing and exits nonzero.

## Provider Permission Failures

Some FMP plans may not allow index constituent endpoints. If FMP returns `402`, `403`, or zero usable rows, the updater does not overwrite `data/index_universe.csv`. It writes:

- `outputs/universe_expansion_report.md`
- `outputs/universe_provider_capability_report.md`

The provider capability report records each endpoint with:

- `provider_name`
- `endpoint_label`
- `http_status`
- `rows_returned`
- `error_message_redacted`
- `likely_cause`

Likely causes are `ok`, `missing_key`, `unauthorized`, `payment_required`, `empty`, or `unknown`.

## Manual Constituents Import

Optional future fallback path:

```text
data/manual_index_constituents.csv
```

If this file exists, the updater validates it and merges valid rows with the existing local universe. This file is not required for normal FMP-based operation.

Template:

```text
data/manual_index_constituents.template.csv
```

Accepted columns:

- `ticker` required
- `company_name` required
- `index_memberships` required; semicolon-separated, for example `S&P 500; Nasdaq-100`
- `sector` optional
- `industry` optional
- `theme` optional; the updater can infer a broad theme when missing
- `source` optional
- `universe_tier` optional
- `active` optional
- `last_updated` optional
- `source_updated_at` optional compatibility alias

Manual import rules:

- Do not invent constituents.
- Use only verified index membership sources.
- Keep one row per ticker where practical.
- Do not include API keys, private account data, or brokerage information.

## Public Bootstrap Validation

The updater overwrites `data/index_universe.csv` only when:

- At least 400 unique tickers are present.
- Required columns exist.
- S&P 500 membership is present.
- Nasdaq-100 membership is present.
- Dow 30 membership is present.
- Tickers look valid.
- No obvious HTML garbage rows are present.

If validation fails, the prior universe remains untouched and diagnostics are written to the reports.

## What Is Intentionally Not Included

- No Fiscal.ai integration.
- No Quartr integration.
- No Koyfin automation.
- No Koyfin scraping or login automation.
- No brokerage connection.
- No trading automation.
- No API key persistence.
