#!/usr/bin/env python3
"""Expand the local index universe from FMP constituents plus watchlist rows."""

from __future__ import annotations

import csv
import argparse
import re
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
INDEX_UNIVERSE_CSV = DATA_DIR / "index_universe.csv"
WATCHLIST_CSV = DATA_DIR / "watchlist.csv"
MANUAL_CONSTITUENTS_CSV = DATA_DIR / "manual_index_constituents.csv"
REPORT_MD = OUTPUT_DIR / "universe_expansion_report.md"
CAPABILITY_REPORT_MD = OUTPUT_DIR / "universe_provider_capability_report.md"

REQUIRED_COLUMNS = [
    "ticker",
    "company_name",
    "index_memberships",
    "sector",
    "industry",
    "theme",
    "source",
    "universe_tier",
    "active",
    "last_updated",
    "source_updated_at",
]

INDEX_ORDER = ["S&P 500", "Nasdaq-100", "Dow 30", "Local Watchlist"]

PUBLIC_WIKI_SOURCES = {
    "S&P 500": {
        "label": "wikipedia_sp500",
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "required_headers": ["symbol", "security", "gics sector"],
    },
    "Nasdaq-100": {
        "label": "wikipedia_nasdaq100",
        "url": "https://en.wikipedia.org/wiki/Nasdaq-100",
        "required_headers": ["ticker", "company"],
    },
    "Dow 30": {
        "label": "wikipedia_dow30",
        "url": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
        "required_headers": ["symbol", "company"],
    },
}

FMP_ENDPOINTS = {
    "S&P 500": [
        ("v3_sp500_constituent", "https://financialmodelingprep.com/api/v3/sp500_constituent"),
        ("stable_sp500_constituent", "https://financialmodelingprep.com/stable/sp500-constituent"),
    ],
    "Nasdaq-100": [
        ("v3_nasdaq_constituent", "https://financialmodelingprep.com/api/v3/nasdaq_constituent"),
        ("stable_nasdaq_constituent", "https://financialmodelingprep.com/stable/nasdaq-constituent"),
    ],
    "Dow 30": [
        ("v3_dowjones_constituent", "https://financialmodelingprep.com/api/v3/dowjones_constituent"),
        ("stable_dowjones_constituent", "https://financialmodelingprep.com/stable/dowjones-constituent"),
    ],
}

HIGH_PRIORITY_TICKERS = {
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "GOOG",
    "AMZN",
    "META",
    "TSLA",
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
    "SMCI",
}


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def today_text() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_ticker(value: Any) -> str:
    ticker = clean(value).upper()
    return ticker.replace(".", "-")


