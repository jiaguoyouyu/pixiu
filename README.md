# Pixiu

Research-only automated ranking engine for a stock/ETF watchlist.

GitHub repository name recommendation: `pixiu`.

Required notices:

- Not financial advice
- Model output requires human review
- Data quality may affect results

The tool does not place trades, send brokerage orders, scrape private accounts, use margin, execute options, or store credentials. It only reads a local CSV, optionally enriches it with public Nasdaq historical/summary/financial data with Yahoo Finance as a fallback, and writes research outputs.

## Files

- `scripts/pixiu.py`: dependency-free Python ranker and main entrypoint.
- `scripts/investment_ranker.py`: backward-compatible wrapper for existing automations.
- `data/watchlist.csv`: starter watchlist. You can add columns from the schema below.
- `outputs/daily_investment_scores.csv`: generated ranked score table.
- `outputs/daily_investment_report.md`: generated daily report.
- `README_investment_ranker.md`: this guide.

The generated score CSV includes `cad_alternative` and `cad_note` columns. These are static Canadian-listed CDR/ETF mapping hints for CAD-account review, not execution instructions.

## Run

```bash
python3 scripts/pixiu.py
```

Offline/local-only mode:

```bash
python3 scripts/pixiu.py --offline
```

## Daily usage

Run the daily report with one command:

```bash
./scripts/run_daily_report.sh
```

Outputs are saved to:

- `outputs/daily_investment_scores.csv`
- `outputs/daily_investment_report.md`

The daily runner prints the run timestamp, project root, ranker exit code, strategy counts, top 20 ranked tickers with CAD alternatives, and output file locations. On macOS it copies the final summary to the clipboard with `pbcopy` when available; if clipboard copy fails, the summary is still printed normally.

Strategy bucket meanings:

- `Buy/Add`: strongest bucket; still requires human review before any staged action.
- `ETF Trend Candidate`: constructive ETF trend candidate for staggered CAD-account allocation review.
- `Ranked Buy Candidate`: non-ETF candidate eligible for human review and possible small starter sizing.
- `High-Quality Watch`: quality screens well, but valuation, catalyst, trend, risk, or missing data does not justify immediate buying.
- `Pullback Buy`: no entry now; wait for pullback or consolidation.
- `Defined-Risk Options`: defined-risk options framework only; no naked options.
- `Avoid Chase`: do not chase current price; wait or review later.
- `Avoid`: no current research setup.

Every output requires human review. Not financial advice. Model output requires human review. Data quality may affect results.

## Weekly Earnings Radar

Run the watchlist-only weekly earnings radar with one command:

```bash
./scripts/run_weekly_earnings_report.sh
```

Outputs are saved to:

- `outputs/weekly_earnings_calendar.csv`
- `outputs/weekly_earnings_report.md`

The weekly radar scans only `data/watchlist.csv`, attempts public per-ticker earnings-date enrichment, and includes every watchlist ticker in the CSV. Missing earnings dates, market cap, or momentum fields are marked as `N/A` and called out in `data_status`; missing data is never silently fabricated.

Importance buckets:

- `Critical Market-Moving Earnings`: highest importance score, usually mega-cap, AI, semiconductor, or high-index-impact earnings.
- `High Importance`: important watchlist earnings with strong theme, size, momentum, or index-impact characteristics.
- `Medium Importance`: relevant watchlist earnings but less likely to dominate market or ETF risk.
- `Low Importance`: lower expected market impact based on available public data.
- `Data Gap / Watch`: no confirmed earnings date from the public per-ticker source; verify manually.

Weekly outputs are research-only. Verify earnings dates in the broker or company investor relations page before making any decision. Do not buy solely because earnings are upcoming. Avoid oversized positions before earnings, avoid naked options, check implied move if trading options, and re-run the Pixiu after earnings.

### Manual earnings override

Use `data/earnings_overrides.csv` when public earnings sources are rate-limited or missing a known date. The weekly radar reads this file before public Yahoo/Nasdaq fallback data.

Expected columns:

`ticker`, `company_name`, `earnings_date`, `report_timing`, `source`, `source_note`, `updated_at`

Example row:

```csv
NVDA,NVIDIA,2026-05-20,after_market,company_ir,Verify from NVIDIA Investor Relations,2026-05-20
```

Validation rules:

- `ticker` is required and normalized to uppercase.
- `earnings_date` and `updated_at` must use `YYYY-MM-DD`.
- `report_timing` must be one of `before_market`, `after_market`, `during_market`, or `unknown`.
- `source` must be one of `company_ir`, `broker`, `nasdaq`, `yahoo`, `marketwatch`, or `manual`.

To update it, add or replace one row per ticker, then run:

```bash
./scripts/run_weekly_earnings_report.sh
```

Manual overrides are still research inputs, not execution instructions. Verify every override date and timing in the broker or company investor relations page before trading. Stale or invalid rows are ignored and surfaced in the weekly report.

## Index Universe Weekly Earnings Radar

