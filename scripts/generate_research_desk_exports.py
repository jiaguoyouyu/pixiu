#!/usr/bin/env python3
"""Generate local research desk exports from Pixiu outputs.

This script is intentionally local-only. It does not call Koyfin, Fiscal.ai,
brokerages, market data providers, or any private account endpoint.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

WATCHLIST_CSV = DATA_DIR / "watchlist.csv"
INDEX_UNIVERSE_CSV = DATA_DIR / "index_universe.csv"
DAILY_SCORES_CSV = OUTPUT_DIR / "daily_investment_scores.csv"
INDEX_EARNINGS_CSV = OUTPUT_DIR / "index_weekly_earnings_calendar.csv"

KOYFIN_CSV = OUTPUT_DIR / "koyfin_watchlists.csv"
KOYFIN_MD = OUTPUT_DIR / "koyfin_watchlists.md"
FISCAL_MD = OUTPUT_DIR / "fiscal_ai_research_questions.md"
DESK_BRIEF_MD = OUTPUT_DIR / "daily_wall_street_desk_brief.md"
TASKS_CSV = OUTPUT_DIR / "research_desk_tasks.csv"

NOTICES = [
    "Not financial advice",
    "Model output requires human review",
    "Data quality may affect results",
]

SECURITY_NOTE = (
    "Research-only. No brokerage connection, no orders, no private account "
    "access, no Koyfin scraping, no Koyfin login automation, no Fiscal.ai API "
    "call, and no naked options recommendation."
)

CONSTRUCTIVE_STRATEGIES = {
    "Buy/Add",
    "ETF Trend Candidate",
    "Ranked Buy Candidate",
    "High-Quality Watch",
    "Pullback Buy",
    "Defined-Risk Options",
}

AI_SEMI_MEGA_THEMES = {
    "AI Infrastructure",
    "Semiconductors",
    "Mega-cap Tech",
    "Cloud / Software",
    "Cybersecurity",
}

AI_SEMI_MEGA_TICKERS = {
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "AVGO",
    "AMD",
    "QCOM",
    "MU",
    "MRVL",
    "ASML",
    "ARM",
    "TSM",
    "INTC",
    "ORCL",
    "CRM",
    "NOW",
    "ADBE",
    "PLTR",
    "DDOG",
    "CRWD",
}


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Read a CSV into dictionaries and surface missing/invalid input warnings."""
    warnings: list[str] = []
    if not path.exists():
        return [], [f"Missing input: {path}"]

    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = [
                {str(key).strip(): (value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)
            ]
    except Exception as exc:  # pragma: no cover - defensive daily runner guard
        return [], [f"Could not read {path}: {exc}"]

    if not rows:
        warnings.append(f"No rows found in {path}")
    return rows, warnings


def normalize_ticker(value: str | None) -> str:
    return (value or "").strip().upper()


def first_value(row: dict[str, str], *keys: str, default: str = "N/A") -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return default


def safe_float(value: str | None, default: float = 0.0) -> float:
    try:
        if value in (None, "", "N/A"):
            return default
        return float(str(value).replace(",", ""))
    except ValueError:
        return default


def safe_int(value: str | None) -> int | None:
    try:
        if value in (None, "", "N/A"):
            return None
        return int(float(str(value).replace(",", "")))
    except ValueError:
        return None


def md_cell(value: object) -> str:
    text = str(value if value is not None else "N/A").replace("\n", " ").strip()
    return text.replace("|", "/")


def markdown_table(headers: list[str], rows: Iterable[dict[str, str]], limit: int | None = None) -> str:
    selected = list(rows)
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        return "- None.\n"

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(md_cell(row.get(header, "N/A")) for header in headers) + " |")
    return "\n".join(lines) + "\n"


def keyed_by_ticker(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    keyed: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = normalize_ticker(row.get("ticker"))
        if ticker and ticker not in keyed:
            keyed[ticker] = row
    return keyed


def sort_by_score(rows: Iterable[dict[str, str]], score_key: str) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (-safe_float(row.get(score_key)), normalize_ticker(row.get("ticker"))),
    )


def is_confirmed_next_7(row: dict[str, str]) -> bool:
    earnings_date = first_value(row, "earnings_date")
    days = safe_int(row.get("days_until_earnings"))
    status = first_value(row, "data_status", default="")
    return earnings_date != "N/A" and days is not None and 0 <= days <= 7 and "Data Gap" not in status