def normalize_cell(value: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", clean(value))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_header(value: str) -> str:
    text = normalize_cell(value).lower()
    text = text.replace("\xa0", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_memberships(value: str) -> set[str]:
    parts = [part.strip() for part in clean(value).replace(",", ";").split(";")]
    return {part for part in parts if part}


def ordered_memberships(memberships: set[str]) -> str:
    ordered = [name for name in INDEX_ORDER if name in memberships]
    extra = sorted(memberships - set(INDEX_ORDER))
    return "; ".join(ordered + extra)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [
            {clean(key): clean(value) for key, value in row.items()}
            for row in csv.DictReader(handle)
            if row
        ]


class WikiTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._in_table = 0
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._in_table == 0:
                self._current_table = []
            self._in_table += 1
            return
        if self._in_table <= 0:
            return
        if tag == "tr":
            self._in_row = True
            self._current_row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_table <= 0:
            return
        if tag in {"td", "th"} and self._in_cell:
            self._current_row.append(normalize_cell("".join(self._current_cell)))
            self._current_cell = []
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._current_row = []
            self._in_row = False
        elif tag == "table":
            self._in_table -= 1
            if self._in_table == 0 and self._current_table:
                self.tables.append(self._current_table)
                self._current_table = []

    def handle_data(self, data: str) -> None:
        if self._in_table > 0 and self._in_cell:
            self._current_cell.append(data)


def fetch_public_html(label: str, url: str) -> tuple[str, dict[str, Any]]:
    request = urllib.request.Request(url, headers={"User-Agent": "InvestmentRankerResearch/2.1B"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return payload, {
                "provider_name": "Public Web",
                "endpoint_label": label,
                "http_status": str(int(response.status)),
                "rows_returned": 0,
                "error_message_redacted": "",
                "likely_cause": "ok",
            }
    except urllib.error.HTTPError as exc:
        return "", {
            "provider_name": "Public Web",
            "endpoint_label": label,
            "http_status": str(int(exc.code)),
            "rows_returned": 0,
            "error_message_redacted": redacted_message(f"HTTP {exc.code}: {exc.reason}"),
            "likely_cause": "unknown",
        }
    except urllib.error.URLError as exc:
        return "", {
            "provider_name": "Public Web",
            "endpoint_label": label,
            "http_status": "N/A",
            "rows_returned": 0,
            "error_message_redacted": redacted_message(f"URL error: {exc.reason}"),
            "likely_cause": "unknown",
        }


def table_to_dicts(table: list[list[str]], required_headers: list[str]) -> list[dict[str, str]]:
    for header_index, row in enumerate(table[:8]):
        normalized = [normalize_header(cell) for cell in row]
        if all(any(required == header or required in header for header in normalized) for required in required_headers):
            headers = normalized
            records: list[dict[str, str]] = []
            for values in table[header_index + 1 :]:
                if len(values) < 2:
                    continue
                padded = values + [""] * max(0, len(headers) - len(values))
                records.append({headers[index]: normalize_cell(padded[index]) for index in range(len(headers))})
            return records
    return []


def pick_public(row: dict[str, str], *names: str) -> str:
    for name in names:
        for key, value in row.items():
            if name == key or name in key:
                if value:
                    return value
    return ""


def public_row_to_manual(index_name: str, source_label: str, row: dict[str, str]) -> dict[str, str] | None:
    ticker = normalize_ticker(pick_public(row, "symbol", "ticker"))
    company_name = pick_public(row, "security", "company", "company name")
    sector = pick_public(row, "gics sector", "sector")
    industry = pick_public(row, "gics sub industry", "sub industry", "industry")
    if not ticker or not company_name:
        return None
    if not re.match(r"^[A-Z][A-Z0-9-]{0,9}$", ticker):
        return None
    if "<" in ticker or ">" in ticker or "<" in company_name or ">" in company_name:
        return None
    return {
        "ticker": ticker,
        "company_name": company_name,
        "index_memberships": index_name,
        "sector": sector,
        "industry": industry,
        "theme": "",
        "source": source_label,
        "universe_tier": "",
                "active": "TRUE",
                "last_updated": today_text(),
                "source_updated_at": today_text(),
            }


def fetch_public_bootstrap_rows() -> tuple[list[dict[str, str]], list[dict[str, Any]], list[str]]:
    rows: list[dict[str, str]] = []
    diagnostics: list[dict[str, Any]] = [
        {
            "provider_name": "FMP",
            "endpoint_label": "all",
            "http_status": "N/A",
            "rows_returned": 0,
            "error_message_redacted": "FMP not used for public bootstrap.",
            "likely_cause": "not_used",
        },
        {
            "provider_name": "EODHD",
            "endpoint_label": "all",
            "http_status": "N/A",
            "rows_returned": 0,
            "error_message_redacted": "EODHD not used for public bootstrap.",
            "likely_cause": "not_used",
        },
    ]
    errors: list[str] = []
    for index_name, config in PUBLIC_WIKI_SOURCES.items():
        html, diagnostic = fetch_public_html(config["label"], config["url"])
        if not html:
            diagnostics.append(diagnostic)
            errors.append(f"{config['label']}: {diagnostic['error_message_redacted']}")
            continue
        parser = WikiTableParser()
        parser.feed(html)
        source_rows: list[dict[str, str]] = []
        for table in parser.tables:
            records = table_to_dicts(table, list(config["required_headers"]))
            if records:
                for record in records:
                    manual_row = public_row_to_manual(index_name, config["label"], record)
                    if manual_row:
                        source_rows.append(manual_row)
                break
        diagnostic["rows_returned"] = len(source_rows)
        diagnostic["likely_cause"] = "ok" if source_rows else "empty"
        if not source_rows:
            diagnostic["error_message_redacted"] = "No parseable constituent rows found."
            errors.append(f"{config['label']}: no parseable rows")
        diagnostics.append(diagnostic)
        rows.extend(source_rows)
    return rows, diagnostics, errors


def redacted_message(message: str) -> str:
    text = clean(message).replace("\n", " ")
    for key_name in ("FMP_API_KEY", "apikey", "api_key", "token", "Authorization"):
        text = text.replace(key_name, "[redacted_key_label]")
    if len(text) > 220:
        text = text[:217] + "..."
    return text


def likely_cause(http_status: int | None, rows_returned: int, error_message: str | None) -> str:
    message = (error_message or "").lower()
    if http_status in {401, 403} or "unauthorized" in message or "forbidden" in message:
        return "unauthorized"
    if http_status == 402 or "payment" in message or "subscription" in message or "plan" in message:
        return "payment_required"
    if "missing" in message and "key" in message:
        return "missing_key"
    if rows_returned > 0:
        return "ok"
    if http_status and 200 <= http_status < 300:
        return "empty"
    return "unknown"


def capability_row(
    endpoint_label: str,
    http_status: int | None,
    rows_returned: int,
    error_message: str | None,
) -> dict[str, Any]:
    return {
        "provider_name": "FMP",
        "endpoint_label": endpoint_label,
        "http_status": str(http_status) if http_status is not None else "N/A",
        "rows_returned": rows_returned,
        "error_message_redacted": redacted_message(error_message or ""),
        "likely_cause": likely_cause(http_status, rows_returned, error_message),
    }


def request_json(endpoint_label: str, url: str, api_key: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params = urllib.parse.urlencode({"apikey": api_key})
    separator = "&" if "?" in url else "?"
    request_url = f"{url}{separator}{params}"
    request = urllib.request.Request(request_url, headers={"User-Agent": "InvestmentRankerResearch/2.1"})
    http_status: int | None = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            http_status = int(response.status)
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = clean(exc.reason)
        message = f"HTTP {exc.code}: {body or exc.reason}"
        return [], capability_row(endpoint_label, int(exc.code), 0, message)
    except urllib.error.URLError as exc:
        return [], capability_row(endpoint_label, None, 0, f"URL error: {exc.reason}")
    except TimeoutError:
        return [], capability_row(endpoint_label, None, 0, "timeout")

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        return [], capability_row(endpoint_label, http_status, 0, f"invalid JSON: {exc}")

    if isinstance(parsed, dict):
        error_text = clean(parsed.get("Error Message") or parsed.get("error") or parsed.get("message"))
        if error_text:
            return [], capability_row(endpoint_label, http_status, 0, error_text)
        for key in ("data", "historical", "constituents"):
            value = parsed.get(key)
            if isinstance(value, list):
                parsed = value
                break

    if not isinstance(parsed, list):
        return [], capability_row(endpoint_label, http_status, 0, "unexpected response shape")

    rows = [row for row in parsed if isinstance(row, dict)]
    if not rows:
        return rows, capability_row(endpoint_label, http_status, 0, "empty response")
    return rows, capability_row(endpoint_label, http_status, len(rows), None)


def fetch_index(index_name: str, api_key: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    for endpoint_label, endpoint in FMP_ENDPOINTS[index_name]:
        rows, diagnostic = request_json(f"{index_name}::{endpoint_label}", endpoint, api_key)
        diagnostics.append(diagnostic)
        if rows:
            return rows, diagnostics
    return [], diagnostics


def classify_theme(ticker: str, company_name: str, sector: str, industry: str) -> str:
    text = f"{ticker} {company_name} {sector} {industry}".lower()
    if ticker in {"NVDA", "AVGO", "AMD", "MRVL", "MU", "QCOM", "ASML", "ARM", "TSM", "INTC", "SMCI"}:
        return "AI Infrastructure" if ticker in {"NVDA", "AVGO", "AMD", "MRVL", "SMCI"} else "Semiconductors"
    if ticker in {"AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA"}:
        return "Mega-cap Tech"
    if any(term in text for term in ["semiconductor", "chip", "semiconductors"]):
        return "Semiconductors"
    if any(term in text for term in ["software", "cloud", "application", "saas"]):
        return "Cloud / Software"
    if any(term in text for term in ["cybersecurity", "security software"]):
        return "Cybersecurity"
    if any(term in text for term in ["bank", "financial", "insurance", "capital markets"]):
        return "Financials"
    if any(term in text for term in ["energy", "oil", "gas"]):
        return "Energy"
    if any(term in text for term in ["industrial", "aerospace", "machinery", "transport"]):
        return "Industrials"
    if any(term in text for term in ["retail", "consumer staples", "consumer discretionary"]):
        return "Retail"
    if any(term in text for term in ["communication services", "internet", "media", "entertainment"]):
        return "Consumer Internet"
    return "Other"


def universe_tier(ticker: str, memberships: set[str], theme: str) -> str:
    if ticker in HIGH_PRIORITY_TICKERS or theme in {"AI Infrastructure", "Semiconductors", "Mega-cap Tech"}:
        return "theme_watch"
    if memberships & {"S&P 500", "Nasdaq-100", "Dow 30"}:
        return "core_index"
    if "Local Watchlist" in memberships:
        return "core_watchlist"
    return "index"


def add_or_merge(
    universe: dict[str, dict[str, Any]],
    ticker: str,
    company_name: str,
    membership: str | None,
    sector: str,
    industry: str,
    theme: str,
    source: str,
    last_updated: str,
) -> None:
    ticker = normalize_ticker(ticker)
    if not ticker:
        return
    existing = universe.setdefault(
        ticker,
        {
            "ticker": ticker,
            "company_name": "",
            "memberships": set(),
            "sector": "",
            "industry": "",
            "theme": "",
            "sources": set(),
            "last_updated": last_updated,
        },
    )
    if company_name and not existing["company_name"]:
        existing["company_name"] = company_name
    if sector and not existing["sector"]:
        existing["sector"] = sector
    if industry and not existing["industry"]:
        existing["industry"] = industry
    if theme and (not existing["theme"] or existing["theme"] == "Other"):
        existing["theme"] = theme
    if membership:
        existing["memberships"].add(membership)
    existing["sources"].add(source)
    existing["last_updated"] = max(clean(existing.get("last_updated")), last_updated)


def merge_existing(universe: dict[str, dict[str, Any]], rows: list[dict[str, str]], last_updated: str) -> None:
    for row in rows:
        ticker = normalize_ticker(row.get("ticker"))
        memberships = split_memberships(row.get("index_memberships", ""))
        if not memberships:
            memberships = {"Prior Universe"}
        for membership in memberships:
            add_or_merge(
                universe,
                ticker,
                clean(row.get("company_name")),
                membership,
                clean(row.get("sector")),
                clean(row.get("industry")),
                clean(row.get("theme")),
                "prior_index_universe",
                clean(row.get("last_updated") or row.get("source_updated_at") or last_updated),
            )


def merge_watchlist(universe: dict[str, dict[str, Any]], rows: list[dict[str, str]], last_updated: str) -> None:
    for row in rows:
        add_or_merge(
            universe,
            clean(row.get("ticker")),
            clean(row.get("name") or row.get("company_name")),
            "Local Watchlist",
            clean(row.get("sector")),
            clean(row.get("industry")),
            clean(row.get("theme")),
            "local_watchlist",
            last_updated,
        )


def merge_fmp_rows(universe: dict[str, dict[str, Any]], index_name: str, rows: list[dict[str, Any]], last_updated: str) -> None:
    for row in rows:
        add_or_merge(
            universe,
            clean(row.get("symbol") or row.get("ticker")),
            clean(row.get("name") or row.get("companyName") or row.get("company_name")),
            index_name,
            clean(row.get("sector")),
            clean(row.get("subSector") or row.get("industry")),
            "",
            f"fmp_{index_name.lower().replace(' ', '_').replace('-', '_')}",
            last_updated,
        )


def validate_manual_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    required = {"ticker", "company_name", "index_memberships"}
    valid: list[dict[str, str]] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        missing = sorted(column for column in required if not clean(row.get(column)))
        if missing:
            errors.append(f"manual_index_constituents.csv row {index}: missing {', '.join(missing)}")
            continue
        normalized = dict(row)
        normalized["ticker"] = normalize_ticker(row.get("ticker"))
        valid.append(normalized)
    return valid, errors


def write_manual_constituents(rows: list[dict[str, str]]) -> None:
    with MANUAL_CONSTITUENTS_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in REQUIRED_COLUMNS})


def merge_manual_rows(universe: dict[str, dict[str, Any]], rows: list[dict[str, str]], last_updated: str) -> None:
    for row in rows:
        memberships = split_memberships(row.get("index_memberships", ""))
        for membership in memberships:
            add_or_merge(
                universe,
                row.get("ticker", ""),
                row.get("company_name", ""),
                membership,
                row.get("sector", ""),
                row.get("industry", ""),
                row.get("theme", ""),
                "manual_index_constituents",
                clean(row.get("last_updated")) or last_updated,
            )


def materialize(universe: dict[str, dict[str, Any]], last_updated: str) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for ticker in sorted(universe):
        item = universe[ticker]
        memberships = set(item["memberships"])
        company_name = clean(item.get("company_name")) or ticker
        sector = clean(item.get("sector"))
        industry = clean(item.get("industry"))
        theme = clean(item.get("theme")) or classify_theme(ticker, company_name, sector, industry)
        output.append(
            {
                "ticker": ticker,
                "company_name": company_name,
                "index_memberships": ordered_memberships(memberships),
                "sector": sector,
                "industry": industry,
                "theme": theme,
                "source": "; ".join(sorted(item["sources"])),
                "universe_tier": universe_tier(ticker, memberships, theme),
                "active": "TRUE",
                "last_updated": clean(item.get("last_updated")) or last_updated,
                "source_updated_at": clean(item.get("last_updated")) or last_updated,
            }
        )
    return output


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in REQUIRED_COLUMNS})


def validate_output_rows(rows: list[dict[str, str]]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    tickers = {row.get("ticker", "").strip().upper() for row in rows if row.get("ticker")}
    if len(tickers) < 400:
        errors.append(f"unique ticker count {len(tickers)} is below required 400")
    headers = set(REQUIRED_COLUMNS)
    for column in REQUIRED_COLUMNS:
        if any(column not in row for row in rows):
            errors.append(f"missing required column in generated rows: {column}")
    memberships = " ".join(row.get("index_memberships", "") for row in rows)
    for membership in ["S&P 500", "Nasdaq-100", "Dow 30"]:
        if membership not in memberships:
            errors.append(f"missing membership coverage: {membership}")
    bad_tickers = [
        row.get("ticker", "")
        for row in rows
        if not re.match(r"^[A-Z][A-Z0-9-]{0,9}$", row.get("ticker", ""))
        or "<" in row.get("ticker", "")
        or ">" in row.get("ticker", "")
    ]
    if bad_tickers:
        errors.append("invalid ticker values: " + ", ".join(bad_tickers[:10]))
    html_garbage = [
        row.get("ticker", "")
        for row in rows
        if any("<" in row.get(column, "") or ">" in row.get(column, "") for column in REQUIRED_COLUMNS)
    ]
    if html_garbage:
        errors.append("possible HTML garbage rows: " + ", ".join(html_garbage[:10]))
    return not errors, errors


def write_report(
    rows: list[dict[str, str]],
    fetched_counts: dict[str, int],
    errors: list[str],
    snapshot_path: Path | None,
    status: str,
    message: str,
    manual_rows_loaded: int = 0,
    source_mode: str = "unknown",
    validation_errors: list[str] | None = None,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    membership_counts: Counter[str] = Counter()
    sector_counts: Counter[str] = Counter()
    missing_company = 0
    missing_sector = 0
    for row in rows:
        for membership in split_memberships(row.get("index_memberships", "")):
            membership_counts[membership] += 1
        sector = row.get("sector") or "N/A"
        sector_counts[sector] += 1
        if not row.get("company_name"):
            missing_company += 1
        if not row.get("sector"):
            missing_sector += 1

    validation_errors = validation_errors or []
    high_priority = [row for row in rows if row.get("universe_tier") in {"theme_watch", "high_priority"}][:30]
    lines = [
        "# Universe Expansion Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Notices",
        "",
        "- Not financial advice",
        "- Model output requires human review",
        "- Data quality may affect results",
        "- Research-only. No brokerage connection, no orders, no credential storage, and no API key persistence.",
        "",
        "## Status",
        "",
        f"- Status: {status}",
        f"- Source mode: {source_mode}",
        f"- Message: {message}",
        f"- Snapshot created: {snapshot_path if snapshot_path else 'N/A'}",
        f"- Manual import rows loaded: {manual_rows_loaded}",
        f"- Validation result: {'PASS' if not validation_errors and status in {'success', 'manual_import_success'} else 'BLOCKED' if validation_errors else 'N/A'}",
        "",
        "## FMP Fetch Counts",
        "",
    ]
    if fetched_counts:
        lines.extend(f"- {name}: {count}" for name, count in sorted(fetched_counts.items()))
    else:
        lines.append("- No FMP rows fetched.")
    lines.extend(["", "## Universe Summary", "", f"- Total unique tickers: {len(rows)}", ""])
    lines.append("## Count By Index Membership")
    lines.append("")
    if membership_counts:
        lines.extend(f"- {name}: {count}" for name, count in sorted(membership_counts.items()))
    else:
        lines.append("- N/A")
    lines.extend(["", "## Count By Sector", ""])
    for sector, count in sector_counts.most_common():
        lines.append(f"- {sector}: {count}")
    lines.extend(
        [
            "",
            "## Missing Fields",
            "",
            f"- Missing company_name: {missing_company}",
            f"- Missing sector: {missing_sector}",
            "",
            "## Top High-Priority Tickers",
            "",
        ]
    )
    if high_priority:
        lines.extend(
            f"- {row['ticker']} | {row['company_name']} | {row['index_memberships']} | {row['theme']}"
            for row in high_priority
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Provider Errors", ""])
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- None")
    lines.extend(["", "## Validation Diagnostics", ""])
    if validation_errors:
        lines.extend(f"- {error}" for error in validation_errors)
    else:
        lines.append("- No validation errors recorded.")
    lines.extend(
        [
            "",
            "## Public Source Data Quality",
            "",
            "- Public sources are not guaranteed official, complete, or current.",
            "- Human review is required before relying on membership, sector, or industry fields.",
            "- This output is for research universe construction only.",
        ]
    )
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def write_capability_report(diagnostics: list[dict[str, Any]], status: str, message: str, source_mode: str = "unknown") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Universe Provider Capability Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Notices",
        "",
        "- Not financial advice",
        "- Model output requires human review",
        "- Data quality may affect results",
        "- Provider diagnostics are redacted. API keys are not printed or stored.",
        "",
        "## Status",
        "",
        f"- Status: {status}",
        f"- Source mode: {source_mode}",
        f"- Message: {message}",
        f"- FMP: {'not used' if source_mode == 'public_bootstrap' else 'diagnostic only' if source_mode != 'fmp_provider' else 'attempted'}",
        f"- EODHD: not used",
        f"- Public bootstrap attempted: {'yes' if source_mode == 'public_bootstrap' else 'no'}",
        "",
        "## Endpoint Diagnostics",
        "",
        "| provider_name | endpoint_label | http_status | rows_returned | likely_cause | error_message_redacted |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    if diagnostics:
        for row in diagnostics:
            lines.append(
                "| {provider_name} | {endpoint_label} | {http_status} | {rows_returned} | {likely_cause} | {error_message_redacted} |".format(
                    provider_name=clean(row.get("provider_name")) or "FMP",
                    endpoint_label=clean(row.get("endpoint_label")),
                    http_status=clean(row.get("http_status")),
                    rows_returned=clean(row.get("rows_returned")),
                    likely_cause=clean(row.get("likely_cause")),
                    error_message_redacted=clean(row.get("error_message_redacted")).replace("|", "/"),
                )
            )
    else:
        lines.append("| FMP | all | N/A | 0 | missing_key | No provider call attempted. |")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `ok`: endpoint returned constituent rows.",
            "- `unauthorized`: key exists but endpoint access is forbidden or unauthorized.",
            "- `payment_required`: endpoint likely requires a higher FMP plan.",
            "- `missing_key`: no key was available to the process.",
            "- `empty`: endpoint was reachable but returned zero rows.",
            "- `unknown`: transport or response issue; inspect redacted message.",
            "",
        ]
    )
    CAPABILITY_REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def provider_blocked_status(diagnostics: list[dict[str, Any]]) -> str:
    causes = {clean(row.get("likely_cause")) for row in diagnostics}
    if "payment_required" in causes or "unauthorized" in causes:
        return "BLOCKED_BY_PROVIDER_PERMISSION"
    if "missing_key" in causes:
        return "MISSING_PROVIDER_KEY"
    if "empty" in causes:
        return "PROVIDER_RETURNED_ZERO_ROWS"
    return "PROVIDER_UNAVAILABLE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Pixiu index universe.")
    parser.add_argument("--public-bootstrap", action="store_true", help="Fetch public Wikipedia constituent tables and bootstrap the universe.")
    parser.add_argument("--fmp-provider", action="store_true", help="Attempt FMP constituent endpoints. Not used by v2.1B verification.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("FMP_API_KEY")
    existing_rows = read_csv(INDEX_UNIVERSE_CSV)
    watchlist_rows = read_csv(WATCHLIST_CSV)
    manual_input_rows = read_csv(MANUAL_CONSTITUENTS_CSV)
    manual_rows, manual_errors = validate_manual_rows(manual_input_rows) if manual_input_rows else ([], [])
    last_updated = today_text()

    if args.public_bootstrap:
        public_rows, diagnostics, public_errors = fetch_public_bootstrap_rows()
        if public_rows:
            write_manual_constituents(public_rows)
            manual_rows, manual_errors = validate_manual_rows(public_rows)
        universe: dict[str, dict[str, Any]] = {}
        merge_existing(universe, existing_rows, last_updated)
        merge_watchlist(universe, watchlist_rows, last_updated)
        if manual_rows:
            merge_manual_rows(universe, manual_rows, last_updated)
        output_rows = materialize(universe, last_updated)
        validation_ok, validation_errors = validate_output_rows(output_rows)
        errors = public_errors + manual_errors

        if not validation_ok:
            status = "PUBLIC_BOOTSTRAP_VALIDATION_FAILED"
            message = "Public bootstrap did not produce a valid expanded universe. No universe overwrite performed."
            write_capability_report(diagnostics, status, message, source_mode="public_bootstrap")
            write_report(
                existing_rows,
                {name: 0 for name in PUBLIC_WIKI_SOURCES},
                errors,
                None,
                status,
                message,
                manual_rows_loaded=len(manual_rows),
                source_mode="public_bootstrap",
                validation_errors=validation_errors,
            )
            print(message)
            print(f"Public rows parsed: {len(public_rows)}")
            print(f"Report: {REPORT_MD}")
            print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
            return 1

        snapshot_path = DATA_DIR / f"index_universe_snapshot_{now_stamp()}.csv"
        if INDEX_UNIVERSE_CSV.exists():
            snapshot_path.write_text(INDEX_UNIVERSE_CSV.read_text(encoding="utf-8"), encoding="utf-8")
        write_csv(INDEX_UNIVERSE_CSV, output_rows)
        fetched_counts = Counter(row["index_memberships"] for row in public_rows)
        status = "success"
        message = "Universe expanded from public Wikipedia tables plus existing local data."
        write_capability_report(diagnostics, status, message, source_mode="public_bootstrap")
        write_report(
            output_rows,
            dict(fetched_counts),
            errors,
            snapshot_path,
            status,
            message,
            manual_rows_loaded=len(manual_rows),
            source_mode="public_bootstrap",
            validation_errors=[],
        )
        print("Universe public bootstrap complete")
        print(f"Total unique tickers: {len(output_rows)}")
        print(f"Public rows parsed: {len(public_rows)}")
        print(f"Manual constituent CSV: {MANUAL_CONSTITUENTS_CSV}")
        print(f"Snapshot: {snapshot_path}")
        print(f"Output CSV: {INDEX_UNIVERSE_CSV}")
        print(f"Report: {REPORT_MD}")
        print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
        print("Research-only. No brokerage connection, no orders, no API key persistence.")
        return 0

    if manual_rows:
        universe: dict[str, dict[str, Any]] = {}
        merge_existing(universe, existing_rows, last_updated)
        merge_watchlist(universe, watchlist_rows, last_updated)
        merge_manual_rows(universe, manual_rows, last_updated)
        output_rows = materialize(universe, last_updated)
        validation_ok, validation_errors = validate_output_rows(output_rows)
        if not validation_ok:
            status = "MANUAL_IMPORT_VALIDATION_FAILED"
            message = "Manual constituents file exists but did not produce a valid expanded universe. No universe overwrite performed."
            write_capability_report([], status, message, source_mode="manual_import")
            write_report(
                existing_rows,
                {},
                manual_errors,
                None,
                status,
                message,
                manual_rows_loaded=len(manual_rows),
                source_mode="manual_import",
                validation_errors=validation_errors,
            )
            print(message)
            print(f"Report: {REPORT_MD}")
            print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
            return 1
        snapshot_path = DATA_DIR / f"index_universe_snapshot_{now_stamp()}.csv"
        if INDEX_UNIVERSE_CSV.exists():
            snapshot_path.write_text(INDEX_UNIVERSE_CSV.read_text(encoding="utf-8"), encoding="utf-8")
        write_csv(INDEX_UNIVERSE_CSV, output_rows)
        status = "manual_import_success"
        message = "Universe updated from manual_index_constituents.csv plus existing local data."
        write_capability_report([], status, message, source_mode="manual_import")
        write_report(
            output_rows,
            {},
            manual_errors,
            snapshot_path,
            status,
            message,
            manual_rows_loaded=len(manual_rows),
            source_mode="manual_import",
            validation_errors=[],
        )
        print("Universe update complete from manual_index_constituents.csv.")
        print(f"Total unique tickers: {len(output_rows)}")
        print(f"Manual import rows loaded: {len(manual_rows)}")
        print(f"Snapshot: {snapshot_path}")
        print(f"Output CSV: {INDEX_UNIVERSE_CSV}")
        print(f"Report: {REPORT_MD}")
        print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
        print("Research-only. No brokerage connection, no orders, no API key persistence.")
        return 0

    if not args.fmp_provider:
        status = "NO_UPDATE_MODE_SELECTED"
        message = "Run ./scripts/run_universe_update.sh --public-bootstrap to use public sources. No universe overwrite performed."
        write_capability_report([], status, message, source_mode="existing_fallback")
        write_report(
            existing_rows,
            {},
            ["No manual constituents file and no public bootstrap flag provided."],
            None,
            status,
            message,
            manual_rows_loaded=0,
            source_mode="existing_fallback",
        )
        print(message)
        print(f"Report: {REPORT_MD}")
        print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
        return 2

    if not api_key:
        status = "MISSING_PROVIDER_KEY"
        if manual_rows:
            universe: dict[str, dict[str, Any]] = {}
            merge_existing(universe, existing_rows, last_updated)
            merge_watchlist(universe, watchlist_rows, last_updated)
            merge_manual_rows(universe, manual_rows, last_updated)
            output_rows = materialize(universe, last_updated)
            snapshot_path = DATA_DIR / f"index_universe_snapshot_{now_stamp()}.csv"
            if INDEX_UNIVERSE_CSV.exists():
                snapshot_path.write_text(INDEX_UNIVERSE_CSV.read_text(encoding="utf-8"), encoding="utf-8")
            write_csv(INDEX_UNIVERSE_CSV, output_rows)
            message = "Universe updated from manual_index_constituents.csv plus existing local data; no FMP provider call attempted."
            write_capability_report([], "manual_import_success", message)
            write_report(
                output_rows,
                {},
                ["FMP_API_KEY is missing; no provider fetch attempted."] + manual_errors,
                snapshot_path,
                "manual_import_success",
                message,
                manual_rows_loaded=len(manual_rows),
            )
            print("Universe update complete from manual_index_constituents.csv.")
            print(f"Total unique tickers: {len(output_rows)}")
            print(f"Manual import rows loaded: {len(manual_rows)}")
            print(f"Snapshot: {snapshot_path}")
            print(f"Output CSV: {INDEX_UNIVERSE_CSV}")
            print(f"Report: {REPORT_MD}")
            print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
            print("Research-only. No brokerage connection, no orders, no API key persistence.")
            return 0

        message = "Set FMP_API_KEY in the current terminal and rerun ./scripts/run_universe_update.sh."
        write_capability_report([], status, message)
        write_report(
            existing_rows,
            {},
            ["FMP_API_KEY is missing; no provider fetch attempted."] + manual_errors,
            None,
            status,
            message,
            manual_rows_loaded=0,
        )
        print("FMP_API_KEY is missing. Set FMP_API_KEY in the current terminal and rerun ./scripts/run_universe_update.sh.")
        print("No universe overwrite performed.")
        print(f"Report: {REPORT_MD}")
        print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
        return 2

    universe: dict[str, dict[str, Any]] = {}
    merge_existing(universe, existing_rows, last_updated)
    merge_watchlist(universe, watchlist_rows, last_updated)

    fetched_counts: dict[str, int] = {}
    provider_diagnostics: list[dict[str, Any]] = []
    for index_name in FMP_ENDPOINTS:
        rows, diagnostics = fetch_index(index_name, api_key)
        fetched_counts[index_name] = len(rows)
        provider_diagnostics.extend(diagnostics)
        merge_fmp_rows(universe, index_name, rows, last_updated)

    provider_rows_loaded = sum(fetched_counts.values())
    if manual_rows:
        merge_manual_rows(universe, manual_rows, last_updated)

    diagnostic_errors = [
        f"{row.get('endpoint_label')}: {row.get('likely_cause')} {row.get('error_message_redacted')}".strip()
        for row in provider_diagnostics
        if row.get("likely_cause") != "ok"
    ]
    errors = diagnostic_errors + manual_errors

    if not provider_rows_loaded and not manual_rows:
        status = provider_blocked_status(provider_diagnostics)
        message = "FMP provider returned no usable constituent rows. No universe overwrite performed."
        write_capability_report(provider_diagnostics, status, message)
        write_report(
            existing_rows,
            fetched_counts,
            errors or ["No provider rows returned."],
            None,
            status,
            message,
            manual_rows_loaded=0,
        )
        print(f"{status}: FMP provider returned no usable constituent rows. No universe overwrite performed.")
        print(f"Report: {REPORT_MD}")
        print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
        return 1

    output_rows = materialize(universe, last_updated)
    snapshot_path = DATA_DIR / f"index_universe_snapshot_{now_stamp()}.csv"
    if INDEX_UNIVERSE_CSV.exists():
        snapshot_path.write_text(INDEX_UNIVERSE_CSV.read_text(encoding="utf-8"), encoding="utf-8")
    write_csv(INDEX_UNIVERSE_CSV, output_rows)
    status = "success" if provider_rows_loaded else "manual_import_success"
    message = "Universe expanded from FMP plus local watchlist." if provider_rows_loaded else "Universe updated from manual_index_constituents.csv plus existing local data."
    write_capability_report(provider_diagnostics, status, message)
    write_report(output_rows, fetched_counts, errors, snapshot_path, status, message, manual_rows_loaded=len(manual_rows))

    print("Universe update complete")
    print(f"Total unique tickers: {len(output_rows)}")
    for name, count in sorted(fetched_counts.items()):
        print(f"{name} fetched rows: {count}")
    print(f"Manual import rows loaded: {len(manual_rows)}")
    print(f"Snapshot: {snapshot_path}")
    print(f"Output CSV: {INDEX_UNIVERSE_CSV}")
    print(f"Report: {REPORT_MD}")
    print(f"Provider capability report: {CAPABILITY_REPORT_MD}")
    print("Research-only. No brokerage connection, no orders, no API key persistence.")
    if errors:
        print("Provider warnings were recorded in the report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