v1.5 provider-calendar mode is now enabled for the index universe radar.

- Keep using `./scripts/run_index_earnings_report.sh`.
- Earnings calendar provider priority: `FMP_API_KEY` first, then `FINNHUB_API_KEY` fallback.
- API keys are read only from environment variables.
- Do not write API keys into code, README files, CSV files, reports, shell snippets, or committed artifacts.
- With no provider key, the command still succeeds, makes no provider network call, and reports: `No earnings provider key found. Set FMP_API_KEY or FINNHUB_API_KEY.`
- `data/index_universe_overrides.csv` is now emergency fallback only, not the primary workflow.
- Provider rows win over manual overrides.
- If the provider succeeds but has no event for a ticker, the ticker remains `Data Gap / Watch`.
- Expanded CSV fields: `eps_estimate`, `revenue_estimate`, `provider`, `earnings_date_source`, `provider_status`.
- v1.6 adds a `Daily Earnings Brief` section to translate confirmed earnings and high-impact data gaps into research actions.
- v1.6 adds an automated verification harness:

```bash
./scripts/verify_index_earnings_pipeline.sh
```

The verification harness runs a no-key provider test, checks required report sections and CSV fields, scans report/CSV output for likely API key leakage markers, and prints a compact PASS/FAIL summary.

v1.6.1 makes the verification harness non-destructive by default: it preserves existing `outputs/index_weekly_earnings_calendar.csv` and `outputs/index_weekly_earnings_report.md` while testing no-key behavior, then restores the original files before exiting.

Recommended daily order:

1. Export `FMP_API_KEY` in the current terminal, if available.
2. Run `./scripts/run_index_earnings_report.sh`.
3. Run `./scripts/verify_index_earnings_pipeline.sh`.
4. Use the restored output files; after verification they remain the live report outputs from step 2.

Run the index universe earnings radar with one command:

```bash
./scripts/run_index_earnings_report.sh
```

Outputs are saved to:

- `outputs/index_weekly_earnings_calendar.csv`
- `outputs/index_weekly_earnings_report.md`

The index radar still uses the local seeded index universe, but earnings dates now come from provider calendar APIs when provider keys are available. If no provider key exists or provider fetching fails, `data/index_universe_overrides.csv` may be used as emergency fallback:

- `data/index_universe.csv`: starter high-impact index universe.
- `data/index_universe_overrides.csv`: manual earnings-date overrides.

To update `data/index_universe.csv`, add or edit rows with:

`ticker`, `company_name`, `index_memberships`, `sector`, `theme`, `source`, `source_updated_at`

Use semicolon-separated index memberships, for example:

```csv
AAPL,Apple,Nasdaq-100; S&P 500; Dow 30,Information Technology,Mega-cap Tech,manual_review,2026-05-21
```

To update `data/index_universe_overrides.csv`, add one row per verified earnings event:

```csv
NVDA,NVIDIA,2026-05-20,after_market,company_ir,Verify from NVIDIA Investor Relations,2026-05-20
```

Allowed `report_timing` values are `before_market`, `after_market`, `during_market`, and `unknown`. Allowed `source` values are `company_ir`, `broker`, `nasdaq`, `yahoo`, `marketwatch`, and `manual`.

All earnings dates require human verification from the broker or company investor relations page. The index radar is research-only, does not place orders, does not connect to brokerage accounts, reads provider API keys only from environment variables, does not store API keys, and does not recommend naked options.

`Data Gap / Watch` means the ticker is high-impact enough to prioritize for manual review, but there is no confirmed provider earnings date in the current look-ahead window. It is not a confirmed earnings event. The Markdown report separates confirmed upcoming earnings from high-impact data gaps so no `N/A` earnings-date row is presented as a confirmed top market-moving earnings event.

## Research Desk Exports

v1.9 adds a local-only research desk export layer for daily manual review:

```bash
./scripts/run_research_desk_exports.sh
```

Generated files:

- `outputs/koyfin_watchlists.csv`
- `outputs/koyfin_watchlists.md`
- `outputs/fiscal_ai_research_questions.md`
- `outputs/daily_wall_street_desk_brief.md`
- `outputs/research_desk_tasks.csv`

The Koyfin files are manual watchlist references/import aids only. The project does not scrape Koyfin and does not automate Koyfin login.

The Fiscal.ai file is a manual analyst prompt queue only. Fiscal.ai API integration remains disabled/stubbed unless explicitly requested later; no API key is required or stored.

Verify the research desk exports with:

```bash
./scripts/verify_research_desk_exports.sh
```

The verifier compiles the generator, runs the research desk runner, checks expected Markdown headings and CSV columns, scans generated outputs for likely API key leakage markers, and confirms the existing v1.6.1 index earnings verifier still passes.

## Research Warehouse

v2.0 adds a minimal local DuckDB historical research warehouse:

```bash
./scripts/run_research_warehouse_update.sh
./scripts/verify_research_warehouse.sh
python3 scripts/query_research_warehouse.py summary
```