def is_high_impact_data_gap(row: dict[str, str]) -> bool:
    earnings_date = first_value(row, "earnings_date")
    status = first_value(row, "data_status", default="")
    score = safe_float(row.get("importance_score"))
    return (earnings_date == "N/A" or "Data Gap" in status) and score >= 65.0


def company_name_for(
    ticker: str,
    watchlist_by_ticker: dict[str, dict[str, str]],
    index_by_ticker: dict[str, dict[str, str]],
    daily_by_ticker: dict[str, dict[str, str]],
) -> str:
    for source in (index_by_ticker, watchlist_by_ticker, daily_by_ticker):
        row = source.get(ticker, {})
        name = first_value(row, "company_name", "name", default="")
        if name:
            return name
    return ticker


def sector_for(
    ticker: str,
    watchlist_by_ticker: dict[str, dict[str, str]],
    index_by_ticker: dict[str, dict[str, str]],
) -> str:
    for source in (index_by_ticker, watchlist_by_ticker):
        row = source.get(ticker, {})
        sector = first_value(row, "sector", default="")
        if sector:
            return sector
    return "N/A"


def theme_for(ticker: str, index_by_ticker: dict[str, dict[str, str]], daily_row: dict[str, str] | None = None) -> str:
    index_theme = first_value(index_by_ticker.get(ticker, {}), "theme", default="")
    if index_theme:
        return index_theme
    if daily_row:
        sector = first_value(daily_row, "sector", default="")
        if "semi" in sector.lower():
            return "Semiconductors"
        if "software" in sector.lower():
            return "Cloud / Software"
    return "Other"


