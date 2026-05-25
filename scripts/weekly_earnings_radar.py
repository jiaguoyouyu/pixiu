#!/usr/bin/env python3
"""
Research-only weekly earnings radar for the Pixiu watchlist.

This script does not place trades, connect to brokerage accounts, scrape
private accounts, use margin, execute options, or store credentials. It reads
the local watchlist, attempts public per-ticker enrichment, and writes weekly
earnings research outputs.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parents[1]
WATCHLIST_PATH = BASE_DIR / "data" / "watchlist.csv"
EARNINGS_OVERRIDES_PATH = BASE_DIR / "data" / "earnings_overrides.csv"
OUTPUT_CSV = BASE_DIR / "outputs" / "weekly_earnings_calendar.csv"
OUTPUT_REPORT = BASE_DIR / "outputs" / "weekly_earnings_report.md"

DISCLAIMER_LINES = [
    "Not financial advice",
    "Model output requires human review",
    "Data quality may affect results",
]

CSV_COLUMNS = [
    "ticker",
    "company_name",
    "sector",
    "theme",
    "earnings_date",
    "report_timing",
    "days_until_earnings",
    "market_cap",
    "recent_momentum",
    "watchlist_match",
    "cad_alternative",
    "cad_note",
    "importance_score",
    "importance_bucket",
    "key_reason",
    "key_risk",
    "data_status",
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

ALLOWED_OVERRIDE_TIMINGS = {"before_market", "after_market", "during_market", "unknown"}
ALLOWED_OVERRIDE_SOURCES = {"company_ir", "broker", "nasdaq", "yahoo", "marketwatch", "manual"}

ETF_TICKERS = {
    "SPY",
    "VOO",
    "SPYM",
    "IVV",
    "SPLG",
    "QQQ",
    "QQQM",
    "XLK",
    "SMH",
    "SOXX",
    "XSD",
    "IGV",
    "VGT",
    "IYW",
    "ARKK",
}

NO_CAD_MAPPING = "No clear direct CAD mapping found"
NO_CAD_MAPPING_NOTE = "No clear direct CAD mapping found; verify manually before trading."

CAD_MAPPING: Dict[str, Tuple[str, str]] = {
    "AAPL": ("AAPL.TO", "Apple CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "AMD": ("AMD.TO", "AMD CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "AMZN": ("AMZN.TO", "Amazon CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "ASML": ("ASML.TO", "ASML CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "AVGO": ("AVGO.TO", "Broadcom CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "COIN": ("COIN.TO", "Coinbase CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "CRM": ("CRM.TO", "Salesforce CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "CRWV": ("CRWV.TO", "CoreWeave CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "GOOGL": ("GOOG.TO", "Alphabet CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "GOOG": ("GOOG.TO", "Alphabet CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "INTC": ("INTC.TO", "Intel CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "KLAC": ("KLAC.TO", "KLA CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "LRCX": ("LRCX.TO", "Lam Research CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "META": ("META.TO", "Meta CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "MRVL": ("MRV.TO", "Marvell Technology CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "MSFT": ("MSFT.TO", "Microsoft CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "MU": ("MU.TO", "Micron CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "NVDA": ("NVDA.TO", "Nvidia CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "ORCL": ("ORAC.TO", "Oracle CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "PLTR": ("PLTR.TO", "Palantir CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "SNDK": ("SNDK.TO", "Sandisk CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "TSLA": ("TSLA.TO", "Tesla CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "WDC": ("WDC.TO", "Western Digital CDR; verify liquidity, spread, CDR ratio, and hedging behavior."),
    "SPY": (
        "VFV.TO / ZSP.TO / XUS.TO",
        "CAD S&P 500 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "VOO": (
        "VFV.TO / ZSP.TO / XUS.TO",
        "CAD S&P 500 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "SPYM": (
        "VFV.TO / ZSP.TO / XUS.TO",
        "CAD S&P 500 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "QQQ": (
        "XQQ.TO / ZQQ.TO / QQC.TO / HXQ.TO",
        "CAD Nasdaq 100 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "QQQM": (
        "XQQ.TO / ZQQ.TO / QQC.TO / HXQ.TO",
        "CAD Nasdaq 100 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "XLK": (
        "TEC.TO / TXF.TO / XIT.TO",
        "CAD tech ETF alternatives; not exact XLK clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "VGT": (
        "TEC.TO / TXF.TO / XIT.TO",
        "CAD tech ETF alternatives; not exact VGT clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "IYW": (
        "TEC.TO / TXF.TO / XIT.TO",
        "CAD tech ETF alternatives; not exact IYW clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "SMH": (
        "CHPS.TO / XCHP.TO",
        "CAD semiconductor ETF alternatives; not exact SMH clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "SOXX": (
        "CHPS.TO / XCHP.TO",
        "CAD semiconductor ETF alternatives; not exact SOXX clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "XSD": (
        "CHPS.TO / XCHP.TO",
        "CAD semiconductor ETF alternatives; not exact XSD clone; verify holdings, fees, liquidity, spread, and hedge status.",
    ),
    "TSM": (
        "CHPS.TO / XCHP.TO",
        "Indirect semiconductor ETF exposure only; not a direct TSM CDR; verify manually before trading.",
    ),
    "ARM": (
        "CHPS.TO / XCHP.TO",
        "Indirect semiconductor ETF exposure only; not a direct ARM CDR; verify manually before trading.",
    ),
    "DELL": (
        NO_CAD_MAPPING,
        "No clear direct CAD CDR; consider USD listing or broader ETF exposure; verify manually before trading.",
    ),
    "NBIS": (NO_CAD_MAPPING, NO_CAD_MAPPING_NOTE),
    "CRCL": (
        NO_CAD_MAPPING,
        "No clear direct CAD mapping; COIN.TO is only a rough crypto-equity proxy; verify manually before trading.",
    ),
    "MP": (NO_CAD_MAPPING, NO_CAD_MAPPING_NOTE),
}

AI_INFRASTRUCTURE = {"NVDA", "SMCI", "SOUN", "IONQ"}
SEMICONDUCTORS = {"AMD", "AVGO", "MRVL", "MU", "TSM", "ASML", "ARM", "QCOM", "SMH", "SOXX", "XSD"}
MEGA_CAP_TECH = {"MSFT", "GOOGL", "GOOG", "AMZN", "META", "AAPL", "NVDA", "TSLA", "QQQ", "XLK", "IYW", "VGT"}
CLOUD_SOFTWARE = {"CRM", "NOW", "DDOG", "PLTR", "SNOW", "NET", "MDB", "MSFT", "AMZN", "GOOGL"}
CYBERSECURITY = {"CRWD"}
CONSUMER_INTERNET = {"META", "RDDT", "RBLX", "APP", "SHOP"}
CRYPTO_CAPITAL_MARKETS = {"COIN", "CRCL"}
ETF_IMPACT = {"SPY", "QQQ", "XLK", "IYW", "VGT", "SMH", "SOXX", "ARKK"}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_ticker(value: Any) -> str:
    return clean_text(value).upper().replace(" ", "")


def cad_mapping_for_ticker(ticker: str) -> Tuple[str, str]:
    return CAD_MAPPING.get(normalize_ticker(ticker), (NO_CAD_MAPPING, NO_CAD_MAPPING_NOTE))


def is_etf(ticker: str, sector: str) -> bool:
    return normalize_ticker(ticker) in ETF_TICKERS or clean_text(sector).lower() == "etf"


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return None
        return float(value)
    text = clean_text(value)
    if not text or text.upper() in {"N/A", "NA", "NONE", "--"}:
        return None

    multiplier = 1.0
    upper = text.upper().replace("$", "").replace(",", "").strip()
    if upper.endswith("%"):
        upper = upper[:-1].strip()
    if upper.endswith("T"):
        multiplier = 1_000_000_000_000.0
        upper = upper[:-1]
    elif upper.endswith("B"):
        multiplier = 1_000_000_000.0
        upper = upper[:-1]
    elif upper.endswith("M"):
        multiplier = 1_000_000.0
        upper = upper[:-1]
    elif upper.endswith("K"):
        multiplier = 1_000.0
        upper = upper[:-1]

    try:
        return float(upper) * multiplier
    except ValueError:
        return None


def raw_value(node: Any) -> Any:
    if isinstance(node, dict):
        if "raw" in node:
            return node.get("raw")
        if "fmt" in node:
            return node.get("fmt")
        if "longFmt" in node:
            return node.get("longFmt")
    return node


def request_json(url: str, timeout: float = 8.0) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")), None
    except HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except URLError as exc:
        return None, f"URL error: {exc.reason}"
    except TimeoutError:
        return None, "request timed out"
    except json.JSONDecodeError as exc:
        return None, f"JSON decode error: {exc}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def yahoo_quote_summary_url(ticker: str) -> str:
    encoded = quote(ticker, safe="")
    modules = "price,summaryDetail,defaultKeyStatistics,financialData,calendarEvents"
    return f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{encoded}?modules={modules}"


def yahoo_chart_url(ticker: str) -> str:
    encoded = quote(ticker, safe="")
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        "?range=3mo&interval=1d&includePrePost=false&events=div%2Csplits"
    )


def nasdaq_summary_url(ticker: str, asset_class: str) -> str:
    encoded = quote(ticker, safe="")
    return f"https://api.nasdaq.com/api/quote/{encoded}/summary?assetclass={asset_class}"


def load_watchlist(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Watchlist not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Watchlist is empty: {path}")

    normalized: List[Dict[str, str]] = []
    seen = set()
    for row_index, row in enumerate(rows, start=2):
        ticker = normalize_ticker(row.get("ticker"))
        if not ticker:
            raise ValueError(f"Missing ticker at watchlist CSV row {row_index}")
        if ticker in seen:
            continue
        seen.add(ticker)
        normalized.append(
            {
                "ticker": ticker,
                "company_name": clean_text(row.get("name")) or "N/A",
                "sector": clean_text(row.get("sector")) or "N/A",
            }
        )
    return normalized


def parse_iso_date(value: Any) -> Optional[dt.date]:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = dt.date.fromisoformat(text)
    except ValueError:
        return None
    if parsed.isoformat() != text:
        return None
    return parsed


def empty_override_meta(path: Path) -> Dict[str, Any]:
    return {
        "path": str(path),
        "file_exists": path.exists(),
        "loaded_count": 0,
        "valid_count": 0,
        "invalid_warnings": [],
        "invalid_by_ticker": {},
    }


def load_earnings_overrides(path: Path) -> Tuple[Dict[str, Dict[str, str]], Dict[str, Any]]:
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
            row_errors: List[str] = []
            if not ticker:
                row_errors.append("ticker required")

            earnings_date_text = clean_text(row.get("earnings_date"))
            earnings_date = parse_iso_date(earnings_date_text)
            if earnings_date is None:
                row_errors.append("earnings_date must use YYYY-MM-DD")

            report_timing = clean_text(row.get("report_timing")).lower() or "unknown"
            if report_timing not in ALLOWED_OVERRIDE_TIMINGS:
                row_errors.append(
                    "report_timing must be one of " + ", ".join(sorted(ALLOWED_OVERRIDE_TIMINGS))
                )

            source = clean_text(row.get("source")).lower() or "manual"
            if source not in ALLOWED_OVERRIDE_SOURCES:
                row_errors.append("source must be one of " + ", ".join(sorted(ALLOWED_OVERRIDE_SOURCES)))

            updated_at_text = clean_text(row.get("updated_at"))
            updated_at = parse_iso_date(updated_at_text)
            if updated_at is None:
                row_errors.append("updated_at must use YYYY-MM-DD")

            if row_errors:
                warning = f"CSV row {row_index}: Invalid override ignored"
                if ticker:
                    warning += f" for {ticker}"
                warning += " - " + "; ".join(row_errors)
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


def parse_yahoo_date(node: Any) -> Optional[dt.date]:
    value = raw_value(node)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(value)).date()
        except (OverflowError, OSError, ValueError):
            return None

    text = clean_text(value)
    if not text:
        return None
    if " - " in text:
        text = text.split(" - ", 1)[0].strip()

    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_report_timing(value: Any) -> str:
    text = clean_text(raw_value(value)).lower()
    if not text:
        return "unknown"
    if any(token in text for token in ("before", "pre", "bmo", "amc-before")):
        return "before market"
    if any(token in text for token in ("after", "post", "amc", "pm")):
        return "after market"
    return "unknown"


def parse_yahoo_quote_summary(ticker: str) -> Tuple[Dict[str, Any], Optional[str]]:
    payload, error = request_json(yahoo_quote_summary_url(ticker), timeout=8.0)
    if error:
        return {}, error
    if not payload:
        return {}, "empty Yahoo quote summary response"
    try:
        result = payload["quoteSummary"]["result"][0]
    except (KeyError, IndexError, TypeError):
        details = None
        try:
            details = payload["quoteSummary"].get("error")
        except (KeyError, TypeError):
            pass
        return {}, f"quote summary unavailable: {details or 'missing expected fields'}"

    price = result.get("price") or {}
    stats = result.get("defaultKeyStatistics") or {}
    calendar = result.get("calendarEvents") or {}
    earnings = calendar.get("earnings") or {}

    metrics: Dict[str, Any] = {}
    company_name = clean_text(price.get("longName")) or clean_text(price.get("shortName"))
    if company_name:
        metrics["company_name"] = company_name

    market_cap = parse_float(raw_value(price.get("marketCap")))
    if market_cap is None:
        market_cap = parse_float(raw_value(stats.get("enterpriseValue")))
    if market_cap is not None:
        metrics["market_cap"] = market_cap

    earnings_dates = earnings.get("earningsDate") or []
    if earnings_dates:
        parsed_date = parse_yahoo_date(earnings_dates[0])
        if parsed_date:
            metrics["earnings_date"] = parsed_date

    timing_node = (
        earnings.get("earningsTime")
        or earnings.get("time")
        or calendar.get("earningsTime")
        or calendar.get("time")
    )
    metrics["report_timing"] = normalize_report_timing(timing_node)
    return metrics, None


def parse_nasdaq_summary_value(summary_data: Dict[str, Any], key: str) -> Any:
    node = summary_data.get(key)
    if isinstance(node, dict):
        return node.get("value")
    return node


def fetch_nasdaq_summary(ticker: str, sector: str) -> Tuple[Dict[str, Any], Optional[str]]:
    asset_class = "etf" if is_etf(ticker, sector) else "stocks"
    payload, error = request_json(nasdaq_summary_url(ticker, asset_class), timeout=8.0)
    if error:
        return {}, error
    if not payload:
        return {}, "empty Nasdaq summary response"

    try:
        data = payload["data"]
    except (KeyError, TypeError):
        return {}, "Nasdaq summary missing expected fields"
    if not data:
        return {}, "Nasdaq summary returned no data"

    summary_data = data.get("summaryData") or {}
    metrics: Dict[str, Any] = {}
    company_name = clean_text(data.get("companyName"))
    if company_name:
        metrics["company_name"] = company_name

    market_cap = parse_float(parse_nasdaq_summary_value(summary_data, "MarketCap"))
    if market_cap is not None:
        metrics["market_cap"] = market_cap
    return metrics, None


def fetch_recent_momentum(ticker: str) -> Tuple[Optional[float], Optional[str]]:
    payload, error = request_json(yahoo_chart_url(ticker), timeout=8.0)
    if error:
        return None, error
    if not payload:
        return None, "empty Yahoo chart response"

    try:
        result = payload["chart"]["result"][0]
        close_values = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        return None, "Yahoo chart missing close series"

    closes = [parse_float(value) for value in close_values]
    closes = [value for value in closes if value is not None and value > 0]
    if len(closes) < 2:
        return None, "Yahoo chart has insufficient close history"

    start = closes[-21] if len(closes) >= 21 else closes[0]
    end = closes[-1]
    if start == 0:
        return None, "Yahoo chart start price is zero"
    return (end / start - 1.0) * 100.0, None


def classify_theme(ticker: str, company_name: str, sector: str) -> str:
    ticker = normalize_ticker(ticker)
    sector_lower = clean_text(sector).lower()
    name_lower = clean_text(company_name).lower()

    explicit_ai_text = (
        "artificial intelligence" in name_lower
        or " ai " in f" {name_lower.replace('-', ' ').replace('/', ' ')} "
        or sector_lower == "ai infrastructure"
    )
    if ticker in AI_INFRASTRUCTURE or explicit_ai_text:
        return "AI Infrastructure"
    if ticker in SEMICONDUCTORS or "semiconductor" in sector_lower or "semiconductor" in name_lower:
        return "Semiconductors"
    if ticker in MEGA_CAP_TECH:
        return "Mega-cap Tech"
    if ticker in CYBERSECURITY or "cyber" in sector_lower or "security" in name_lower:
        return "Cybersecurity"
    if ticker in CLOUD_SOFTWARE or "software" in sector_lower or "cloud" in sector_lower:
        return "Cloud / Software"
    if ticker in CONSUMER_INTERNET:
        return "Consumer Internet"
    if ticker in CRYPTO_CAPITAL_MARKETS or "crypto" in sector_lower or "coinbase" in name_lower:
        return "Crypto / Capital Markets"
    if "financial" in sector_lower:
        return "Financials"
    if "energy" in sector_lower:
        return "Energy"
    if "industrial" in sector_lower:
        return "Industrials"
    if "retail" in sector_lower or ticker == "SHOP":
        return "Retail"
    return "Other"


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
    if market_cap >= 10_000_000_000:
        return 50.0
    return 40.0


def theme_score(theme: str) -> float:
    scores = {
        "AI Infrastructure": 95.0,
        "Mega-cap Tech": 95.0,
        "Semiconductors": 90.0,
        "Cloud / Software": 80.0,
        "Cybersecurity": 80.0,
        "Consumer Internet": 75.0,
        "Crypto / Capital Markets": 70.0,
        "Financials": 55.0,
        "Energy": 55.0,
        "Industrials": 55.0,
        "Retail": 55.0,
        "Other": 50.0,
    }
    return scores.get(theme, 50.0)


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


def index_impact_score(ticker: str, theme: str, market_cap: Optional[float]) -> float:
    ticker = normalize_ticker(ticker)
    if ticker in {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA"}:
        return 100.0
    if ticker in ETF_IMPACT:
        return 85.0
    if ticker in {"AVGO", "AMD", "TSM", "ASML", "ARM", "MU", "QCOM", "MRVL", "SMCI"}:
        return 85.0
    if market_cap is not None and market_cap >= 500_000_000_000:
        return 85.0
    if theme in {"AI Infrastructure", "Semiconductors", "Mega-cap Tech"}:
        return 75.0
    return 50.0


def earnings_timing_score(days_until: Optional[int]) -> float:
    if days_until is None:
        return 50.0
    if 0 <= days_until <= 2:
        return 100.0
    if 3 <= days_until <= 5:
        return 85.0
    if 6 <= days_until <= 7:
        return 75.0
    return 50.0


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


def pct_text(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def number_text(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return str(int(round(value)))


def market_cap_text(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def key_reason_for_row(
    ticker: str,
    theme: str,
    earnings_date: Optional[dt.date],
    days_until: Optional[int],
    market_cap: Optional[float],
    momentum: Optional[float],
    confirmation_source: Optional[str] = None,
) -> str:
    reasons = ["watchlist match"]
    if confirmation_source == "manual":
        reasons.append("manual earnings override")
    elif confirmation_source == "public":
        reasons.append("public source confirmed")
    if earnings_date is not None and days_until is not None:
        if 0 <= days_until <= 7:
            reasons.append(f"confirmed earnings in {days_until} calendar days")
        elif 8 <= days_until <= 30:
            reasons.append(f"confirmed earnings in {days_until} calendar days; upcoming watch")
        else:
            reasons.append("confirmed earnings date outside 7-day window")
    else:
        reasons.append("no confirmed earnings date from public source")
    reasons.append(theme)
    if market_cap is not None and market_cap >= 100_000_000_000:
        reasons.append(f"large market cap {market_cap_text(market_cap)}")
    if momentum is not None and abs(momentum) >= 10:
        reasons.append(f"recent momentum {pct_text(momentum)}")
    if normalize_ticker(ticker) in ETF_IMPACT:
        reasons.append("ETF/index exposure signal")
    return "; ".join(reasons)


def key_risk_for_row(
    earnings_date: Optional[dt.date],
    days_until: Optional[int],
    data_status: Iterable[str],
    manual_override_used: bool = False,
) -> str:
    statuses = list(data_status)
    status_text = " ".join(statuses).lower()
    if manual_override_used:
        return "Manual earnings override used; verify date and timing with broker or company IR before acting."
    if "stale override ignored" in status_text:
        return "Stale manual override ignored; verify the earnings date manually before acting."
    if earnings_date is None:
        return "No confirmed earnings date; verify broker or company IR source before acting."
    if days_until is not None and 0 <= days_until <= 7:
        return "Earnings event risk; avoid oversized positions, verify timing, and do not use naked options."
    if any("missing" in status.lower() or "error" in status.lower() for status in statuses):
        return "Public data gaps may affect importance score; verify manually."
    return "Earnings timing may change; verify manually before trading."


def analyze_watchlist_row(
    row: Dict[str, str],
    run_date: dt.date,
    overrides: Dict[str, Dict[str, str]],
    invalid_override_warnings: Dict[str, List[str]],
) -> Dict[str, str]:
    ticker = row["ticker"]
    sector = row["sector"]
    company_name = row["company_name"]
    data_status: List[str] = []

    earnings_date: Optional[dt.date] = None
    report_timing = "unknown"
    market_cap: Optional[float] = None
    recent_momentum: Optional[float] = None
    manual_override_used = False
    confirmation_source: Optional[str] = None

    for warning in invalid_override_warnings.get(ticker, []):
        data_status.append(warning)

    override = overrides.get(ticker)
    if override:
        override_date = parse_iso_date(override.get("earnings_date"))
        if override_date is not None and override_date < run_date:
            data_status.append(
                "Stale override ignored: "
                f"{override_date.isoformat()} from {override.get('source', 'manual')}; "
                f"updated_at {override.get('updated_at', 'N/A')}"
            )
        elif override_date is not None:
            earnings_date = override_date
            report_timing = clean_text(override.get("report_timing")) or "unknown"
            company_name = clean_text(override.get("company_name")) or company_name
            manual_override_used = True
            confirmation_source = "manual"
            data_status.append(
                "Manual override: "
                f"source {override.get('source', 'manual')}; "
                f"updated_at {override.get('updated_at', 'N/A')}"
            )
            source_note = clean_text(override.get("source_note"))
            if source_note:
                data_status.append(f"Manual override note: {source_note}")

    if not manual_override_used:
        yahoo_metrics, yahoo_error = parse_yahoo_quote_summary(ticker)
        if yahoo_error:
            data_status.append(f"Yahoo quote summary error: {yahoo_error}")
        else:
            company_name = clean_text(yahoo_metrics.get("company_name")) or company_name
            market_cap = parse_float(yahoo_metrics.get("market_cap"))
            earnings_date = yahoo_metrics.get("earnings_date")
            report_timing = clean_text(yahoo_metrics.get("report_timing")) or "unknown"
            if earnings_date is not None:
                confirmation_source = "public"
                data_status.append("Public source confirmed")

    if market_cap is None or company_name == "N/A":
        nasdaq_metrics, nasdaq_error = fetch_nasdaq_summary(ticker, sector)
        if nasdaq_error:
            data_status.append(f"Nasdaq summary error: {nasdaq_error}")
        else:
            company_name = clean_text(nasdaq_metrics.get("company_name")) or company_name
            if market_cap is None:
                market_cap = parse_float(nasdaq_metrics.get("market_cap"))

    recent_momentum, momentum_error = fetch_recent_momentum(ticker)
    if momentum_error:
        data_status.append(f"Yahoo chart momentum error: {momentum_error}")

    days_until: Optional[int] = None
    if earnings_date is not None:
        days_until = (earnings_date - run_date).days
        if 0 <= days_until <= 7:
            data_status.append("Earnings date confirmed in next 7 calendar days")
        elif manual_override_used and 8 <= days_until <= 30:
            data_status.append("Manual override upcoming watch within 30 calendar days")
        else:
            data_status.append("Confirmed earnings date outside 7-day window")
    else:
        data_status.append("No confirmed earnings date")

    if market_cap is None:
        data_status.append("market_cap missing; neutral market cap score used")
    if recent_momentum is None:
        data_status.append("recent_momentum missing; neutral momentum score used")

    theme = classify_theme(ticker, company_name, sector)
    watchlist_score = 100.0
    score = (
        0.25 * market_cap_score(market_cap)
        + 0.20 * watchlist_score
        + 0.20 * theme_score(theme)
        + 0.15 * recent_momentum_score(recent_momentum)
        + 0.10 * index_impact_score(ticker, theme, market_cap)
        + 0.10 * earnings_timing_score(days_until)
    )
    score = round(max(0.0, min(100.0, score)), 2)
    bucket = importance_bucket(score, earnings_date)
    cad_alternative, cad_note = cad_mapping_for_ticker(ticker)
    reason = key_reason_for_row(
        ticker,
        theme,
        earnings_date,
        days_until,
        market_cap,
        recent_momentum,
        confirmation_source,
    )
    risk = key_risk_for_row(earnings_date, days_until, data_status, manual_override_used)

    return {
        "ticker": ticker,
        "company_name": company_name or "N/A",
        "sector": sector or "N/A",
        "theme": theme,
        "earnings_date": earnings_date.isoformat() if earnings_date else "N/A",
        "report_timing": report_timing or "unknown",
        "days_until_earnings": str(days_until) if days_until is not None else "N/A",
        "market_cap": number_text(market_cap),
        "recent_momentum": pct_text(recent_momentum),
        "watchlist_match": "yes",
        "cad_alternative": cad_alternative,
        "cad_note": cad_note,
        "importance_score": f"{score:.2f}",
        "importance_bucket": bucket,
        "key_reason": reason,
        "key_risk": risk,
        "data_status": "; ".join(data_status) if data_status else "ok",
    }


def sort_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    def sort_key(row: Dict[str, str]) -> Tuple[int, int, float, str]:
        days = parse_float(row.get("days_until_earnings"))
        confirmed = row.get("earnings_date") not in {"", "N/A", None}
        if days is not None and 0 <= days <= 7:
            group = 0
            day_key = int(days)
        elif confirmed:
            group = 1
            day_key = int(days) if days is not None else 9999
        else:
            group = 2
            day_key = 9999
        return (group, day_key, -float(row.get("importance_score") or 0.0), row.get("ticker", ""))

    return sorted(rows, key=sort_key)


def write_csv(rows: List[Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "N/A") for column in CSV_COLUMNS})


def markdown_escape(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return "N/A"
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


def rows_in_next_7(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result = []
    for row in rows:
        days = parse_float(row.get("days_until_earnings"))
        if days is not None and 0 <= days <= 7:
            result.append(row)
    return result


def rows_in_next_30_watch(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    result = []
    for row in rows:
        days = parse_float(row.get("days_until_earnings"))
        if days is not None and 8 <= days <= 30:
            result.append(row)
    return result


def rows_without_confirmed_date(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [row for row in rows if row.get("earnings_date") in {"", "N/A", None}]


def write_report(
    rows: List[Dict[str, str]],
    path: Path,
    run_date: dt.date,
    override_meta: Dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    next_7 = rows_in_next_7(rows)
    upcoming_watch = rows_in_next_30_watch(rows)
    data_gaps = rows_without_confirmed_date(rows)
    confirmed_outside = [
        row
        for row in rows
        if row.get("earnings_date") not in {"", "N/A", None} and row not in next_7
    ]
    manual_override_rows = [row for row in rows if "Manual override:" in row.get("data_status", "")]
    stale_override_rows = [row for row in rows if "Stale override ignored" in row.get("data_status", "")]
    invalid_warnings = list(override_meta.get("invalid_warnings") or [])
    invalid_stale_count = len(invalid_warnings) + len(stale_override_rows)

    top_columns = [
        ("Ticker", "ticker"),
        ("Company", "company_name"),
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
        ("Theme", "theme"),
        ("CAD Alternative", "cad_alternative"),
        ("Data Status", "data_status"),
    ]
    cad_columns = [
        ("Ticker", "ticker"),
        ("CAD Alternative", "cad_alternative"),
        ("CAD Note", "cad_note"),
    ]
    override_columns = [
        ("Ticker", "ticker"),
        ("Company", "company_name"),
        ("Earnings Date", "earnings_date"),
        ("Timing", "report_timing"),
        ("Days", "days_until_earnings"),
        ("Data Status", "data_status"),
    ]

    ai_semiconductor = [
        row
        for row in rows
        if row.get("theme") in {"AI Infrastructure", "Semiconductors"}
        and (row in next_7 or row in upcoming_watch or row.get("earnings_date") in {"", "N/A", None})
    ]
    mega_cap = [
        row
        for row in rows
        if row.get("theme") == "Mega-cap Tech"
        and (row in next_7 or row in upcoming_watch or row.get("earnings_date") in {"", "N/A", None})
    ]

    invalid_warning_lines = ["- " + markdown_escape(warning) for warning in invalid_warnings[:25]]
    if len(invalid_warnings) > 25:
        invalid_warning_lines.append(f"- {len(invalid_warnings) - 25} additional invalid override warnings omitted.")
    if not invalid_warning_lines:
        invalid_warning_lines = ["- None"]

    lines = [
        "# Weekly Earnings Radar",
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
        "Security boundary: research-only; no brokerage connection; no trade placement; no private account access; no API keys; no naked options recommendation.",
        "",
        "## Weekly Earnings Radar Summary",
        "",
        f"- Watchlist tickers analyzed: {len(rows)}",
        f"- Confirmed earnings in next 7 calendar days: {len(next_7)}",
        f"- Confirmed earnings outside this window: {len(confirmed_outside)}",
        f"- No confirmed earnings date / data gaps: {len(data_gaps)}",
        "- Source approach: public per-ticker Yahoo quote summary calendar events with Yahoo chart and Nasdaq summary enrichment where available.",
        "",
        "## Manual Earnings Overrides",
        "",
        f"- Override file: `{override_meta.get('path', EARNINGS_OVERRIDES_PATH)}`",
        f"- Override file exists: {'yes' if override_meta.get('file_exists') else 'no'}",
        f"- Overrides loaded count: {override_meta.get('loaded_count', 0)}",
        f"- Valid overrides count: {override_meta.get('valid_count', 0)}",
        f"- Invalid/stale overrides count: {invalid_stale_count}",
        f"- Tickers using manual override: {', '.join(row['ticker'] for row in manual_override_rows) if manual_override_rows else 'None'}",
        "",
        "Manual override dates must still be verified with the broker or company investor relations page before trading.",
        "",
        "Manual override rows used:",
        "",
        markdown_table(manual_override_rows, override_columns, "No manual overrides used in this run.", limit=50),
        "",
        "Invalid or stale override warnings:",
        "",
        "\n".join(invalid_warning_lines),
        "",
        "## Top 10 Market-Moving Earnings",
        "",
        markdown_table(next_7, top_columns, "No confirmed watchlist earnings found in the next 7 calendar days.", limit=10),
        "",
        "## Watchlist Earnings In Next 7 Days",
        "",
        markdown_table(next_7, top_columns, "No confirmed watchlist earnings found in the next 7 calendar days."),
        "",
        "## Upcoming Watch Next 30 Days",
        "",
        markdown_table(
            upcoming_watch,
            top_columns,
            "No confirmed watchlist earnings found in days 8-30.",
        ),
        "",
        "## AI / Semiconductor Earnings Focus",
        "",
        markdown_table(
            ai_semiconductor,
            top_columns,
            "No confirmed AI or semiconductor watchlist earnings found in the next 7 calendar days; data-gap rows remain in the CSV.",
            limit=15,
        ),
        "",
        "## Mega-Cap Tech Earnings Focus",
        "",
        markdown_table(
            mega_cap,
            top_columns,
            "No confirmed mega-cap tech watchlist earnings found in the next 7 calendar days; data-gap rows remain in the CSV.",
            limit=15,
        ),
        "",
        "## No Confirmed Earnings Date / Data Gaps",
        "",
        markdown_table(data_gaps, gap_columns, "No missing earnings-date rows.", limit=50),
        "",
        "## CAD Alternatives",
        "",
        "CAD alternatives must be verified in the broker before trading. CDRs may have different liquidity, spread, CDR ratio, and hedging behavior than the U.S. underlying. ETF alternatives are not exact clones unless specifically verified.",
        "",
        markdown_table(rows, cad_columns, "No CAD mapping rows available.", limit=50),
        "",
        "## Earnings Risk Notes",
        "",
        "- Earnings dates from public sources can be stale, missing, or revised. Verify from the broker or company investor relations page.",
        "- Do not buy solely because earnings are upcoming.",
        "- Avoid oversized positions before earnings because gaps can overwhelm normal stop levels.",
        "- Avoid naked options. If options are reviewed, use defined-risk structures only and verify implied move, liquidity, and max loss.",
        "- Re-run the daily Pixiu after earnings because fundamentals, price trend, and risk state can change quickly.",
        "",
        "## Human Review Checklist",
        "",
        "- Verify earnings date from broker or company IR page",
        "- Do not buy solely because earnings are upcoming",
        "- Avoid oversized positions before earnings",
        "- Avoid naked options",
        "- Check implied move if trading options",
        "- Re-run Pixiu after earnings",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def analyze_watchlist(
    rows: List[Dict[str, str]],
    run_date: dt.date,
    overrides: Dict[str, Dict[str, str]],
    override_meta: Dict[str, Any],
) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    invalid_by_ticker = override_meta.get("invalid_by_ticker") or {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_ticker = {
            executor.submit(analyze_watchlist_row, row, run_date, overrides, invalid_by_ticker): row["ticker"]
            for row in rows
        }
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                results.append(future.result())
            except Exception as exc:
                cad_alternative, cad_note = cad_mapping_for_ticker(ticker)
                source_row = next((row for row in rows if row["ticker"] == ticker), {})
                company_name = source_row.get("company_name") or "N/A"
                sector = source_row.get("sector") or "N/A"
                theme = classify_theme(ticker, company_name, sector)
                results.append(
                    {
                        "ticker": ticker,
                        "company_name": company_name,
                        "sector": sector,
                        "theme": theme,
                        "earnings_date": "N/A",
                        "report_timing": "unknown",
                        "days_until_earnings": "N/A",
                        "market_cap": "N/A",
                        "recent_momentum": "N/A",
                        "watchlist_match": "yes",
                        "cad_alternative": cad_alternative,
                        "cad_note": cad_note,
                        "importance_score": "50.00",
                        "importance_bucket": "Data Gap / Watch",
                        "key_reason": "watchlist match; no confirmed earnings date from public source",
                        "key_risk": "Public data fetch failed for this ticker; verify manually before acting.",
                        "data_status": f"ticker analysis error: {type(exc).__name__}: {exc}",
                    }
                )
    return sort_rows(results)


def print_console_summary(rows: List[Dict[str, str]], run_date: dt.date, override_meta: Dict[str, Any]) -> None:
    next_7 = rows_in_next_7(rows)
    data_gaps = rows_without_confirmed_date(rows)
    manual_override_rows = [row for row in rows if "Manual override:" in row.get("data_status", "")]
    stale_override_rows = [row for row in rows if "Stale override ignored" in row.get("data_status", "")]
    print("Weekly Earnings Radar complete")
    print(f"Run date: {run_date.isoformat()}")
    print(f"Watchlist tickers analyzed: {len(rows)}")
    print(f"Overrides loaded: {override_meta.get('loaded_count', 0)}")
    print(f"Valid overrides: {override_meta.get('valid_count', 0)}")
    print(f"Invalid/stale overrides: {len(override_meta.get('invalid_warnings') or []) + len(stale_override_rows)}")
    print(f"Manual overrides used: {len(manual_override_rows)}")
    print(f"Confirmed earnings in next 7 calendar days: {len(next_7)}")
    print(f"No confirmed earnings date / data gaps: {len(data_gaps)}")
    print()
    print("Top 10 market-moving earnings:")
    if not next_7:
        print("- None confirmed in next 7 calendar days")
    else:
        for row in next_7[:10]:
            print(
                "- {ticker}: {earnings_date}, score {importance_score}, {importance_bucket}, CAD {cad_alternative}".format(
                    **row
                )
            )
    print()
    print(f"CSV output: {OUTPUT_CSV}")
    print(f"Markdown report: {OUTPUT_REPORT}")


def main() -> int:
    run_date = dt.date.today()
    try:
        watchlist_rows = load_watchlist(WATCHLIST_PATH)
        overrides, override_meta = load_earnings_overrides(EARNINGS_OVERRIDES_PATH)
        analyzed_rows = analyze_watchlist(watchlist_rows, run_date, overrides, override_meta)
        write_csv(analyzed_rows, OUTPUT_CSV)
        write_report(analyzed_rows, OUTPUT_REPORT, run_date, override_meta)
        print_console_summary(analyzed_rows, run_date, override_meta)
    except Exception as exc:
        print(f"Weekly Earnings Radar failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