The warehouse stores daily score rows, index earnings calendar rows, research desk tasks, and Koyfin manual-watchlist export rows in `data/pixiu.duckdb`.

Documentation:

- `docs/research_warehouse.md`

If the DuckDB Python package is missing, install it manually:

```bash
pip install duckdb
```

The warehouse is research-only. It does not connect to brokerages, place orders, automate Koyfin, call Fiscal.ai, call Quartr, or store credentials/API keys.

## Optional Watchlist Columns

The script accepts any subset of these columns and marks unavailable fields as missing/neutral rather than fabricating them:

`ticker`, `name`, `sector`, `price`, `market_cap`, `PE`, `forward_PE`, `PS`, `EV_to_sales`, `FCF_yield`, `revenue_growth`, `gross_margin`, `operating_margin`, `net_debt_to_ebitda`, `5D return`, `20D return`, `63D return`, `250D return`, `volume`, `average_volume`, `RSI_14`, `ATR_14`, `MA20`, `MA50`, `MA200`, `IV_rank`, `IV_minus_HV`, `earnings_date`, `analyst_revision`, `news_catalyst`.

Local CSV values take priority. Public price history and financial statement data are used only when available. Missing values are reported as data gaps and usually receive neutral component scores.

## CAD Alternatives

The report includes a static CAD alternatives section for top-ranked names. CDR mappings, such as `GOOGL -> GOOG.TO`, are not identical to the U.S. underlying and must be verified for liquidity, spread, CDR ratio, and hedging behavior. ETF mappings are alternatives, not exact clones. Indirect mappings, such as `TSM -> CHPS.TO / XCHP.TO`, are marked as indirect exposure only. Missing mappings are reported as `No clear direct CAD mapping found; verify manually before trading.`

## Scoring Model

The engine implements the requested formulas:

- `MarketGateScore = 0.30 * SPY_Trend + 0.25 * QQQ_Trend + 0.20 * SMH_Trend + 0.10 * Breadth + 0.10 * Volatility + 0.05 * Rates`
- `QualityScore = 0.30 * FCF_Yield_Score + 0.20 * Revenue_Growth_Score + 0.15 * Gross_Margin_Score + 0.15 * Operating_Margin_Score + 0.10 * Balance_Sheet_Score + 0.10 * Buyback_or_Dilution_Score`
- `ValuationScore = 0.35 * FCF_Yield_Percentile + 0.20 * EV_to_Sales_Inverse + 0.20 * Forward_PE_Inverse + 0.15 * PEG_Inverse + 0.10 * Historical_Valuation_Discount`
- `TrendScore = 0.25 * Price_Above_MA20 + 0.25 * MA20_Above_MA50 + 0.20 * MA50_Above_MA200 + 0.15 * Relative_Strength_20D + 0.15 * Volume_Confirmation`
- `OptionsScore = 0.35 * IV_Rank + 0.25 * IV_minus_RealizedVol + 0.20 * Option_Liquidity + 0.10 * Skew_Edge + 0.10 * Support_Distance`
- `FinalScore = 0.20 * MarketGateScore + 0.20 * QualityScore + 0.15 * ValuationScore + 0.20 * TrendScore + 0.10 * CatalystScore + 0.10 * OptionsScore - 0.15 * RiskPenalty`

Risk penalties include overvaluation, overheat, earnings event risk, liquidity, drawdown, and gap/ATR risk. The overheat rules requested in the prompt are implemented directly.

## Strategy Rules

- `Buy/Add`: market score at least 60, final score at least 75, and risk penalty at most 20.
- `ETF Trend Candidate`: ETF ticker, market score at least 60, trend score at least 85, risk penalty at most 20, and final score at least 60. This means constructive ETF trend for staggered allocation review, not an automatic buy signal.
- `Ranked Buy Candidate`: non-ETF ticker, market score at least 60, final score at least 65, and risk penalty at most 20. This means eligible for human review and possible small staged entry, not an automatic buy signal.
- `High-Quality Watch`: quality score at least 70, final score at least 60, and risk penalty at most 30. This means quality is good but not enough for immediate buying.
- `Pullback Buy`: final score at least 60, trend score at least 70, and risk penalty at most 35. This means no entry now; wait for a pullback or consolidation.
- `Defined-Risk Options`: options score at least 70 and risk penalty at most 35.
- `Avoid Chase`: final score at least 55 and risk penalty at most 50. This means do not chase current price.
- Otherwise: `Avoid`.

Options outputs are defined-risk only. The report uses put credit spread frameworks, covered-call/call-credit-spread context for overextended names, max loss/gain/breakeven formulas, delta target, DTE target, and exit rules. It never recommends naked options.

## Verification

Each run verifies:

- CSV loads successfully.
- No missing ticker symbols.
- No NaN scores in final output.
- No strategy is generated without `risk_penalty`.
- No options strategy is naked.
- All outputs are saved.

The script prints the top 20 ranked tickers after saving the files.