def build_koyfin_rows(
    watchlist_rows: list[dict[str, str]],
    daily_rows: list[dict[str, str]],
    index_rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    watchlist_by_ticker = keyed_by_ticker(watchlist_rows)
    daily_by_ticker = keyed_by_ticker(daily_rows)
    index_by_ticker = keyed_by_ticker(index_rows)
    seen: set[tuple[str, str]] = set()
    koyfin_rows: list[dict[str, str]] = []

    def add_row(watchlist_name: str, ticker: str, source_row: dict[str, str], notes: str) -> None:
        ticker = normalize_ticker(ticker)
        if not ticker or (watchlist_name, ticker) in seen:
            return
        seen.add((watchlist_name, ticker))
        daily_row = daily_by_ticker.get(ticker, {})
        index_row = index_by_ticker.get(ticker, {})
        row = {
            "watchlist_name": watchlist_name,
            "ticker": ticker,
            "company_name": company_name_for(ticker, watchlist_by_ticker, index_by_ticker, daily_by_ticker),
            "sector": sector_for(ticker, watchlist_by_ticker, index_by_ticker),
            "theme": theme_for(ticker, index_by_ticker, daily_row),
            "strategy": first_value(daily_row, "strategy", default="N/A"),
            "final_score": first_value(daily_row, "final_score", default="N/A"),
            "importance_score": first_value(index_row or source_row, "importance_score", default="N/A"),
            "earnings_date": first_value(index_row or source_row, "earnings_date", default="N/A"),
            "days_until_earnings": first_value(index_row or source_row, "days_until_earnings", default="N/A"),
            "cad_alternative": first_value(daily_row, "cad_alternative", default=first_value(index_row, "cad_alternative")),
            "cad_note": first_value(daily_row, "cad_note", default=first_value(index_row, "cad_note")),
            "notes": notes,
        }
        koyfin_rows.append(row)

    top_ranked = [
        row
        for row in sort_by_score(daily_rows, "final_score")
        if first_value(row, "strategy", default="Avoid") in CONSTRUCTIVE_STRATEGIES
    ]
    confirmed_earnings = sort_by_score([row for row in index_rows if is_confirmed_next_7(row)], "importance_score")
    high_impact_gaps = sort_by_score([row for row in index_rows if is_high_impact_data_gap(row)], "importance_score")

    ai_focus_daily = [
        row
        for row in sort_by_score(daily_rows, "final_score")
        if normalize_ticker(row.get("ticker")) in AI_SEMI_MEGA_TICKERS
        or theme_for(normalize_ticker(row.get("ticker")), index_by_ticker, row) in AI_SEMI_MEGA_THEMES
    ]

    for row in top_ranked[:30]:
        add_row("IR - Top Ranked", row.get("ticker", ""), row, "Daily ranker constructive bucket; human review required.")
    for row in confirmed_earnings[:30]:
        add_row("IR - Confirmed Earnings", row.get("ticker", ""), row, "Provider-confirmed earnings in next 7 days; verify timing manually.")
    for row in high_impact_gaps[:30]:
        add_row("IR - High Impact Data Gaps", row.get("ticker", ""), row, "Not a confirmed earnings event; prioritize manual earnings-date verification.")
    for row in ai_focus_daily[:30]:
        add_row("IR - AI Semis Mega Cap", row.get("ticker", ""), row, "AI, semiconductor, cloud/software, or mega-cap research focus.")
    for row in watchlist_rows:
        add_row("IR - Watchlist Universe", row.get("ticker", ""), row, "Base Pixiu watchlist ticker.")

    counts: dict[str, int] = defaultdict(int)
    for row in koyfin_rows:
        counts[row["watchlist_name"]] += 1
    return koyfin_rows, dict(counts)


def build_tasks(
    daily_rows: list[dict[str, str]],
    index_rows: list[dict[str, str]],
    koyfin_counts: dict[str, int],
) -> list[dict[str, str]]:
    tasks: list[dict[str, str]] = []

    def add_task(
        priority: str,
        task_type: str,
        ticker: str,
        company_name: str,
        due_date: str,
        source: str,
        action: str,
        notes: str,
    ) -> None:
        tasks.append(
            {
                "priority": priority,
                "task_type": task_type,
                "ticker": ticker or "N/A",
                "company_name": company_name or "N/A",
                "due_date": due_date or "N/A",
                "source": source,
                "action": action,
                "status": "open",
                "notes": notes,
            }
        )

    confirmed_earnings = sort_by_score([row for row in index_rows if is_confirmed_next_7(row)], "importance_score")
    high_impact_gaps = sort_by_score([row for row in index_rows if is_high_impact_data_gap(row)], "importance_score")
    top_ranked = [
        row
        for row in sort_by_score(daily_rows, "final_score")
        if first_value(row, "strategy", default="Avoid") in CONSTRUCTIVE_STRATEGIES
    ]

    for row in confirmed_earnings[:15]:
        ticker = normalize_ticker(row.get("ticker"))
        add_task(
            "1",
            "earnings_review",
            ticker,
            first_value(row, "company_name", default=ticker),
            first_value(row, "earnings_date"),
            "index_weekly_earnings_calendar.csv",
            "Verify earnings timing, compare EPS/revenue estimates, and re-run daily ranker after the report.",
            "Do not chase solely because earnings are upcoming.",
        )

    for row in high_impact_gaps[:15]:
        ticker = normalize_ticker(row.get("ticker"))
        add_task(
            "2",
            "data_gap_review",
            ticker,
            first_value(row, "company_name", default=ticker),
            "N/A",
            "index_weekly_earnings_calendar.csv",
            "Verify whether an earnings event is scheduled; this is not a confirmed event.",
            "High index/theme impact but no confirmed earnings date in current output.",
        )

    for row in top_ranked[:15]:
        ticker = normalize_ticker(row.get("ticker"))
        add_task(
            "2",
            "ranked_candidate_review",
            ticker,
            first_value(row, "company_name", "name", default=ticker),
            str(date.today()),
            "daily_investment_scores.csv",
            "Review thesis, valuation, catalyst, risk, and CAD alternative before any action.",
            f"Strategy: {first_value(row, 'strategy')}; final score: {first_value(row, 'final_score')}.",
        )

    add_task(
        "3",
        "koyfin_manual_export",
        "N/A",
        "N/A",
        str(date.today()),
        "koyfin_watchlists.csv",
        "Manually import or recreate watchlists in Koyfin; do not scrape or automate login.",
        f"Generated watchlist groups: {', '.join(f'{name}={count}' for name, count in sorted(koyfin_counts.items())) or 'none'}.",
    )
    add_task(
        "3",
        "fiscal_ai_prompt_review",
        "N/A",
        "N/A",
        str(date.today()),
        "fiscal_ai_research_questions.md",
        "Copy selected prompts into Fiscal.ai manually if useful; API integration remains disabled.",
        "No Fiscal.ai API call is made by this project.",
    )
    return tasks


def notices_block() -> str:
    return "\n".join(f"- {notice}" for notice in NOTICES) + f"\n- {SECURITY_NOTE}\n"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "N/A") for field in fieldnames})


