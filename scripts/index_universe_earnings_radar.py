#!/usr/bin/env python3
"""
Research-only index universe weekly earnings radar.

Minimal v1.4 implementation: local-file-first, no public index refresh, no
public earnings fetch, no brokerage connection, no orders, and no API keys.
"""

from __future__ import annotations

import csv
import datetime as dt
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from earnings_providers import fetch_provider_earnings_calendar


BASE_DIR = Path(__file__).resolve().parents[1]
INDEX_UNIVERSE_PATH = BASE_DIR / "data" / "index_universe.csv"
INDEX_OVERRIDES_PATH = BASE_DIR / "data" / "index_universe_overrides.csv"
WATCHLIST_PATH = BASE_DIR / "data" / "watchlist.csv"
OUTPUT_CSV = BASE_DIR / "outputs" / "index_weekly_earnings_calendar.csv"
OUTPUT_REPORT = BASE_DIR / "outputs" / "index_weekly_earnings_report.md"

DISCLAIMER_LINES = [
    "Not financial advice",
    "Model output requires human review",
    "Data quality may affect results",
]

INDEX_UNIVERSE_COLUMNS = [
    "ticker",
    "company_name",
    "index_memberships",
    "sector",
    "theme",
    "source",
    "source_updated_at",
]

OVERRIDE_COLUMNS = [
    "ticker",
    "company_name",
    "earnings_date",
    "report_timing",
    "source",
    "source_note",
    "updated_at",
]

OUTPUT_COLUMNS = [
    "ticker",
    "company_name",
    "index_memberships",
    "sector",
    "theme",
    "earnings_date",
    "report_timing",
    "days_until_earnings",
    "eps_estimate",
    "revenue_estimate",
    "provider",
    "earnings_date_source",
    "provider_status",
    "market_cap",
    "recent_momentum",
    "cad_alternative",
    "cad_note",
    "importance_score",
    "importance_bucket",
    "key_reason",
    "key_risk",
    "data_status",
    "source",
]

ALLOWED_OVERRIDE_TIMINGS = {"before_market", "after_market", "during_market", "unknown"}
ALLOWED_OVERRIDE_SOURCES = {"company_ir", "broker", "nasdaq", "yahoo", "marketwatch", "manual"}
INDEX_ORDER = ["Nasdaq-100", "S&P 500", "Dow 30"]

NO_CAD_MAPPING = "No clear direct CAD mapping found"
NO_CAD_MAPPING_NOTE = "No clear direct CAD mapping found; verify manually before trading."