def write_koyfin_markdown(path: Path, koyfin_rows: list[dict[str, str]], koyfin_counts: dict[str, int], warnings: list[str]) -> None:
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in koyfin_rows:
        groups[row["watchlist_name"]].append(row)

    lines = [
        "# Koyfin Watchlists",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Notices",
        notices_block(),
        "## Manual Koyfin Workflow",
        "",
        "- Use `outputs/koyfin_watchlists.csv` as a manual reference/import file.",
        "- Do not scrape Koyfin.",
        "- Do not automate Koyfin login.",
        "- Verify ticker availability, exchange suffixes, and watchlist import format inside Koyfin.",
        "",
        "## Watchlist Groups",
        "",
    ]
    if not koyfin_counts:
        lines.append("- No watchlist rows generated.")
    else:
        for name, count in sorted(koyfin_counts.items()):
            lines.append(f"- {name}: {count} tickers")
    lines.append("")

    headers = [
        "ticker",
        "company_name",
        "strategy",
        "final_score",
        "importance_score",
        "earnings_date",
        "cad_alternative",
        "notes",
    ]
    for group_name in sorted(groups):
        lines.extend([f"## {group_name}", ""])
        lines.append(markdown_table(headers, groups[group_name], limit=50))

    lines.extend(["## Data Gaps", ""])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No missing input files detected.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def fiscal_prompt_for_confirmed(row: dict[str, str]) -> str:
    ticker = normalize_ticker(row.get("ticker"))
    company = first_value(row, "company_name", default=ticker)
    earnings_date = first_value(row, "earnings_date")
    eps = first_value(row, "eps_estimate")
    revenue = first_value(row, "revenue_estimate")
    return (
        f"- {ticker} / {company}: Research action: verify release timing for {earnings_date}; "
        f"compare expected EPS {eps} and expected revenue {revenue} against prior results; "
        "watch guidance, margins, demand commentary, and peer/ETF read-through. "
        "Do not provide direct buy/sell instructions."
    )


def fiscal_prompt_for_gap(row: dict[str, str]) -> str:
    ticker = normalize_ticker(row.get("ticker"))
    company = first_value(row, "company_name", default=ticker)
    theme = first_value(row, "theme")
    memberships = first_value(row, "index_memberships")
    return (
        f"- {ticker} / {company}: Verify whether an earnings date is scheduled. "
        f"Explain why {theme} and {memberships} exposure could matter for SPY/QQQ/SMH/XLK-style risk. "
        "Treat this as a data-gap review, not a confirmed event."
    )


def fiscal_prompt_for_ranked(row: dict[str, str]) -> str:
    ticker = normalize_ticker(row.get("ticker"))
    strategy = first_value(row, "strategy")
    final_score = first_value(row, "final_score")
    risk = first_value(row, "risk_penalty")
    return (
        f"- {ticker}: Build a research brief for a {strategy} with final score {final_score} "
        f"and risk penalty {risk}. Check valuation, growth quality, revisions, catalysts, "
        "balance sheet risk, and downside scenario. Do not provide direct buy/sell instructions."
    )


def write_fiscal_markdown(
    path: Path,
    daily_rows: list[dict[str, str]],
    index_rows: list[dict[str, str]],
    warnings: list[str],
) -> None:
    confirmed_earnings = sort_by_score([row for row in index_rows if is_confirmed_next_7(row)], "importance_score")
    high_impact_gaps = sort_by_score([row for row in index_rows if is_high_impact_data_gap(row)], "importance_score")
    top_ranked = [
        row
        for row in sort_by_score(daily_rows, "final_score")
        if first_value(row, "strategy", default="Avoid") in CONSTRUCTIVE_STRATEGIES
    ]

    lines = [
        "# Fiscal.ai Research Questions",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Notices",
        notices_block(),
        "## Fiscal.ai API Status",
        "",
        "- Fiscal.ai API integration is disabled and stubbed.",
        "- Use these as manual analyst prompts only.",
        "- Do not paste private brokerage data or API credentials into prompts.",
        "",
        "## Confirmed Earnings Prompts",
        "",
    ]
    if confirmed_earnings:
        lines.extend(fiscal_prompt_for_confirmed(row) for row in confirmed_earnings[:10])
    else:
        lines.append("- No confirmed provider earnings in the next 7 calendar days.")

    lines.extend(["", "## High-Impact Data Gap Prompts", ""])
    if high_impact_gaps:
        lines.extend(fiscal_prompt_for_gap(row) for row in high_impact_gaps[:10])
    else:
        lines.append("- No high-impact data gaps found.")

    lines.extend(["", "## Ranked Candidate Prompts", ""])
    if top_ranked:
        lines.extend(fiscal_prompt_for_ranked(row) for row in top_ranked[:10])
    else:
        lines.append("- No constructive ranked candidates found in current daily scores.")

    lines.extend(
        [
            "",
            "## Reusable Prompt Template",
            "",
            "Use this template manually:",
            "",
            "> Create a research-only earnings and fundamentals brief for [TICKER]. "
            "Verify timing, summarize EPS/revenue expectations, compare prior surprises, "
            "review margin and guidance risk, identify ETF/index read-through, list key risks, "
            "and end with questions for human review. Do not give direct buy/sell instructions.",
            "",
            "## Data Gaps",
            "",
        ]
    )
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No missing input files detected.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def confirmed_summary_sentence(confirmed_earnings: list[dict[str, str]]) -> str:
    if not confirmed_earnings:
        return "No confirmed provider earnings are present in the next 7 calendar days."
    tickers = ", ".join(normalize_ticker(row.get("ticker")) for row in confirmed_earnings[:5])
    return f"{len(confirmed_earnings)} confirmed earnings events are present in the next 7 days: {tickers}."