CAD_MAPPING: Dict[str, Tuple[str, str]] = {
    "AAPL": ("AAPL.TO", "Apple CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "AMD": ("AMD.TO", "AMD CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "AMZN": ("AMZN.TO", "Amazon CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "ASML": ("ASML.TO", "ASML CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "AVGO": ("AVGO.TO", "Broadcom CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "CRM": ("CRM.TO", "Salesforce CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "GOOGL": ("GOOG.TO", "Alphabet CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "GOOG": ("GOOG.TO", "Alphabet CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "INTC": ("INTC.TO", "Intel CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "META": ("META.TO", "Meta CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "MRVL": ("MRV.TO", "Marvell Technology CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "MSFT": ("MSFT.TO", "Microsoft CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "MU": ("MU.TO", "Micron CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "NVDA": ("NVDA.TO", "Nvidia CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "ORCL": ("ORAC.TO", "Oracle CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "TSLA": ("TSLA.TO", "Tesla CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "TSM": (
        "CHPS.TO / XCHP.TO",
        "Indirect semiconductor ETF exposure only; not a direct TSM CDR; verify manually before trading.",
    ),
    "ARM": (
        "CHPS.TO / XCHP.TO",
        "Indirect semiconductor ETF exposure only; not a direct ARM CDR; verify manually before trading.",
    ),
}

MAG7 = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA"}
SEMICONDUCTOR_LEADERS = {"NVDA", "AVGO", "AMD", "ASML", "ARM", "TSM", "QCOM", "MU", "MRVL"}
MAJOR_SP_NASDAQ_TECH_THEMES = {
    "AI Infrastructure",
    "Semiconductors",
    "Mega-cap Tech",
    "Cloud / Software",
    "Cybersecurity",
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_ticker(value: Any) -> str:
    return clean_text(value).upper().replace(" ", "")


def normalize_membership(value: Any) -> Optional[str]:
    text = clean_text(value)
    lowered = text.lower().replace("_", " ").replace("-", " ")
    lowered = " ".join(lowered.split())
    if lowered in {"nasdaq 100", "nasdaq100", "ndx", "qqq"}:
        return "Nasdaq-100"
    if lowered in {"s&p 500", "sp 500", "sp500", "s p 500"}:
        return "S&P 500"
    if lowered in {"dow 30", "dow", "djia", "dow jones industrial average"}:
        return "Dow 30"
    return None


def parse_memberships(value: Any) -> List[str]:
    raw_parts = clean_text(value).replace(",", ";").split(";")
    found = []
    for part in raw_parts:
        normalized = normalize_membership(part)
        if normalized and normalized not in found:
            found.append(normalized)
    return [name for name in INDEX_ORDER if name in found]


def membership_text(memberships: Iterable[str]) -> str:
    ordered = [name for name in INDEX_ORDER if name in set(memberships)]
    return "; ".join(ordered) if ordered else "N/A"


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return None
        return number
    text = clean_text(value)
    if not text or text.upper() in {"N/A", "NA", "NONE", "--"}:
        return None
    multiplier = 1.0
    normalized = text.upper().replace("$", "").replace(",", "").strip()
    if normalized.endswith("%"):
        normalized = normalized[:-1].strip()
    if normalized.endswith("T"):
        multiplier = 1_000_000_000_000.0
        normalized = normalized[:-1]
    elif normalized.endswith("B"):
        multiplier = 1_000_000_000.0
        normalized = normalized[:-1]
    elif normalized.endswith("M"):
        multiplier = 1_000_000.0
        normalized = normalized[:-1]
    try:
        return float(normalized) * multiplier
    except ValueError:
        return None


def parse_iso_date(value: Any) -> Optional[dt.date]:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = dt.date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def cad_mapping_for_ticker(ticker: str) -> Tuple[str, str]:
    return CAD_MAPPING.get(normalize_ticker(ticker), (NO_CAD_MAPPING, NO_CAD_MAPPING_NOTE))


def empty_override_meta(path: Path) -> Dict[str, Any]:
    return {
        "path": str(path),
        "file_exists": path.exists(),
        "loaded_count": 0,
        "valid_count": 0,
        "invalid_warnings": [],
        "invalid_by_ticker": {},
    }


def load_index_universe(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    warnings: List[str] = []
    if not path.exists():
        raise FileNotFoundError(f"Index universe file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [column for column in INDEX_UNIVERSE_COLUMNS if column not in fieldnames]
        if missing_columns:
            raise ValueError("Index universe missing columns: " + ", ".join(missing_columns))

        merged: Dict[str, Dict[str, Any]] = {}
        for row_index, row in enumerate(reader, start=2):
            ticker = normalize_ticker(row.get("ticker"))
            if not ticker:
                warnings.append(f"CSV row {row_index}: missing ticker ignored")
                continue

            memberships = parse_memberships(row.get("index_memberships"))
            if not memberships:
                warnings.append(f"{ticker}: no confirmed index membership in local universe seed")

            existing = merged.setdefault(
                ticker,
                {
                    "ticker": ticker,
                    "company_name": "",
                    "index_memberships": set(),
                    "sector": "",
                    "theme": "",
                    "source": set(),
                    "source_updated_at": set(),
                    "market_cap": "",
                    "recent_momentum": "",
                },
            )
            existing["company_name"] = existing["company_name"] or clean_text(row.get("company_name"))
            existing["sector"] = existing["sector"] or clean_text(row.get("sector"))
            existing["theme"] = existing["theme"] or clean_text(row.get("theme"))
            existing["index_memberships"].update(memberships)
            source = clean_text(row.get("source"))
            if source:
                existing["source"].add(source)
            updated_at = clean_text(row.get("source_updated_at"))
            if updated_at:
                existing["source_updated_at"].add(updated_at)
            if not existing["market_cap"]:
                existing["market_cap"] = clean_text(row.get("market_cap"))
            if not existing["recent_momentum"]:
                existing["recent_momentum"] = clean_text(row.get("recent_momentum"))

    rows: List[Dict[str, str]] = []
    for ticker, item in merged.items():
        rows.append(
            {
                "ticker": ticker,
                "company_name": item["company_name"] or "N/A",
                "index_memberships": membership_text(item["index_memberships"]),
                "sector": item["sector"] or "N/A",
                "theme": item["theme"] or "Other",
                "source": "; ".join(sorted(item["source"])) or "N/A",
                "source_updated_at": "; ".join(sorted(item["source_updated_at"])) or "N/A",
                "market_cap": item["market_cap"] or "N/A",
                "recent_momentum": item["recent_momentum"] or "N/A",
            }
        )
    return sorted(rows, key=lambda row: row["ticker"]), warnings


def load_index_overrides(path: Path) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Any]]:
    meta = empty_override_meta(path)
    overrides: Dict[str, Dict[str, str]] = {}
    if not path.exists():
        return overrides, meta

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [column for column in OVERRIDE_COLUMNS if column not in fieldnames]
        if missing_columns:
            meta["invalid_warnings"].append(
                "Invalid override file header: missing columns " + ", ".join(missing_columns)
            )
            return overrides, meta

        for row_index, row in enumerate(reader, start=2):
            if not any(clean_text(row.get(column)) for column in OVERRIDE_COLUMNS):
                continue
            meta["loaded_count"] += 1
            ticker = normalize_ticker(row.get("ticker"))
            errors: List[str] = []
            if not ticker:
                errors.append("ticker required")

            earnings_date = parse_iso_date(row.get("earnings_date"))
            if earnings_date is None:
                errors.append("earnings_date must use YYYY-MM-DD")

            report_timing = clean_text(row.get("report_timing")).lower() or "unknown"
            if report_timing not in ALLOWED_OVERRIDE_TIMINGS:
                errors.append("report_timing must be one of " + ", ".join(sorted(ALLOWED_OVERRIDE_TIMINGS)))

            source = clean_text(row.get("source")).lower() or "manual"
            if source not in ALLOWED_OVERRIDE_SOURCES:
                errors.append("source must be one of " + ", ".join(sorted(ALLOWED_OVERRIDE_SOURCES)))

            updated_at = parse_iso_date(row.get("updated_at"))
            if updated_at is None:
                errors.append("updated_at must use YYYY-MM-DD")

            if errors:
                warning = f"CSV row {row_index}: Invalid override ignored"
                if ticker:
                    warning += f" for {ticker}"
                warning += " - " + "; ".join(errors)
                meta["invalid_warnings"].append(warning)
                if ticker:
                    meta["invalid_by_ticker"].setdefault(ticker, []).append(warning)
                continue

            overrides[ticker] = {
                "ticker": ticker,
                "company_name": clean_text(row.get("company_name")),
                "earnings_date": earnings_date.isoformat(),
                "report_timing": report_timing,
                "source": source,
                "source_note": clean_text(row.get("source_note")),
                "updated_at": updated_at.isoformat(),
            }
            meta["valid_count"] += 1

    return overrides, meta


def load_watchlist_tickers(path: Path) -> set:
    if not path.exists():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return {normalize_ticker(row.get("ticker")) for row in reader if normalize_ticker(row.get("ticker"))}


def index_membership_score(memberships: List[str]) -> float:
    count = len(memberships)
    if count >= 3:
        return 100.0
    if count == 2:
        return 80.0
    if count == 1:
        return 60.0
    return 50.0


def market_cap_score(market_cap: Optional[float]) -> float:
    if market_cap is None:
        return 50.0
    if market_cap >= 2_000_000_000_000:
        return 100.0
    if market_cap >= 1_000_000_000_000:
        return 95.0
    if market_cap >= 500_000_000_000:
        return 90.0
    if market_cap >= 200_000_000_000:
        return 80.0
    if market_cap >= 100_000_000_000:
        return 70.0
    if market_cap >= 50_000_000_000:
        return 60.0
    return 50.0


def recent_momentum_score(momentum: Optional[float]) -> float:
    if momentum is None:
        return 50.0
    if momentum >= 20:
        return 90.0
    if momentum >= 10:
        return 80.0
    if momentum >= 5:
        return 70.0
    if momentum >= 0:
        return 60.0
    if momentum >= -5:
        return 50.0
    if momentum >= -10:
        return 40.0
    return 30.0


def theme_score(theme: str) -> float:
    if theme in {"AI Infrastructure", "Semiconductors", "Mega-cap Tech"}:
        return 100.0
    if theme in {"Cloud / Software", "Cybersecurity"}:
        return 85.0
    if theme == "Consumer Internet":
        return 75.0
    if theme == "Financials":
        return 65.0
    if theme in {"Industrials", "Retail"}:
        return 60.0
    return 50.0


def etf_impact_score(ticker: str, memberships: List[str], theme: str) -> float:
    ticker = normalize_ticker(ticker)
    if ticker in MAG7 or ticker in SEMICONDUCTOR_LEADERS:
        return 100.0
    if {"Nasdaq-100", "S&P 500"}.issubset(set(memberships)) and theme in MAJOR_SP_NASDAQ_TECH_THEMES:
        return 85.0
    if "Dow 30" in memberships:
        return 70.0
    return 50.0


def earnings_timing_score(days_until: Optional[int]) -> float:
    if days_until is None:
        return 40.0
    if 0 <= days_until <= 2:
        return 100.0
    if 3 <= days_until <= 7:
        return 85.0
    if 8 <= days_until <= 30:
        return 65.0
    return 40.0


def importance_bucket(score: float, earnings_date: Optional[dt.date]) -> str:
    if earnings_date is None:
        return "Data Gap / Watch"
    if score >= 80:
        return "Critical Market-Moving Earnings"
    if score >= 65:
        return "High Importance"
    if score >= 50:
        return "Medium Importance"
    return "Low Importance"


def text_or_na(value: Any) -> str:
    text = clean_text(value)
    return text if text else "N/A"


def score_row(
    universe_row: Dict[str, str],
    override: Optional[Dict[str, str]],
    run_date: dt.date,
    invalid_override_warnings: List[str],
    watchlist_tickers: set,
) -> Dict[str, str]:
    ticker = universe_row["ticker"]
    company_name = universe_row["company_name"]
    memberships = parse_memberships(universe_row["index_memberships"])
    theme = universe_row["theme"] or "Other"
    data_status: List[str] = []
    data_status.extend(invalid_override_warnings)

    earnings_date: Optional[dt.date] = None
    report_timing = "unknown"
    output_source = universe_row["source"]
    override_used = False
    earnings_date_source = "none"
    provider = "none"
    provider_status = "not_attempted"
    eps_estimate = "N/A"
    revenue_estimate = "N/A"

    if override:
        override_date = parse_iso_date(override.get("earnings_date"))
        if override_date is not None and override_date < run_date:
            data_status.append(
                f"Stale override ignored: {override_date.isoformat()} from {override.get('source', 'manual')}"
            )
        elif override_date is not None:
            earnings_date = override_date
            report_timing = clean_text(override.get("report_timing")) or "unknown"
            company_name = clean_text(override.get("company_name")) or company_name
            row_source = clean_text(override.get("earnings_date_source")) or clean_text(override.get("source")) or "manual_override"
            provider = clean_text(override.get("provider")) or ("none" if row_source == "manual_override" else row_source)
            provider_status = clean_text(override.get("provider_status")) or "success"
            earnings_date_source = row_source
            eps_estimate = text_or_na(override.get("eps_estimate"))
            revenue_estimate = text_or_na(override.get("revenue_estimate"))
            output_source = f"{universe_row['source']}; earnings:{row_source}"
            override_used = True
            if row_source == "manual_override":
                data_status.append(
                    "Manual override fallback: "
                    f"source {override.get('source', 'manual')}; updated_at {override.get('updated_at', 'N/A')}"
                )
            else:
                data_status.append(
                    "Provider earnings calendar: "
                    f"provider {provider}; status {provider_status}; updated_at {override.get('updated_at', 'N/A')}"
                )
            source_note = clean_text(override.get("source_note"))
            if source_note:
                data_status.append(f"Manual override note: {source_note}")

    days_until: Optional[int] = None
    if earnings_date is not None:
        days_until = (earnings_date - run_date).days
        if 0 <= days_until <= 7:
            data_status.append("Confirmed earnings in next 7 calendar days")
        elif 8 <= days_until <= 30:
            data_status.append("Confirmed earnings in next 30 calendar days; upcoming watch")
        else:
            data_status.append("Confirmed earnings outside 30-day report window")
    else:
        data_status.append("Data Gap / Watch: no confirmed earnings date")

    market_cap = parse_float(universe_row.get("market_cap"))
    recent_momentum = parse_float(universe_row.get("recent_momentum"))
    if market_cap is None:
        data_status.append("market_cap unavailable locally; neutral market cap score used")
    if recent_momentum is None:
        data_status.append("recent_momentum unavailable locally; neutral momentum score used")
    if not memberships:
        data_status.append("index membership not confirmed in local seed; neutral membership score used")

    score = (
        0.20 * index_membership_score(memberships)
        + 0.20 * market_cap_score(market_cap)
        + 0.20 * theme_score(theme)
        + 0.15 * recent_momentum_score(recent_momentum)
        + 0.15 * etf_impact_score(ticker, memberships, theme)
        + 0.10 * earnings_timing_score(days_until)
    )
    score = round(max(0.0, min(100.0, score)), 2)
    bucket = importance_bucket(score, earnings_date)
    cad_alternative, cad_note = cad_mapping_for_ticker(ticker)

    reason_parts = ["local index universe seed"]
    if memberships:
        reason_parts.append(membership_text(memberships))
    else:
        reason_parts.append("no confirmed major index membership")
    if override_used and days_until is not None:
        reason_parts.append(f"{earnings_date_source} earnings in {days_until} calendar days")
    else:
        reason_parts.append("no confirmed provider earnings date")
    reason_parts.append(theme)
    if ticker in watchlist_tickers:
        reason_parts.append("overlaps Pixiu watchlist")

    if override_used and earnings_date_source == "manual_override":
        key_risk = "Manual earnings override fallback used; verify date and timing with broker or company IR before acting."
    elif override_used:
        key_risk = "Provider earnings date used; verify timing with broker or company IR before acting."
    elif earnings_date is None:
        key_risk = "No confirmed provider earnings date; verify manually before acting."
    else:
        key_risk = "Earnings timing may change; verify manually before trading."
    if not memberships:
        key_risk += " Index membership is not confirmed for this starter-universe row."

    return {
        "ticker": ticker,
        "company_name": company_name or "N/A",
        "index_memberships": membership_text(memberships),
        "sector": universe_row["sector"] or "N/A",
        "theme": theme,
        "earnings_date": earnings_date.isoformat() if earnings_date else "N/A",
        "report_timing": report_timing,
        "days_until_earnings": str(days_until) if days_until is not None else "N/A",
        "eps_estimate": eps_estimate,
        "revenue_estimate": revenue_estimate,
        "provider": provider,
        "earnings_date_source": earnings_date_source,
        "provider_status": provider_status,
        "market_cap": text_or_na(universe_row.get("market_cap")),
        "recent_momentum": text_or_na(universe_row.get("recent_momentum")),
        "cad_alternative": cad_alternative,
        "cad_note": cad_note,
        "importance_score": f"{score:.2f}",
        "importance_bucket": bucket,
        "key_reason": "; ".join(reason_parts),
        "key_risk": key_risk,
        "data_status": "; ".join(data_status),
        "source": output_source,
    }


def sort_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    def sort_key(row: Dict[str, str]) -> Tuple[int, int, float, str]:
        days = parse_float(row.get("days_until_earnings"))
        if days is not None and 0 <= days <= 7:
            group = 0
            day_key = int(days)
        elif days is not None and 8 <= days <= 30:
            group = 1
            day_key = int(days)
        elif row.get("earnings_date") not in {"", "N/A", None}:
            group = 2
            day_key = int(days) if days is not None else 9999
        else:
            group = 3
            day_key = 9999
        return (group, day_key, -float(row.get("importance_score") or 0.0), row.get("ticker", ""))

    return sorted(rows, key=sort_key)


def rows_next_7(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result = []
    for row in rows:
        days = parse_float(row.get("days_until_earnings"))
        if days is not None and 0 <= days <= 7:
            result.append(row)
    return result


def rows_next_30(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result = []
    for row in rows:
        days = parse_float(row.get("days_until_earnings"))
        if days is not None and 0 <= days <= 30:
            result.append(row)
    return result


def rows_data_gap(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [row for row in rows if row.get("earnings_date") in {"", "N/A", None}]


def rows_high_impact_data_gap(rows: List[Dict[str, str]], minimum_score: float = 65.0) -> List[Dict[str, str]]:
    result = []
    for row in rows_data_gap(rows):
        score = parse_float(row.get("importance_score"))
        if score is not None and score >= minimum_score:
            result.append(row)
    return sorted(result, key=lambda row: (-float(row.get("importance_score") or 0.0), row.get("ticker", "")))


def write_csv(rows: List[Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "N/A") for column in OUTPUT_COLUMNS})


def markdown_escape(value: Any) -> str:
    text = text_or_na(value)
    return text.replace("|", "\\|").replace("\n", " ")


def markdown_table(rows: List[Dict[str, str]], columns: List[Tuple[str, str]], empty_text: str, limit: Optional[int] = None) -> str:
    selected = rows[:limit] if limit else rows
    if not selected:
        return f"_{empty_text}_\n"
    lines = [
        "| " + " | ".join(header for header, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in selected:
        lines.append("| " + " | ".join(markdown_escape(row.get(key, "N/A")) for _, key in columns) + " |")
    return "\n".join(lines) + "\n"


def filter_membership(rows: List[Dict[str, str]], membership: str) -> List[Dict[str, str]]:
    return [row for row in rows if membership in parse_memberships(row.get("index_memberships"))]


def brief_timing_label(row: Dict[str, str]) -> str:
    ticker = text_or_na(row.get("ticker"))
    days = parse_float(row.get("days_until_earnings"))
    if days is None:
        return f"{ticker} has no confirmed earnings date"
    day_count = int(days)
    if day_count == 0:
        return f"{ticker} reports today"
    if day_count == 1:
        return f"{ticker} reports tomorrow"
    return f"{ticker} reports in {day_count} calendar days"


def brief_estimate_text(row: Dict[str, str]) -> str:
    eps = text_or_na(row.get("eps_estimate"))
    revenue = text_or_na(row.get("revenue_estimate"))
    if eps == "N/A" and revenue == "N/A":
        return "EPS/revenue estimates unavailable"
    return f"EPS estimate: {eps}; revenue estimate: {revenue}"


def brief_theme_focus(row: Dict[str, str]) -> str:
    theme = text_or_na(row.get("theme"))
    if theme in {"AI Infrastructure", "Semiconductors"}:
        return "data-center demand, gross margin, inventory, capex signals, and guidance"
    if theme in {"Mega-cap Tech", "Cloud / Software", "Cybersecurity"}:
        return "revenue growth, AI/cloud demand, margins, retention, and guidance"
    if theme == "Retail":
        return "margins, consumer demand, pricing, inventory, and guidance"
    if theme == "Financials":
        return "net interest income, credit quality, trading activity, and capital return"
    if theme == "Industrials":
        return "orders, backlog, margins, supply chain, and guidance"
    if theme == "Consumer Internet":
        return "engagement, ad demand, subscription trends, margins, and guidance"
    return "revenue quality, margins, demand signals, and guidance"


def provider_plain_english(provider_meta: Dict[str, Any]) -> str:
    provider = text_or_na(provider_meta.get("provider"))
    status = text_or_na(provider_meta.get("status"))
    raw_count = provider_meta.get("raw_count", 0)
    intersected = provider_meta.get("intersected_count", 0)
    fallback_used = provider_meta.get("fallback_used", False)
    message = clean_text(provider_meta.get("error"))

    if status == "success":
        return (
            f"Provider {provider} succeeded. It returned {raw_count} raw earnings rows, "
            f"and {intersected} matched the local index universe. Manual fallback used: {fallback_used}."
        )
    if status == "missing_api_key":
        return (
            "No earnings provider key was available. Set FMP_API_KEY or FINNHUB_API_KEY "
            "to enable automatic provider calendar fetch. Manual overrides remain emergency fallback only."
        )
    if message:
        return (
            f"Provider {provider} status is {status}. Provider message: {message}. "
            f"Manual fallback used: {fallback_used}."
        )
    return f"Provider {provider} status is {status}. Manual fallback used: {fallback_used}."


def confirmed_event_brief(row: Dict[str, str]) -> str:
    company = text_or_na(row.get("company_name"))
    indexes = text_or_na(row.get("index_memberships")).replace("; ", " / ")
    theme = text_or_na(row.get("theme"))
    timing = text_or_na(row.get("report_timing"))
    provider = text_or_na(row.get("provider"))
    cad = text_or_na(row.get("cad_alternative"))
    return (
        f"- {brief_timing_label(row)}. {company}. Importance: {text_or_na(row.get('importance_bucket'))}, "
        f"score {text_or_na(row.get('importance_score'))}. Index/theme context: {indexes}; {theme}. "
        f"Timing: {timing}. {brief_estimate_text(row)}. Provider: {provider}. CAD alternative: {cad}. "
        f"Research action: verify release timing, compare EPS/revenue to estimates, watch {brief_theme_focus(row)}. "
        "Re-run the daily ranker after the report."
    )


def data_gap_brief(row: Dict[str, str]) -> str:
    indexes = text_or_na(row.get("index_memberships")).replace("; ", " / ")
    return (
        f"- {text_or_na(row.get('ticker'))}: no confirmed earnings date. "
        f"Score {text_or_na(row.get('importance_score'))}; theme {text_or_na(row.get('theme'))}; "
        f"indexes {indexes}. Research action: verify the earnings date from provider, broker, or company IR before treating this as an event."
    )


def build_daily_earnings_brief(rows: List[Dict[str, str]], provider_meta: Dict[str, Any]) -> str:
    next_7 = rows_next_7(rows)
    today = [row for row in next_7 if parse_float(row.get("days_until_earnings")) == 0]
    high_impact_gaps = rows_high_impact_data_gap(rows)[:10]

    lines = [
        "### Provider Summary",
        "",
        provider_plain_english(provider_meta),
        "",
        "### Today's Confirmed Earnings Events",
        "",
    ]
    if today:
        lines.extend(confirmed_event_brief(row) for row in today)
    else:
        lines.append("- No confirmed provider earnings today.")

    lines.extend(["", "### Next 7 Days Confirmed Earnings Events", ""])
    if next_7:
        lines.extend(confirmed_event_brief(row) for row in next_7)
    else:
        lines.append("- No confirmed provider earnings in the next 7 days.")

    lines.extend(["", "### Highest-Priority Research Actions", ""])
    if next_7:
        lines.append("- Verify release timing for each confirmed provider event before treating it as actionable research input.")
        lines.append("- Watch EPS/revenue surprise, margin commentary, demand signals, and guidance.")
        lines.append("- Re-run the daily ranker after each confirmed report.")
    else:
        lines.append("- No confirmed provider earnings are available for the next 7 days; prioritize manual verification of high-impact data gaps.")
        lines.append("- Confirm dates through provider data, broker calendar, or company investor relations before treating any watch name as an event.")
    lines.append("- Do not chase solely because earnings are upcoming.")

    lines.extend(["", "### High-Impact Watch Names With No Confirmed Earnings Date", ""])
    if high_impact_gaps:
        lines.append("These are not confirmed earnings events. They remain high-priority watch names because of index, theme, or ETF impact.")
        lines.extend(data_gap_brief(row) for row in high_impact_gaps)
    else:
        lines.append("- No high-impact data gaps currently meet the watch threshold.")

    lines.extend(
        [
            "",
            "### Risk Reminders",
            "",
            "- Research-only output. Not financial advice.",
            "- Model output requires human review. Data quality may affect results.",
            "- Verify earnings date and release timing from broker or company IR page.",
            "- Avoid oversized positions before earnings.",
            "- Avoid naked options.",
            "- Check implied move if reviewing options.",
        ]
    )
    return "\n".join(lines)


def write_report(
    rows: List[Dict[str, str]],
    path: Path,
    run_date: dt.date,
    universe_warnings: List[str],
    override_meta: Dict[str, Any],
    watchlist_tickers: set,
    provider_meta: Dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    next_7 = rows_next_7(rows)
    next_30 = rows_next_30(rows)
    data_gaps = rows_data_gap(rows)
    high_impact_data_gaps = rows_high_impact_data_gap(rows)
    watchlist_overlap = [row for row in rows if row["ticker"] in watchlist_tickers]
    ai_semiconductor_mega = [
        row
        for row in rows
        if row.get("theme") in {"AI Infrastructure", "Semiconductors", "Mega-cap Tech"}
    ]
    warning_lines = ["- " + markdown_escape(warning) for warning in (universe_warnings + list(override_meta.get("invalid_warnings") or []))[:50]]
    provider_status_lines = [
        f"- Provider attempted: {provider_meta.get('provider', 'none')}",
        f"- Provider status: {provider_meta.get('status', 'unknown')}",
        f"- Raw provider rows: {provider_meta.get('raw_count', 0)}",
        f"- Intersected with index universe: {provider_meta.get('intersected_count', 0)}",
        f"- Manual fallback used: {provider_meta.get('fallback_used', False)}",
    ]
    provider_error = clean_text(provider_meta.get("error"))
    if provider_error:
        provider_status_lines.append(f"- Provider message: {provider_error}")
    if not warning_lines:
        warning_lines = ["- None"]

    top_columns = [
        ("Ticker", "ticker"),
        ("Company", "company_name"),
        ("Indexes", "index_memberships"),
        ("Theme", "theme"),
        ("Earnings Date", "earnings_date"),
        ("Timing", "report_timing"),
        ("Days", "days_until_earnings"),
        ("Score", "importance_score"),
        ("Bucket", "importance_bucket"),
        ("CAD Alternative", "cad_alternative"),
    ]
    gap_columns = [
        ("Ticker", "ticker"),
        ("Company", "company_name"),
        ("Indexes", "index_memberships"),
        ("Theme", "theme"),
        ("Data Status", "data_status"),
    ]
    cad_columns = [
        ("Ticker", "ticker"),
        ("CAD Alternative", "cad_alternative"),
        ("CAD Note", "cad_note"),
    ]

    lines = [
        "# Index Universe Weekly Earnings Radar",
        "",
        f"Generated: {dt.datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Run date: {run_date.isoformat()}",
        f"Look-ahead window: {run_date.isoformat()} to {(run_date + dt.timedelta(days=7)).isoformat()}",
        "",
        "Required notices:",
        "",
        "- Not financial advice",
        "- Model output requires human review",
        "- Data quality may affect results",
        "",
        "Security boundary: research-only; no brokerage connection; no private account access; no orders; no API keys; no naked options recommendation.",
        "",
        "## Provider Status",
        "",
        "\n".join(provider_status_lines),
        "",
        "## Daily Earnings Brief",
        "",
        build_daily_earnings_brief(rows, provider_meta),
        "",
        "## Index Universe Weekly Earnings Summary",
        "",
        f"- Index universe tickers analyzed: {len(rows)}",
        f"- Confirmed earnings in next 7 calendar days: {len(next_7)}",
        f"- Confirmed earnings in next 30 calendar days: {len(next_30)}",
        f"- Data Gap / Watch rows: {len(data_gaps)}",
        f"- High-impact Data Gap / Watch rows: {len(high_impact_data_gaps)}",
        f"- Manual override rows loaded: {override_meta.get('loaded_count', 0)}",
        f"- Valid manual overrides: {override_meta.get('valid_count', 0)}",
        "- v1.5 provider mode fetches earnings calendar data when FMP_API_KEY or FINNHUB_API_KEY is available.",
        "- Market cap and momentum remain local-file-first in this step.",
        "",
        "## Top 20 Market-Moving Earnings",
        "",
        "Confirmed earnings only. Data Gap / Watch rows are excluded from this section.",
        "",
        markdown_table(next_7, top_columns, "None confirmed in the next 7 calendar days.", limit=20),
        "",
        "## High-Impact Data Gaps / Watch",
        "",
        "These are high-importance index names with no confirmed earnings date. They are not confirmed earnings events and require manual verification.",
        "",
        markdown_table(high_impact_data_gaps, top_columns, "No high-impact data gaps found.", limit=20),
        "",
        "## Nasdaq-100 Earnings",
        "",
        markdown_table(filter_membership(next_30, "Nasdaq-100"), top_columns, "No confirmed Nasdaq-100 earnings found.", limit=50),
        "",
        "## S&P 500 Earnings",
        "",
        markdown_table(filter_membership(next_30, "S&P 500"), top_columns, "No confirmed S&P 500 earnings found.", limit=50),
        "",
        "## Dow 30 Earnings",
        "",
        markdown_table(filter_membership(next_30, "Dow 30"), top_columns, "No confirmed Dow 30 earnings found.", limit=50),
        "",
        "## AI / Semiconductor / Mega-Cap Earnings",
        "",
        markdown_table(
            [row for row in ai_semiconductor_mega if row in next_30],
            top_columns,
            "No confirmed AI, semiconductor, or mega-cap earnings found.",
            limit=50,
        ),
        "",
        "## Watchlist Overlap",
        "",
        markdown_table(watchlist_overlap, top_columns, "No overlap with the Pixiu watchlist.", limit=50),
        "",
        "## CAD Alternatives",
        "",
        "CAD alternatives must be verified in the broker before trading. CDRs may have different liquidity, spread, CDR ratio, and hedging behavior than the U.S. underlying. ETF alternatives are not exact clones unless specifically verified.",
        "",
        markdown_table(rows, cad_columns, "No CAD mapping rows available.", limit=100),
        "",
        "## Data Gaps / Source Limits",
        "",
        "- Earnings dates are fetched from provider calendar APIs when keys are available; manual overrides are emergency fallback only.",
        "- Market cap and recent momentum are `N/A` unless provided locally; neutral scores are used for missing values.",
        "- The starter universe is manually seeded and not a complete live index membership refresh.",
        "",
        "Warnings:",
        "",
        "\n".join(warning_lines),
        "",
        "Data-gap rows:",
        "",
        markdown_table(data_gaps, gap_columns, "No data-gap rows.", limit=100),
        "",
        "## Human Review Checklist",
        "",
        "- Verify earnings date from broker or company IR page",
        "- Do not buy solely because earnings are upcoming",
        "- Avoid oversized positions before earnings",
        "- Avoid naked options",
        "- Check implied move if trading options",
        "- Re-run daily Pixiu after earnings",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def provider_rows_by_ticker(provider_rows: List[Dict[str, str]], universe_tickers: set) -> Dict[str, Dict[str, str]]:
    selected: Dict[str, Dict[str, str]] = {}
    for provider_row in provider_rows:
        ticker = normalize_ticker(provider_row.get("ticker"))
        if ticker not in universe_tickers:
            continue
        earnings_date = parse_iso_date(provider_row.get("earnings_date"))
        if earnings_date is None:
            continue
        current = selected.get(ticker)
        current_date = parse_iso_date(current.get("earnings_date")) if current else None
        if current is None or current_date is None or earnings_date < current_date:
            provider_payload = dict(provider_row)
            provider_payload["ticker"] = ticker
            provider_payload["earnings_date_source"] = provider_payload.get("earnings_date_source") or provider_payload.get("provider") or "provider"
            provider_payload["provider_status"] = provider_payload.get("provider_status") or "success"
            selected[ticker] = provider_payload
    return selected


def analyze(run_date: dt.date) -> Tuple[List[Dict[str, str]], List[str], Dict[str, Any], set, Dict[str, Any]]:
    universe_rows, universe_warnings = load_index_universe(INDEX_UNIVERSE_PATH)
    overrides, override_meta = load_index_overrides(INDEX_OVERRIDES_PATH)
    watchlist_tickers = load_watchlist_tickers(WATCHLIST_PATH)
    invalid_by_ticker = override_meta.get("invalid_by_ticker") or {}

    universe_tickers = {row["ticker"] for row in universe_rows}
    provider_meta = fetch_provider_earnings_calendar(run_date, run_date + dt.timedelta(days=7))
    provider_events = provider_rows_by_ticker(provider_meta.get("rows") or [], universe_tickers)
    provider_meta["intersected_count"] = len(provider_events)

    provider_success = provider_meta.get("status") == "success"
    use_manual_fallback = not provider_success
    provider_meta["fallback_used"] = False

    output_rows = []
    for row in universe_rows:
        ticker = row["ticker"]
        event = provider_events.get(ticker)
        if event is None and use_manual_fallback:
            event = overrides.get(ticker)
            if event:
                event = dict(event)
                event["earnings_date_source"] = "manual_override"
                event["provider"] = "none"
                event["provider_status"] = "provider_failed_manual_fallback"
                provider_meta["fallback_used"] = True

        output_rows.append(
            score_row(
                row,
                event,
                run_date,
                invalid_by_ticker.get(ticker, []),
                watchlist_tickers,
            )
        )
    return sort_rows(output_rows), universe_warnings, override_meta, watchlist_tickers, provider_meta


def print_console_summary(rows: List[Dict[str, str]], run_date: dt.date) -> None:
    next_7 = rows_next_7(rows)
    data_gaps = rows_data_gap(rows)
    high_impact_data_gaps = rows_high_impact_data_gap(rows)
    print("Index Universe Weekly Earnings Radar complete")
    print(f"Run date: {run_date.isoformat()}")
    print(f"Tickers loaded from index universe: {len(rows)}")
    print(f"Confirmed earnings in next 7 days: {len(next_7)}")
    print(f"High-impact data gaps: {len(high_impact_data_gaps)}")
    print(f"Data Gap / Watch rows: {len(data_gaps)}")
    print()
    print("Top 20 market-moving earnings:")
    top_rows = next_7[:20]
    if not top_rows:
        print("- No confirmed index earnings in next 7 calendar days.")
    else:
        for row in top_rows:
            print(
                "- {ticker}: {earnings_date}, score {importance_score}, {importance_bucket}, indexes {index_memberships}, CAD {cad_alternative}".format(
                    **row
                )
            )
    print()
    print("Top 10 high-impact data gaps / watch:")
    if not high_impact_data_gaps:
        print("- None")
    else:
        for row in high_impact_data_gaps[:10]:
            print(
                "- {ticker}: no confirmed earnings date, score {importance_score}, indexes {index_memberships}, CAD {cad_alternative}".format(
                    **row
                )
            )
    print()
    print(f"CSV output: {OUTPUT_CSV}")
    print(f"Markdown report: {OUTPUT_REPORT}")


def main() -> int:
    run_date = dt.date.today()
    try:
        rows, universe_warnings, override_meta, watchlist_tickers, provider_meta = analyze(run_date)
        write_csv(rows, OUTPUT_CSV)
        write_report(rows, OUTPUT_REPORT, run_date, universe_warnings, override_meta, watchlist_tickers, provider_meta)
        print_console_summary(rows, run_date)
    except Exception as exc:
        print(f"Index Universe Weekly Earnings Radar failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