def write_desk_brief(
    path: Path,
    daily_rows: list[dict[str, str]],
    index_rows: list[dict[str, str]],
    koyfin_counts: dict[str, int],
    tasks: list[dict[str, str]],
    warnings: list[str],
) -> None:
    confirmed_earnings = sort_by_score([row for row in index_rows if is_confirmed_next_7(row)], "importance_score")
    high_impact_gaps = sort_by_score([row for row in index_rows if is_high_impact_data_gap(row)], "importance_score")
    top_ranked = [
        row
        for row in sort_by_score(daily_rows, "final_score")
        if first_value(row, "strategy", default="Avoid") in CONSTRUCTIVE_STRATEGIES
    ]

    confirmed_headers = [
        "ticker",
        "company_name",
        "earnings_date",
        "report_timing",
        "days_until_earnings",
        "importance_score",
        "importance_bucket",
        "cad_alternative",
    ]
    gap_headers = [
        "ticker",
        "company_name",
        "index_memberships",
        "theme",
        "importance_score",
        "cad_alternative",
    ]
    ranked_headers = [
        "ticker",
        "strategy",
        "final_score",
        "risk_penalty",
        "confidence",
        "cad_alternative",
    ]
    task_headers = ["priority", "task_type", "ticker", "action", "status"]

    lines = [
        "# Daily Wall Street Desk Brief",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Notices",
        notices_block(),
        "## Research Desk Summary",
        "",
        f"- {confirmed_summary_sentence(confirmed_earnings)}",
        f"- High-impact data gaps requiring manual verification: {len(high_impact_gaps)}.",
        f"- Constructive daily ranker candidates: {len(top_ranked)}.",
        f"- Research desk tasks generated: {len(tasks)}.",
        "",
        "## Confirmed Earnings Next 7 Days",
        "",
    ]
    if confirmed_earnings:
        lines.append(markdown_table(confirmed_headers, confirmed_earnings, limit=20))
    else:
        lines.append("- None confirmed in the next 7 calendar days.")

    lines.extend(
        [
            "",
            "## High-Impact Watch Names Without Confirmed Earnings",
            "",
            "These are not confirmed earnings events. They remain high-priority watch names because of index, theme, or ETF impact.",
            "",
        ]
    )
    lines.append(markdown_table(gap_headers, high_impact_gaps, limit=10))

    lines.extend(["", "## Pixiu Focus", ""])
    lines.append(markdown_table(ranked_headers, top_ranked, limit=20))

    lines.extend(["", "## Koyfin Export Plan", ""])
    if koyfin_counts:
        lines.extend(f"- {name}: {count} tickers" for name, count in sorted(koyfin_counts.items()))
    else:
        lines.append("- No Koyfin watchlist rows generated.")
    lines.extend(
        [
            "",
            "Manual only: use the generated CSV as a reference/import file. Do not scrape Koyfin or automate Koyfin login.",
            "",
            "## Fiscal.ai Prompt Queue",
            "",
            "- Manual prompt file generated at `outputs/fiscal_ai_research_questions.md`.",
            "- Fiscal.ai API integration remains disabled/stubbed.",
            "",
            "## Research Desk Tasks",
            "",
        ]
    )
    lines.append(markdown_table(task_headers, tasks, limit=25))

    lines.extend(
        [
            "",
            "## Risk Reminders",
            "",
            "- Verify earnings dates and timing from broker or company investor relations pages.",
            "- Do not buy solely because earnings are upcoming.",
            "- Avoid oversized positions before earnings.",
            "- Avoid naked options.",
            "- Re-run the daily ranker after earnings.",
            "- CAD alternatives must be verified for liquidity, spread, fees, holdings, CDR ratio, and hedging behavior.",
            "",
            "## Data Gaps",
            "",
        ]
    )
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No missing input files detected.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    watchlist_rows, watchlist_warnings = read_csv(WATCHLIST_CSV)
    index_universe_rows, index_universe_warnings = read_csv(INDEX_UNIVERSE_CSV)
    daily_rows, daily_warnings = read_csv(DAILY_SCORES_CSV)
    index_rows, index_warnings = read_csv(INDEX_EARNINGS_CSV)
    warnings = watchlist_warnings + index_universe_warnings + daily_warnings + index_warnings

    # Fallback to index universe rows for data-gap Koyfin coverage if the current
    # index earnings output is unavailable.
    if not index_rows and index_universe_rows:
        index_rows = [
            {
                **row,
                "earnings_date": "N/A",
                "report_timing": "unknown",
                "days_until_earnings": "N/A",
                "importance_score": "50.00",
                "importance_bucket": "Data Gap / Watch",
                "data_status": "Data Gap / Watch",
                "cad_alternative": "N/A",
                "cad_note": "N/A",
            }
            for row in index_universe_rows
        ]

    koyfin_rows, koyfin_counts = build_koyfin_rows(watchlist_rows, daily_rows, index_rows)
    tasks = build_tasks(daily_rows, index_rows, koyfin_counts)

    koyfin_fieldnames = [
        "watchlist_name",
        "ticker",
        "company_name",
        "sector",
        "theme",
        "strategy",
        "final_score",
        "importance_score",
        "earnings_date",
        "days_until_earnings",
        "cad_alternative",
        "cad_note",
        "notes",
    ]
    task_fieldnames = [
        "priority",
        "task_type",
        "ticker",
        "company_name",
        "due_date",
        "source",
        "action",
        "status",
        "notes",
    ]

    write_csv(KOYFIN_CSV, koyfin_fieldnames, koyfin_rows)
    write_csv(TASKS_CSV, task_fieldnames, tasks)
    write_koyfin_markdown(KOYFIN_MD, koyfin_rows, koyfin_counts, warnings)
    write_fiscal_markdown(FISCAL_MD, daily_rows, index_rows, warnings)
    write_desk_brief(DESK_BRIEF_MD, daily_rows, index_rows, koyfin_counts, tasks, warnings)

    confirmed_count = sum(1 for row in index_rows if is_confirmed_next_7(row))
    high_impact_gap_count = sum(1 for row in index_rows if is_high_impact_data_gap(row))
    constructive_count = sum(
        1
        for row in daily_rows
        if first_value(row, "strategy", default="Avoid") in CONSTRUCTIVE_STRATEGIES
    )

    print("Research Desk Exports Generated")
    print(f"Run date: {date.today()}")
    print(f"Watchlist rows loaded: {len(watchlist_rows)}")
    print(f"Daily score rows loaded: {len(daily_rows)}")
    print(f"Index earnings rows loaded: {len(index_rows)}")
    print(f"Confirmed earnings next 7 days: {confirmed_count}")
    print(f"High-impact data gaps: {high_impact_gap_count}")
    print(f"Constructive daily ranker candidates: {constructive_count}")
    print(f"Koyfin watchlist rows: {len(koyfin_rows)}")
    print(f"Research desk tasks: {len(tasks)}")
    print("Output files:")
    for path in [KOYFIN_CSV, KOYFIN_MD, FISCAL_MD, DESK_BRIEF_MD, TASKS_CSV]:
        print(f"- {path}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"- {warning}")
    print(SECURITY_NOTE)
    for notice in NOTICES:
        print(notice)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
