#!/usr/bin/env python3
"""
Research-only investment ranking and strategy engine.

This script does not place trades, connect to brokerage accounts, use margin,
or recommend naked options. It combines a local watchlist with public market
data when available, then writes a ranked CSV and Markdown report.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_WATCHLIST = BASE_DIR / "data" / "watchlist.csv"
DEFAULT_INDEX_UNIVERSE = BASE_DIR / "data" / "index_universe.csv"
DEFAULT_SCORES = BASE_DIR / "outputs" / "daily_investment_scores.csv"
DEFAULT_REPORT = BASE_DIR / "outputs" / "daily_investment_report.md"
DEFAULT_EXPANDED_SCORES = BASE_DIR / "outputs" / "expanded_daily_investment_scores.csv"
DEFAULT_EXPANDED_REPORT = BASE_DIR / "outputs" / "expanded_daily_investment_report.md"
DEFAULT_ACTION_BIAS_EXPLANATION = BASE_DIR / "outputs" / "action_bias_explanation.md"

DISCLAIMER_LINES = [
    "Not financial advice",
    "Model output requires human review",
    "Data quality may affect results",
]
CSV_DISCLAIMER = "; ".join(DISCLAIMER_LINES)

SCORE_COLUMNS = [
    "ticker",
    "final_score",
    "market_score",
    "quality_score",
    "valuation_score",
    "trend_score",
    "catalyst_score",
    "options_score",
    "risk_penalty",
    "strategy",
    "confidence",
    "position_size",
    "entry_zone",
    "stop_or_exit",
    "key_reason",
    "key_risk",
    "cad_alternative",
    "cad_note",
]

EXPANDED_SCORE_COLUMNS = [
    "ticker",
    "company_name",
    "sector",
    "industry",
    "theme",
    "index_memberships",
    "source",
    "universe_tier",
    "quality_score",
    "valuation_score",
    "momentum_score",
    "earnings_risk_score",
    "data_quality_score",
    "market_regime_score",
    "action_score",
    "action_bias",
    "confidence",
    "primary_reason",
    "risk_flags",
    "invalidation_check",
    "backtest_status",
    "options_analysis_status",
    "options_bias",
    "cad_alternative",
    "cad_note",
]

HIGH_PRIORITY_EXPANDED_TICKERS = {
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
    "NFLX",
    "COST",
    "JPM",
    "GS",
    "V",
    "MA",
    "UNH",
    "HD",
    "MCD",
    "CAT",
    "BA",
    "DIS",
    "KO",
    "WMT",
}

DATA_FIELDS = [
    "ticker",
    "name",
    "sector",
    "price",
    "market_cap",
    "pe",
    "forward_pe",
    "ps",
    "ev_to_sales",
    "fcf_yield",
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "net_debt_to_ebitda",
    "5d_return",
    "20d_return",
    "63d_return",
    "250d_return",
    "volume",
    "average_volume",
    "rsi_14",
    "atr_14",
    "ma20",
    "ma50",
    "ma200",
    "iv_rank",
    "iv_minus_hv",
    "earnings_date",
    "analyst_revision",
    "news_catalyst",
]

NUMERIC_FIELDS = {
    "price",
    "market_cap",
    "pe",
    "forward_pe",
    "ps",
    "ev_to_sales",
    "fcf_yield",
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "net_debt_to_ebitda",
    "5d_return",
    "20d_return",
    "63d_return",
    "250d_return",
    "volume",
    "average_volume",
    "rsi_14",
    "atr_14",
    "ma20",
    "ma50",
    "ma200",
    "iv_rank",
    "iv_minus_hv",
    "historical_valuation_discount",
    "buyback_or_dilution",
    "shares_yoy_change",
    "skew_edge",
}

FIELD_ALIASES = {
    "ticker": ["ticker", "symbol"],
    "name": ["name", "company", "fund_name"],
    "sector": ["sector", "industry", "asset_class"],
    "price": ["price", "last", "last_price", "close"],
    "market_cap": ["market_cap", "marketcap", "market_capitalization"],
    "pe": ["pe", "p_e", "trailing_pe", "trailingpe"],
    "forward_pe": ["forward_pe", "forwardpe", "fwd_pe"],
    "ps": ["ps", "p_s", "price_to_sales", "price_sales"],
    "ev_to_sales": ["ev_to_sales", "ev_sales", "enterprise_value_to_sales"],
    "fcf_yield": ["fcf_yield", "free_cash_flow_yield", "free_cashflow_yield"],
    "revenue_growth": ["revenue_growth", "sales_growth", "rev_growth"],
    "gross_margin": ["gross_margin", "gross_margins"],
    "operating_margin": ["operating_margin", "operating_margins"],
    "net_debt_to_ebitda": ["net_debt_to_ebitda", "net_debt_ebitda"],
    "5d_return": ["5d_return", "5_day_return", "5d_ret"],
    "20d_return": ["20d_return", "20_day_return", "20d_ret"],
    "63d_return": ["63d_return", "63_day_return", "63d_ret"],
    "250d_return": ["250d_return", "250_day_return", "250d_ret"],
    "volume": ["volume", "latest_volume"],
    "average_volume": ["average_volume", "avg_volume", "20d_avg_volume"],
    "rsi_14": ["rsi_14", "rsi"],
    "atr_14": ["atr_14", "atr"],
    "ma20": ["ma20", "sma20", "ma_20"],
    "ma50": ["ma50", "sma50", "ma_50"],
    "ma200": ["ma200", "sma200", "ma_200"],
    "iv_rank": ["iv_rank", "implied_volatility_rank"],
    "iv_minus_hv": ["iv_minus_hv", "iv_minus_realizedvol", "iv_minus_realized_vol"],
    "earnings_date": ["earnings_date", "next_earnings_date"],
    "analyst_revision": ["analyst_revision", "analyst_revisions"],
    "news_catalyst": ["news_catalyst", "catalyst", "news"],
}

CAD_ALTERNATIVES = [
    {
        "exposure": "S&P 500",
        "tickers": "VFV.TO, XUS.TO, ZSP.TO",
        "note": "CAD-listed S&P 500 ETF alternatives; not exact clone; verify MER, liquidity, holdings, spread, and hedge status.",
    },
    {
        "exposure": "Nasdaq 100",
        "tickers": "HXQ.TO, QQC.TO, ZQQ.TO",
        "note": "CAD-listed Nasdaq 100 ETF alternatives; not exact clone; verify hedge status, holdings, and spreads.",
    },
    {
        "exposure": "Global technology",
        "tickers": "TEC.TO, XIT.TO",
        "note": "CAD technology ETF alternatives; not exact clone; holdings differ materially from QQQ/XLK.",
    },
    {
        "exposure": "Semiconductors",
        "tickers": "CHPS.TO, XCHP.TO",
        "note": "CAD semiconductor ETF alternatives; not exact clone; verify current listing, AUM, holdings, and bid/ask spread.",
    },
]

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
    "SPY": ("VFV.TO / ZSP.TO / XUS.TO", "CAD S&P 500 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "VOO": ("VFV.TO / ZSP.TO / XUS.TO", "CAD S&P 500 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "SPYM": ("VFV.TO / ZSP.TO / XUS.TO", "CAD S&P 500 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "QQQ": ("XQQ.TO / ZQQ.TO / QQC.TO / HXQ.TO", "CAD Nasdaq 100 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "QQQM": ("XQQ.TO / ZQQ.TO / QQC.TO / HXQ.TO", "CAD Nasdaq 100 ETF alternatives; not exact clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "XLK": ("TEC.TO / TXF.TO / XIT.TO", "CAD tech ETF alternatives; not exact XLK clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "VGT": ("TEC.TO / TXF.TO / XIT.TO", "CAD tech ETF alternatives; not exact VGT clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "IYW": ("TEC.TO / TXF.TO / XIT.TO", "CAD tech ETF alternatives; not exact IYW clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "SMH": ("CHPS.TO / XCHP.TO", "CAD semiconductor ETF alternatives; not exact SMH clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "SOXX": ("CHPS.TO / XCHP.TO", "CAD semiconductor ETF alternatives; not exact SOXX clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "XSD": ("CHPS.TO / XCHP.TO", "CAD semiconductor ETF alternatives; not exact XSD clone; verify holdings, fees, liquidity, spread, and hedge status."),
    "TSM": ("CHPS.TO / XCHP.TO", "Indirect semiconductor ETF exposure only; not a direct TSM CDR; verify manually before trading."),
    "ARM": ("CHPS.TO / XCHP.TO", "Indirect semiconductor ETF exposure only; not a direct ARM CDR; verify manually before trading."),
    "DELL": (NO_CAD_MAPPING, "No clear direct CAD CDR; consider USD listing or broader ETF exposure; verify manually before trading."),
    "NBIS": (NO_CAD_MAPPING, NO_CAD_MAPPING_NOTE),
    "CRCL": (NO_CAD_MAPPING, "No clear direct CAD mapping; COIN.TO is only a rough crypto-equity proxy; verify manually before trading."),
    "MP": (NO_CAD_MAPPING, NO_CAD_MAPPING_NOTE),
}


def normalize_key(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value)).strip("_")


def canonicalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {normalize_key(k): v for k, v in row.items() if k is not None}
    canonical: Dict[str, Any] = {}
    used = set()
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            key = normalize_key(alias)
            if key in normalized:
                canonical[field] = clean_text(normalized[key])
                used.add(key)
                break
    for key, value in normalized.items():
        if key not in used and key not in canonical:
            canonical[key] = clean_text(value)
    return canonical


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return not math.isfinite(value)
    text = str(value).strip()
    return text == "" or text.upper() in {"N/A", "NA", "NAN", "NONE", "NULL", "-", "--"}


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None

    text = str(value).strip()
    if is_missing(text):
        return None
    text = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return None

    multiplier = 1.0
    suffix = text[-1:].upper()
    if suffix in {"K", "M", "B", "T"}:
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
        text = text[:-1]

    try:
        number = float(text) * multiplier
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def as_number(row: Dict[str, Any], key: str) -> Optional[float]:
    return parse_float(row.get(key))


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    if not math.isfinite(value):
        return 50.0
    return max(low, min(high, value))


def linear_score(value: Optional[float], bad: float, good: float) -> float:
    if value is None:
        return 50.0
    if good == bad:
        return 50.0
    return clamp((value - bad) / (good - bad) * 100.0)


def inverse_linear_score(value: Optional[float], good: float, bad: float) -> float:
    if value is None:
        return 50.0
    if good == bad:
        return 50.0
    return clamp((bad - value) / (bad - good) * 100.0)


def bool_score(condition: Optional[bool]) -> float:
    if condition is None:
        return 50.0
    return 100.0 if condition else 0.0


def round_score(value: float) -> float:
    return round(clamp(value), 2)


def compact_number(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    abs_value = abs(value)
    for suffix, divisor in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs_value >= divisor:
            return f"{value / divisor:.2f}{suffix}"
    return f"{value:.2f}"


def fmt_price(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def pct_text(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def load_watchlist(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Watchlist not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [canonicalize_row(row) for row in reader]
    if not rows:
        raise ValueError(f"Watchlist is empty: {path}")
    for index, row in enumerate(rows, start=2):
        ticker = clean_text(row.get("ticker")).upper()
        if not ticker:
            row["_load_error"] = f"missing ticker at CSV row {index}"
        row["ticker"] = ticker
    return rows


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
    except Exception as exc:  # Defensive: public endpoints can fail in many ways.
        return None, f"{type(exc).__name__}: {exc}"


def yahoo_chart_url(ticker: str) -> str:
    encoded = quote(ticker, safe="")
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}"
        "?range=18mo&interval=1d&includePrePost=false&events=div%2Csplits"
    )


def yahoo_quote_summary_url(ticker: str) -> str:
    encoded = quote(ticker, safe="")
    modules = "price,summaryDetail,defaultKeyStatistics,financialData,calendarEvents"
    return f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{encoded}?modules={modules}"


def nasdaq_asset_class(row_or_ticker: Any) -> str:
    if isinstance(row_or_ticker, dict):
        sector = clean_text(row_or_ticker.get("sector")).lower()
        ticker = clean_text(row_or_ticker.get("ticker")).upper()
    else:
        sector = ""
        ticker = clean_text(row_or_ticker).upper()
    return "etf" if ticker in ETF_TICKERS or sector == "etf" else "stocks"


def nasdaq_historical_url(ticker: str, asset_class: str) -> str:
    today = dt.date.today()
    from_date = today - dt.timedelta(days=370)
    encoded = quote(ticker, safe="")
    return (
        f"https://api.nasdaq.com/api/quote/{encoded}/historical"
        f"?assetclass={asset_class}&fromdate={from_date.isoformat()}"
        f"&todate={today.isoformat()}&limit=9999"
    )


def nasdaq_summary_url(ticker: str, asset_class: str) -> str:
    encoded = quote(ticker, safe="")
    return f"https://api.nasdaq.com/api/quote/{encoded}/summary?assetclass={asset_class}"


def nasdaq_financials_url(ticker: str) -> str:
    encoded = quote(ticker, safe="")
    return f"https://api.nasdaq.com/api/company/{encoded}/financials?frequency=1"


def raw_value(node: Any) -> Optional[float]:
    if isinstance(node, dict):
        if "raw" in node:
            return parse_float(node.get("raw"))
        if "fmt" in node:
            return parse_float(node.get("fmt"))
    return parse_float(node)


def fmt_value(node: Any) -> str:
    if isinstance(node, dict):
        if "fmt" in node and node["fmt"] is not None:
            return str(node["fmt"])
        if "raw" in node and node["raw"] is not None:
            raw = node["raw"]
            if isinstance(raw, (int, float)) and raw > 10_000_000:
                try:
                    return dt.datetime.utcfromtimestamp(float(raw)).date().isoformat()
                except (OSError, ValueError):
                    return str(raw)
            return str(raw)
    if node is None:
        return ""
    return str(node)


def moving_average(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    sample = values[-period:]
    if not sample:
        return None
    return sum(sample) / len(sample)


def percent_return(values: List[float], lookback: int) -> Optional[float]:
    if len(values) <= lookback:
        return None
    start = values[-lookback - 1]
    end = values[-1]
    if start in (None, 0) or end is None:
        return None
    return (end / start - 1.0) * 100.0


def rsi(values: List[float], period: int = 14) -> Optional[float]:
    if len(values) <= period:
        return None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    sample = deltas[-period:]
    gains = [max(delta, 0.0) for delta in sample]
    losses = [abs(min(delta, 0.0)) for delta in sample]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) <= period or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    true_ranges: List[float] = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    sample = true_ranges[-period:]
    if len(sample) < period:
        return None
    return sum(sample) / len(sample)


def realized_volatility(values: List[float], period: int = 20) -> Optional[float]:
    if len(values) <= period:
        return None
    returns = []
    for i in range(len(values) - period, len(values)):
        prev = values[i - 1]
        current = values[i]
        if prev and current:
            returns.append(current / prev - 1.0)
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(252.0) * 100.0


def chart_to_metrics(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        result = payload["chart"]["result"][0]
        quote_data = result["indicators"]["quote"][0]
        timestamps = result.get("timestamp") or []
    except (KeyError, IndexError, TypeError):
        return {}, "chart response missing expected fields"

    opens = quote_data.get("open") or []
    highs = quote_data.get("high") or []
    lows = quote_data.get("low") or []
    closes = quote_data.get("close") or []
    volumes = quote_data.get("volume") or []

    aligned: List[Tuple[float, float, float, float, float, int]] = []
    length = min(len(opens), len(highs), len(lows), len(closes), len(volumes), len(timestamps))
    for i in range(length):
        close = parse_float(closes[i])
        high = parse_float(highs[i])
        low = parse_float(lows[i])
        open_ = parse_float(opens[i])
        volume = parse_float(volumes[i])
        timestamp = parse_float(timestamps[i])
        if close is None or high is None or low is None or open_ is None or timestamp is None:
            continue
        aligned.append((open_, high, low, close, volume or 0.0, int(timestamp)))

    if not aligned:
        return {}, "no usable price history"

    open_values = [item[0] for item in aligned]
    high_values = [item[1] for item in aligned]
    low_values = [item[2] for item in aligned]
    close_values = [item[3] for item in aligned]
    volume_values = [item[4] for item in aligned]

    latest_price = close_values[-1]
    latest_volume = volume_values[-1] if volume_values else None
    avg_volume = None
    recent_volumes = [volume for volume in volume_values[-20:] if volume is not None and volume > 0]
    if recent_volumes:
        avg_volume = sum(recent_volumes) / len(recent_volumes)

    atr_14 = atr(high_values, low_values, close_values, 14)
    prev_close = close_values[-2] if len(close_values) >= 2 else None
    gap_up_2atr = False
    if prev_close is not None and atr_14 is not None:
        gap_up_2atr = (open_values[-1] - prev_close) > 2.0 * atr_14

    max_252 = max(close_values[-252:]) if len(close_values) >= 2 else latest_price
    drawdown_from_high = (latest_price / max_252 - 1.0) * 100.0 if max_252 else None

    latest_timestamp = aligned[-1][5]
    latest_date = dt.datetime.utcfromtimestamp(latest_timestamp).date().isoformat()

    metrics: Dict[str, Any] = {
        "price": latest_price,
        "volume": latest_volume,
        "average_volume": avg_volume,
        "5d_return": percent_return(close_values, 5),
        "20d_return": percent_return(close_values, 20),
        "63d_return": percent_return(close_values, 63),
        "250d_return": percent_return(close_values, 250),
        "rsi_14": rsi(close_values, 14),
        "atr_14": atr_14,
        "ma20": moving_average(close_values, 20),
        "ma50": moving_average(close_values, 50),
        "ma200": moving_average(close_values, 200),
        "realized_vol_20d": realized_volatility(close_values, 20),
        "gap_up_2atr": gap_up_2atr,
        "drawdown_from_252d_high": drawdown_from_high,
        "last_price_date": latest_date,
    }
    return metrics, None


def fetch_chart_metrics(ticker: str) -> Tuple[Dict[str, Any], Optional[str]]:
    payload, error = request_json(yahoo_chart_url(ticker))
    if error:
        return {}, error
    if not payload:
        return {}, "empty chart response"
    return chart_to_metrics(payload)


def nasdaq_history_to_metrics(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        rows = payload["data"]["tradesTable"]["rows"]
    except (KeyError, TypeError):
        return {}, "Nasdaq history response missing expected fields"
    if not rows:
        return {}, "Nasdaq history returned no rows"

    aligned: List[Tuple[float, float, float, float, float, int]] = []
    for item in reversed(rows):
        close = parse_float(item.get("close"))
        high = parse_float(item.get("high"))
        low = parse_float(item.get("low"))
        open_ = parse_float(item.get("open"))
        volume = parse_float(item.get("volume"))
        date_text = clean_text(item.get("date"))
        try:
            date_value = dt.datetime.strptime(date_text, "%m/%d/%Y").date()
        except ValueError:
            continue
        if close is None or high is None or low is None or open_ is None:
            continue
        timestamp = int(dt.datetime.combine(date_value, dt.time()).timestamp())
        aligned.append((open_, high, low, close, volume or 0.0, timestamp))

    if not aligned:
        return {}, "Nasdaq history had no usable OHLC rows"

    synthetic_payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [item[5] for item in aligned],
                    "indicators": {
                        "quote": [
                            {
                                "open": [item[0] for item in aligned],
                                "high": [item[1] for item in aligned],
                                "low": [item[2] for item in aligned],
                                "close": [item[3] for item in aligned],
                                "volume": [item[4] for item in aligned],
                            }
                        ]
                    },
                }
            ]
        }
    }
    return chart_to_metrics(synthetic_payload)


def fetch_nasdaq_history_metrics(ticker: str, asset_class: str) -> Tuple[Dict[str, Any], Optional[str]]:
    payload, error = request_json(nasdaq_historical_url(ticker, asset_class), timeout=12.0)
    if error:
        return {}, error
    if not payload:
        return {}, "empty Nasdaq history response"
    return nasdaq_history_to_metrics(payload)


def fetch_public_price_metrics(ticker: str, asset_class: str) -> Tuple[Dict[str, Any], Optional[str], Optional[str]]:
    nasdaq_metrics, nasdaq_error = fetch_nasdaq_history_metrics(ticker, asset_class)
    if nasdaq_metrics:
        return nasdaq_metrics, None, "Nasdaq public historical API"

    yahoo_metrics, yahoo_error = fetch_chart_metrics(ticker)
    if yahoo_metrics:
        return yahoo_metrics, None, "Yahoo Finance public chart API"

    errors = []
    if nasdaq_error:
        errors.append(f"Nasdaq history: {nasdaq_error}")
    if yahoo_error:
        errors.append(f"Yahoo chart: {yahoo_error}")
    return {}, "; ".join(errors) if errors else "no public price data", None


def quote_summary_to_metrics(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        result = payload["quoteSummary"]["result"][0]
    except (KeyError, IndexError, TypeError):
        error = None
        try:
            error = payload["quoteSummary"].get("error")
        except (KeyError, TypeError):
            pass
        return {}, f"quote summary unavailable: {error or 'missing expected fields'}"

    price = result.get("price") or {}
    summary = result.get("summaryDetail") or {}
    stats = result.get("defaultKeyStatistics") or {}
    financial = result.get("financialData") or {}
    calendar = result.get("calendarEvents") or {}

    metrics: Dict[str, Any] = {}
    market_cap = raw_value(price.get("marketCap")) or raw_value(stats.get("enterpriseValue"))
    if market_cap is not None:
        metrics["market_cap"] = market_cap

    field_pairs = [
        ("pe", summary.get("trailingPE") or stats.get("trailingPE")),
        ("forward_pe", summary.get("forwardPE") or stats.get("forwardPE")),
        ("ps", summary.get("priceToSalesTrailing12Months") or stats.get("priceToSalesTrailing12Months")),
        ("ev_to_sales", stats.get("enterpriseToRevenue") or financial.get("enterpriseToRevenue")),
        ("gross_margin", financial.get("grossMargins")),
        ("operating_margin", financial.get("operatingMargins")),
        ("revenue_growth", financial.get("revenueGrowth")),
    ]
    for key, node in field_pairs:
        value = raw_value(node)
        if value is None:
            continue
        if key in {"gross_margin", "operating_margin", "revenue_growth"} and abs(value) <= 2.0:
            value *= 100.0
        metrics[key] = value

    total_debt = raw_value(financial.get("totalDebt"))
    total_cash = raw_value(financial.get("totalCash"))
    ebitda = raw_value(financial.get("ebitda"))
    if total_debt is not None and total_cash is not None and ebitda not in (None, 0):
        metrics["net_debt_to_ebitda"] = (total_debt - total_cash) / ebitda

    free_cashflow = raw_value(financial.get("freeCashflow"))
    if free_cashflow is not None and market_cap not in (None, 0):
        metrics["fcf_yield"] = free_cashflow / market_cap * 100.0

    earnings = calendar.get("earnings") or {}
    earnings_dates = earnings.get("earningsDate") or []
    if earnings_dates:
        metrics["earnings_date"] = fmt_value(earnings_dates[0])

    return metrics, None


def fetch_quote_summary_metrics(ticker: str) -> Tuple[Dict[str, Any], Optional[str]]:
    payload, error = request_json(yahoo_quote_summary_url(ticker))
    if error:
        return {}, error
    if not payload:
        return {}, "empty quote summary response"
    return quote_summary_to_metrics(payload)


def nasdaq_summary_value(summary_data: Dict[str, Any], key: str) -> Any:
    node = summary_data.get(key)
    if isinstance(node, dict):
        return node.get("value")
    return node


def nasdaq_summary_to_metrics(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        data = payload["data"]
    except (KeyError, TypeError):
        return {}, "Nasdaq summary response missing expected fields"
    if not data:
        return {}, "Nasdaq summary returned no data"

    summary_data = data.get("summaryData") or {}
    primary_data = data.get("primaryData") or {}
    metrics: Dict[str, Any] = {}

    price = parse_float(primary_data.get("lastSalePrice"))
    if price is not None:
        metrics["price"] = price

    volume = parse_float(primary_data.get("volume")) or parse_float(nasdaq_summary_value(summary_data, "ShareVolume"))
    if volume is not None:
        metrics["volume"] = volume

    average_volume = parse_float(nasdaq_summary_value(summary_data, "AverageVolume"))
    if average_volume is not None:
        metrics["average_volume"] = average_volume

    market_cap = parse_float(nasdaq_summary_value(summary_data, "MarketCap"))
    if market_cap is not None:
        metrics["market_cap"] = market_cap

    sector = clean_text(nasdaq_summary_value(summary_data, "Sector"))
    if sector:
        metrics["sector"] = sector

    name = clean_text(data.get("companyName"))
    if name:
        metrics["name"] = name

    return metrics, None


def nasdaq_table_rows(table: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    rows = table.get("rows") or []
    result = {}
    for row in rows:
        label = clean_text(row.get("value1")).lower()
        if label:
            result[label] = row
    return result


def nasdaq_latest_value(rows: Dict[str, Dict[str, Any]], label: str, multiply_thousands: bool = True) -> Optional[float]:
    row = rows.get(label.lower())
    if not row:
        return None
    value = parse_float(row.get("value2"))
    if value is None:
        return None
    return value * 1000.0 if multiply_thousands else value


def nasdaq_financials_to_metrics(payload: Dict[str, Any], existing_market_cap: Optional[float]) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        data = payload["data"]
    except (KeyError, TypeError):
        return {}, "Nasdaq financials response missing expected fields"
    if not data:
        return {}, "Nasdaq financials returned no data"

    income_rows = nasdaq_table_rows(data.get("incomeStatementTable") or {})
    balance_rows = nasdaq_table_rows(data.get("balanceSheetTable") or {})
    cash_rows = nasdaq_table_rows(data.get("cashFlowTable") or {})
    ratio_rows = nasdaq_table_rows(data.get("financialRatiosTable") or {})

    metrics: Dict[str, Any] = {}
    revenue = nasdaq_latest_value(income_rows, "Total Revenue")
    previous_revenue = None
    revenue_row = income_rows.get("total revenue")
    if revenue_row:
        previous_revenue = parse_float(revenue_row.get("value3"))
        if previous_revenue is not None:
            previous_revenue *= 1000.0

    gross_profit = nasdaq_latest_value(income_rows, "Gross Profit")
    operating_income = nasdaq_latest_value(income_rows, "Operating Income")
    ebit = nasdaq_latest_value(income_rows, "Earnings Before Interest and Tax")
    net_income = nasdaq_latest_value(income_rows, "Net Income")
    cash = nasdaq_latest_value(balance_rows, "Cash and Cash Equivalents") or 0.0
    short_investments = nasdaq_latest_value(balance_rows, "Short-Term Investments") or 0.0
    short_debt = nasdaq_latest_value(balance_rows, "Short-Term Debt / Current Portion of Long-Term Debt") or 0.0
    long_debt = nasdaq_latest_value(balance_rows, "Long-Term Debt") or 0.0
    operating_cash_flow = nasdaq_latest_value(cash_rows, "Net Cash Flow-Operating")
    capex = nasdaq_latest_value(cash_rows, "Capital Expenditures")
    sale_purchase_stock = nasdaq_latest_value(cash_rows, "Sale and Purchase of Stock")

    gross_margin_ratio = nasdaq_latest_value(ratio_rows, "Gross Margin", multiply_thousands=False)
    operating_margin_ratio = nasdaq_latest_value(ratio_rows, "Operating Margin", multiply_thousands=False)

    if revenue is not None and revenue > 0:
        if previous_revenue not in (None, 0):
            metrics["revenue_growth"] = (revenue / previous_revenue - 1.0) * 100.0
        if gross_margin_ratio is not None:
            metrics["gross_margin"] = gross_margin_ratio
        elif gross_profit is not None:
            metrics["gross_margin"] = gross_profit / revenue * 100.0
        if operating_margin_ratio is not None:
            metrics["operating_margin"] = operating_margin_ratio
        elif operating_income is not None:
            metrics["operating_margin"] = operating_income / revenue * 100.0

        market_cap = existing_market_cap
        if market_cap is not None and market_cap > 0:
            metrics["ps"] = market_cap / revenue
            net_debt = short_debt + long_debt - cash - short_investments
            metrics["ev_to_sales"] = (market_cap + net_debt) / revenue
            if net_income not in (None, 0):
                metrics["pe"] = market_cap / net_income
            if operating_cash_flow is not None and capex is not None:
                fcf = operating_cash_flow + capex
                metrics["fcf_yield"] = fcf / market_cap * 100.0
            if sale_purchase_stock is not None:
                metrics["buyback_or_dilution"] = -sale_purchase_stock / market_cap * 100.0

    denominator = ebit or operating_income
    if denominator not in (None, 0):
        metrics["net_debt_to_ebitda"] = (short_debt + long_debt - cash - short_investments) / denominator

    return metrics, None


def fetch_nasdaq_fundamental_metrics(ticker: str, asset_class: str) -> Tuple[Dict[str, Any], Optional[str]]:
    metrics: Dict[str, Any] = {}
    errors: List[str] = []

    summary_payload, summary_error = request_json(nasdaq_summary_url(ticker, asset_class), timeout=12.0)
    if summary_error:
        errors.append(f"Nasdaq summary: {summary_error}")
    elif summary_payload:
        summary_metrics, parse_error = nasdaq_summary_to_metrics(summary_payload)
        if parse_error:
            errors.append(f"Nasdaq summary: {parse_error}")
        metrics.update(summary_metrics)

    if asset_class != "etf":
        financial_payload, financial_error = request_json(nasdaq_financials_url(ticker), timeout=12.0)
        if financial_error:
            errors.append(f"Nasdaq financials: {financial_error}")
        elif financial_payload:
            financial_metrics, parse_error = nasdaq_financials_to_metrics(
                financial_payload,
                parse_float(metrics.get("market_cap")),
            )
            if parse_error:
                errors.append(f"Nasdaq financials: {parse_error}")
            metrics.update(financial_metrics)

    if metrics:
        return metrics, None
    return {}, "; ".join(errors) if errors else "no Nasdaq fundamental data"


def fetch_public_fundamental_metrics(ticker: str, asset_class: str) -> Tuple[Dict[str, Any], Optional[str], Optional[str]]:
    nasdaq_metrics, nasdaq_error = fetch_nasdaq_fundamental_metrics(ticker, asset_class)
    if nasdaq_metrics:
        return nasdaq_metrics, None, "Nasdaq public summary/financial APIs"

    yahoo_metrics, yahoo_error = fetch_quote_summary_metrics(ticker)
    if yahoo_metrics:
        return yahoo_metrics, None, "Yahoo Finance public quote summary API"

    errors = []
    if nasdaq_error:
        errors.append(nasdaq_error)
    if yahoo_error:
        errors.append(f"Yahoo quote summary: {yahoo_error}")
    return {}, "; ".join(errors) if errors else "no public fundamental data", None


def merge_if_missing(target: Dict[str, Any], source: Dict[str, Any], fields: Iterable[str], source_name: str) -> None:
    for field in fields:
        value = source.get(field)
        if value is None:
            continue
        if is_missing(target.get(field)):
            target[field] = value
            target.setdefault("_sources", set()).add(source_name)


def enrich_one(row: Dict[str, Any], offline: bool = False, fetch_fundamentals: bool = True) -> Dict[str, Any]:
    enriched = dict(row)
    enriched["_sources"] = set(["local watchlist"])
    enriched["_fetch_errors"] = []

    if offline:
        enriched["_fetch_errors"].append("offline mode: public data fetch skipped")
        return enriched

    ticker = clean_text(enriched.get("ticker")).upper()
    asset_class = nasdaq_asset_class(enriched)

    price_metrics, price_error, price_source = fetch_public_price_metrics(ticker, asset_class)
    if price_error:
        enriched["_fetch_errors"].append(f"price history: {price_error}")
    else:
        merge_if_missing(enriched, price_metrics, price_metrics.keys(), price_source or "public price history")

    if fetch_fundamentals:
        fundamental_metrics, fundamental_error, fundamental_source = fetch_public_fundamental_metrics(ticker, asset_class)
        if fundamental_error:
            enriched["_fetch_errors"].append(f"fundamentals: {fundamental_error}")
        else:
            merge_if_missing(
                enriched,
                fundamental_metrics,
                fundamental_metrics.keys(),
                fundamental_source or "public fundamentals",
            )

    return enriched


def enrich_watchlist(rows: List[Dict[str, Any]], offline: bool = False, workers: int = 8) -> List[Dict[str, Any]]:
    if offline:
        return [enrich_one(row, offline=True) for row in rows]

    enriched_rows: List[Optional[Dict[str, Any]]] = [None] * len(rows)
    max_workers = max(1, min(workers, len(rows)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(enrich_one, row, False, True): index for index, row in enumerate(rows)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            try:
                enriched_rows[index] = future.result()
            except Exception as exc:
                failed = dict(rows[index])
                failed["_sources"] = set(["local watchlist"])
                failed["_fetch_errors"] = [f"unexpected enrichment error: {type(exc).__name__}: {exc}"]
                enriched_rows[index] = failed
    return [row for row in enriched_rows if row is not None]


def fetch_market_metrics(offline: bool = False) -> Dict[str, Dict[str, Any]]:
    tickers = ["SPY", "QQQ", "SMH"]
    if offline:
        metrics = {ticker: {"_fetch_errors": ["offline mode"]} for ticker in tickers}
        metrics["^TNX"] = {"_fetch_errors": ["offline mode"]}
        return metrics

    metrics: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {executor.submit(fetch_public_price_metrics, ticker, nasdaq_asset_class(ticker)): ticker for ticker in tickers}
        for future in as_completed(future_map):
            ticker = future_map[future]
            try:
                result, error, _source = future.result()
            except Exception as exc:
                result, error = {}, f"{type(exc).__name__}: {exc}"
            if error:
                result["_fetch_errors"] = [error]
            metrics[ticker] = result
    metrics["^TNX"] = {"_fetch_errors": ["rates data unavailable; neutral score used"]}
    return metrics


def percentile_score(values: List[float], value: Optional[float], high_is_good: bool = True) -> float:
    clean_values = sorted(v for v in values if v is not None and math.isfinite(v))
    if value is None or not clean_values:
        return 50.0
    less = sum(1 for item in clean_values if item < value)
    equal = sum(1 for item in clean_values if item == value)
    percentile = (less + 0.5 * equal) / len(clean_values) * 100.0
    return clamp(percentile if high_is_good else 100.0 - percentile)


def market_trend_score(metrics: Dict[str, Any]) -> float:
    price = parse_float(metrics.get("price"))
    ma20 = parse_float(metrics.get("ma20"))
    ma50 = parse_float(metrics.get("ma50"))
    ma200 = parse_float(metrics.get("ma200"))
    ret20 = parse_float(metrics.get("20d_return"))
    ret63 = parse_float(metrics.get("63d_return"))

    components = [
        (bool_score(price is not None and ma50 is not None and price >= ma50), 0.20),
        (bool_score(price is not None and ma200 is not None and price >= ma200), 0.25),
        (bool_score(ma20 is not None and ma50 is not None and ma20 >= ma50), 0.15),
        (bool_score(ma50 is not None and ma200 is not None and ma50 >= ma200), 0.20),
        (linear_score(ret20, -8.0, 8.0), 0.10),
        (linear_score(ret63, -15.0, 15.0), 0.10),
    ]
    return round_score(sum(score * weight for score, weight in components))


def compute_market_gate(rows: List[Dict[str, Any]], market_metrics: Dict[str, Dict[str, Any]]) -> Tuple[float, Dict[str, float]]:
    spy_trend = market_trend_score(market_metrics.get("SPY", {}))
    qqq_trend = market_trend_score(market_metrics.get("QQQ", {}))
    smh_trend = market_trend_score(market_metrics.get("SMH", {}))

    breadth_flags = []
    for row in rows:
        price = as_number(row, "price")
        ma50 = as_number(row, "ma50")
        if price is not None and ma50 is not None:
            breadth_flags.append(price >= ma50)
    breadth = sum(1 for item in breadth_flags if item) / len(breadth_flags) * 100.0 if breadth_flags else 50.0

    spy_vol = parse_float(market_metrics.get("SPY", {}).get("realized_vol_20d"))
    volatility = inverse_linear_score(spy_vol, good=12.0, bad=40.0)

    tnx_ret20 = parse_float(market_metrics.get("^TNX", {}).get("20d_return"))
    rates = inverse_linear_score(tnx_ret20, good=-10.0, bad=10.0)

    market_gate = (
        0.30 * spy_trend
        + 0.25 * qqq_trend
        + 0.20 * smh_trend
        + 0.10 * breadth
        + 0.10 * volatility
        + 0.05 * rates
    )
    details = {
        "SPY_Trend": round_score(spy_trend),
        "QQQ_Trend": round_score(qqq_trend),
        "SMH_Trend": round_score(smh_trend),
        "Breadth": round_score(breadth),
        "Volatility": round_score(volatility),
        "Rates": round_score(rates),
    }
    return round_score(market_gate), details


def score_quality(row: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    fcf_yield = as_number(row, "fcf_yield")
    revenue_growth = as_number(row, "revenue_growth")
    gross_margin = as_number(row, "gross_margin")
    operating_margin = as_number(row, "operating_margin")
    net_debt_to_ebitda = as_number(row, "net_debt_to_ebitda")
    dilution = as_number(row, "shares_yoy_change")
    buyback = as_number(row, "buyback_or_dilution")

    fcf_score = linear_score(fcf_yield, bad=-5.0, good=10.0)
    revenue_score = linear_score(revenue_growth, bad=-10.0, good=40.0)
    gross_score = linear_score(gross_margin, bad=20.0, good=80.0)
    operating_score = linear_score(operating_margin, bad=-20.0, good=40.0)

    if net_debt_to_ebitda is None:
        balance_score = 50.0
    elif net_debt_to_ebitda <= 0:
        balance_score = 100.0
    elif net_debt_to_ebitda <= 1:
        balance_score = 80.0
    elif net_debt_to_ebitda <= 2.5:
        balance_score = 60.0
    elif net_debt_to_ebitda <= 4:
        balance_score = 35.0
    else:
        balance_score = 10.0

    if buyback is not None:
        buyback_score = linear_score(buyback, bad=-5.0, good=5.0)
    elif dilution is not None:
        buyback_score = inverse_linear_score(dilution, good=-5.0, bad=8.0)
    else:
        buyback_score = 50.0

    quality = (
        0.30 * fcf_score
        + 0.20 * revenue_score
        + 0.15 * gross_score
        + 0.15 * operating_score
        + 0.10 * balance_score
        + 0.10 * buyback_score
    )
    details = {
        "FCF_Yield_Score": round_score(fcf_score),
        "Revenue_Growth_Score": round_score(revenue_score),
        "Gross_Margin_Score": round_score(gross_score),
        "Operating_Margin_Score": round_score(operating_score),
        "Balance_Sheet_Score": round_score(balance_score),
        "Buyback_or_Dilution_Score": round_score(buyback_score),
    }
    return round_score(quality), details


def score_valuation(
    row: Dict[str, Any],
    fcf_values: List[float],
    ev_sales_values: List[float],
    forward_pe_values: List[float],
    peg_values: List[float],
) -> Tuple[float, Dict[str, float]]:
    fcf_yield = as_number(row, "fcf_yield")
    ev_to_sales = as_number(row, "ev_to_sales")
    forward_pe = as_number(row, "forward_pe")
    revenue_growth = as_number(row, "revenue_growth")
    peg = None
    if forward_pe is not None and revenue_growth is not None and revenue_growth > 0:
        peg = forward_pe / revenue_growth
        row["_peg"] = peg

    historical_discount = as_number(row, "historical_valuation_discount")
    fcf_percentile = percentile_score(fcf_values, fcf_yield, high_is_good=True)
    ev_sales_inverse = percentile_score(ev_sales_values, ev_to_sales, high_is_good=False)
    forward_pe_inverse = percentile_score(forward_pe_values, forward_pe, high_is_good=False)
    peg_inverse = percentile_score(peg_values, peg, high_is_good=False)
    historical_discount_score = linear_score(historical_discount, bad=-20.0, good=30.0)

    valuation = (
        0.35 * fcf_percentile
        + 0.20 * ev_sales_inverse
        + 0.20 * forward_pe_inverse
        + 0.15 * peg_inverse
        + 0.10 * historical_discount_score
    )
    details = {
        "FCF_Yield_Percentile": round_score(fcf_percentile),
        "EV_to_Sales_Inverse": round_score(ev_sales_inverse),
        "Forward_PE_Inverse": round_score(forward_pe_inverse),
        "PEG_Inverse": round_score(peg_inverse),
        "Historical_Valuation_Discount": round_score(historical_discount_score),
    }
    return round_score(valuation), details


def score_trend(row: Dict[str, Any], spy_20d_return: Optional[float]) -> Tuple[float, Dict[str, float]]:
    price = as_number(row, "price")
    ma20 = as_number(row, "ma20")
    ma50 = as_number(row, "ma50")
    ma200 = as_number(row, "ma200")
    ret20 = as_number(row, "20d_return")
    volume = as_number(row, "volume")
    avg_volume = as_number(row, "average_volume")

    price_above_ma20 = bool_score(price is not None and ma20 is not None and price >= ma20)
    ma20_above_ma50 = bool_score(ma20 is not None and ma50 is not None and ma20 >= ma50)
    ma50_above_ma200 = bool_score(ma50 is not None and ma200 is not None and ma50 >= ma200)
    relative_strength = linear_score(None if ret20 is None or spy_20d_return is None else ret20 - spy_20d_return, -10.0, 10.0)

    if volume is None or avg_volume in (None, 0):
        volume_score = 50.0
    else:
        ratio = volume / avg_volume
        if ratio >= 1.25:
            volume_score = 100.0
        elif ratio >= 1.0:
            volume_score = 75.0
        elif ratio >= 0.8:
            volume_score = 50.0
        else:
            volume_score = 25.0

    trend = (
        0.25 * price_above_ma20
        + 0.25 * ma20_above_ma50
        + 0.20 * ma50_above_ma200
        + 0.15 * relative_strength
        + 0.15 * volume_score
    )
    details = {
        "Price_Above_MA20": round_score(price_above_ma20),
        "MA20_Above_MA50": round_score(ma20_above_ma50),
        "MA50_Above_MA200": round_score(ma50_above_ma200),
        "Relative_Strength_20D": round_score(relative_strength),
        "Volume_Confirmation": round_score(volume_score),
    }
    return round_score(trend), details


def score_catalyst(row: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    analyst_revision = clean_text(row.get("analyst_revision"))
    news = clean_text(row.get("news_catalyst")).lower()

    revision_number = parse_float(analyst_revision)
    if revision_number is not None:
        revision_score = linear_score(revision_number, bad=-3.0, good=3.0)
    elif analyst_revision:
        lowered = analyst_revision.lower()
        if any(word in lowered for word in ["upgrade", "raise", "positive", "beat"]):
            revision_score = 70.0
        elif any(word in lowered for word in ["downgrade", "cut", "negative", "miss"]):
            revision_score = 30.0
        else:
            revision_score = 50.0
    else:
        revision_score = 50.0

    if not news:
        news_score = 50.0
    elif any(word in news for word in ["upgrade", "contract", "approval", "beat", "guidance", "buyback", "launch"]):
        news_score = 75.0
    elif any(word in news for word in ["probe", "lawsuit", "cut", "delay", "miss", "resignation", "halt"]):
        news_score = 25.0
    else:
        news_score = 55.0

    earnings_days = days_to_event(row.get("earnings_date"))
    if earnings_days is not None and 0 <= earnings_days <= 30:
        earnings_catalyst = 55.0
    else:
        earnings_catalyst = 50.0

    catalyst = 0.45 * revision_score + 0.40 * news_score + 0.15 * earnings_catalyst
    details = {
        "Analyst_Revision": round_score(revision_score),
        "News_Catalyst": round_score(news_score),
        "Earnings_Catalyst": round_score(earnings_catalyst),
    }
    return round_score(catalyst), details


def score_options(row: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    iv_rank = as_number(row, "iv_rank")
    iv_minus_hv = as_number(row, "iv_minus_hv")
    volume = as_number(row, "volume")
    price = as_number(row, "price")
    ma50 = as_number(row, "ma50")
    ma200 = as_number(row, "ma200")
    skew_edge_input = as_number(row, "skew_edge")

    iv_rank_score = clamp(iv_rank) if iv_rank is not None else 50.0
    iv_realized_score = linear_score(iv_minus_hv, bad=-20.0, good=30.0)

    if volume is None:
        option_liquidity = 50.0
    elif volume >= 5_000_000:
        option_liquidity = 90.0
    elif volume >= 1_000_000:
        option_liquidity = 75.0
    elif volume >= 300_000:
        option_liquidity = 55.0
    elif volume >= 100_000:
        option_liquidity = 35.0
    else:
        option_liquidity = 20.0

    skew_edge = clamp(skew_edge_input) if skew_edge_input is not None else 50.0

    support_candidates = [value for value in [ma50, ma200] if value is not None and value > 0]
    if price is None or not support_candidates:
        support_distance = 50.0
    else:
        support = max(value for value in support_candidates if value <= price) if any(value <= price for value in support_candidates) else max(support_candidates)
        distance = (price / support - 1.0) * 100.0 if support else None
        if distance is None:
            support_distance = 50.0
        elif 0 <= distance <= 8:
            support_distance = 85.0
        elif 8 < distance <= 20:
            support_distance = 65.0
        elif distance < 0:
            support_distance = 35.0
        else:
            support_distance = 35.0

    options = (
        0.35 * iv_rank_score
        + 0.25 * iv_realized_score
        + 0.20 * option_liquidity
        + 0.10 * skew_edge
        + 0.10 * support_distance
    )
    details = {
        "IV_Rank": round_score(iv_rank_score),
        "IV_minus_RealizedVol": round_score(iv_realized_score),
        "Option_Liquidity": round_score(option_liquidity),
        "Skew_Edge": round_score(skew_edge),
        "Support_Distance": round_score(support_distance),
    }
    return round_score(options), details


def parse_date(value: Any) -> Optional[dt.date]:
    if is_missing(value):
        return None
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)) and value > 10_000_000:
        try:
            return dt.datetime.utcfromtimestamp(float(value)).date()
        except (OSError, ValueError):
            return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def days_to_event(value: Any, today: Optional[dt.date] = None) -> Optional[int]:
    event_date = parse_date(value)
    if event_date is None:
        return None
    today = today or dt.date.today()
    return (event_date - today).days


def compute_risk_penalty(row: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    price = as_number(row, "price")
    ma20 = as_number(row, "ma20")
    ma200 = as_number(row, "ma200")
    rsi_14 = as_number(row, "rsi_14")
    ret20 = as_number(row, "20d_return")
    ret63 = as_number(row, "63d_return")
    ret250 = as_number(row, "250d_return")
    fcf_yield = as_number(row, "fcf_yield")
    ev_to_sales = as_number(row, "ev_to_sales")
    ps = as_number(row, "ps")
    forward_pe = as_number(row, "forward_pe")
    revenue_growth = as_number(row, "revenue_growth")
    volume = as_number(row, "volume")
    avg_volume = as_number(row, "average_volume")
    atr_14 = as_number(row, "atr_14")
    drawdown = as_number(row, "drawdown_from_252d_high")
    gap_up_2atr = bool(row.get("gap_up_2atr"))

    reasons: List[str] = []

    overvaluation = 0.0
    if ev_to_sales is not None and ev_to_sales > 20:
        overvaluation += 15
        reasons.append("EV/Sales above 20")
    if ps is not None and ps > 20:
        overvaluation += 10
        reasons.append("P/S above 20")
    if forward_pe is not None and forward_pe > 70:
        overvaluation += 10
        reasons.append("forward P/E above 70")
    if fcf_yield is not None and fcf_yield <= 0 and ev_to_sales is not None and ev_to_sales > 15:
        overvaluation += 15
        reasons.append("negative/zero FCF yield with high EV/Sales")
    if fcf_yield is not None and fcf_yield <= 0 and revenue_growth is not None and revenue_growth < 15:
        overvaluation += 10
        reasons.append("weak growth with non-positive FCF yield")

    overheat = 0.0
    if rsi_14 is not None and rsi_14 > 78:
        overheat += 20
        reasons.append("RSI_14 above 78")
    if price is not None and ma20 not in (None, 0) and price > ma20 * 1.12:
        overheat += 20
        reasons.append("price more than 12% above MA20")
    if ret20 is not None and ret20 > 40:
        overheat += 25
        reasons.append("20D return above 40%")
    if gap_up_2atr:
        overheat += 15
        reasons.append("gap up greater than 2x ATR")
    if ret250 is not None and ret250 > 200 and fcf_yield is not None and fcf_yield <= 0:
        overheat += 25
        reasons.append("250D return above 200% with non-positive FCF yield")

    earnings_penalty = 0.0
    days = days_to_event(row.get("earnings_date"))
    if days is not None and 0 <= days <= 7:
        earnings_penalty += 25
        reasons.append("earnings within 7 calendar days")
    elif days is not None and 8 <= days <= 14:
        earnings_penalty += 10
        reasons.append("earnings within 14 calendar days")

    liquidity = 0.0
    if volume is None:
        liquidity += 10
        reasons.append("volume unavailable")
    elif volume < 100_000:
        liquidity += 25
        reasons.append("volume below 100K")
    elif volume < 300_000:
        liquidity += 15
        reasons.append("volume below 300K")
    if volume is not None and avg_volume not in (None, 0) and volume < 0.5 * avg_volume:
        liquidity += 10
        reasons.append("latest volume less than 50% of average")

    drawdown_penalty = 0.0
    if price is not None and ma200 is not None and price < ma200:
        drawdown_penalty += 20
        reasons.append("price below MA200")
    if ret63 is not None and ret63 < -20:
        drawdown_penalty += 15
        reasons.append("63D return below -20%")
    if drawdown is not None and drawdown < -25:
        drawdown_penalty += 15
        reasons.append("more than 25% below 252D high")

    gap_risk = 0.0
    if price not in (None, 0) and atr_14 is not None:
        atr_pct = atr_14 / price * 100.0
        if atr_pct > 10:
            gap_risk += 20
            reasons.append("ATR risk above 10% of price")
        elif atr_pct > 6:
            gap_risk += 12
            reasons.append("ATR risk above 6% of price")
        elif atr_pct > 4:
            gap_risk += 6
            reasons.append("ATR risk above 4% of price")

    total = min(100.0, overvaluation + overheat + earnings_penalty + liquidity + drawdown_penalty + gap_risk)
    details = {
        "OvervaluationPenalty": round(overvaluation, 2),
        "OverheatPenalty": round(overheat, 2),
        "EarningsEventPenalty": round(earnings_penalty, 2),
        "LiquidityPenalty": round(liquidity, 2),
        "DrawdownPenalty": round(drawdown_penalty, 2),
        "GapRiskPenalty": round(gap_risk, 2),
        "reasons": reasons,
    }
    return round(total, 2), details


def choose_strategy(
    ticker: str,
    is_etf: bool,
    market_score: float,
    final_score: float,
    quality_score: float,
    trend_score: float,
    options_score: float,
    risk_penalty: float,
) -> str:
    ticker = clean_text(ticker).upper()
    is_etf = is_etf or ticker in ETF_TICKERS
    if market_score >= 60 and final_score >= 75 and risk_penalty <= 20:
        return "Buy/Add"
    if is_etf and market_score >= 60 and trend_score >= 85 and risk_penalty <= 20 and final_score >= 60:
        return "ETF Trend Candidate"
    if not is_etf and market_score >= 60 and final_score >= 65 and risk_penalty <= 20:
        return "Ranked Buy Candidate"
    if quality_score >= 70 and final_score >= 60 and risk_penalty <= 30:
        return "High-Quality Watch"
    if final_score >= 60 and trend_score >= 70 and risk_penalty <= 35:
        return "Pullback Buy"
    if options_score >= 70 and risk_penalty <= 35:
        return "Defined-Risk Options"
    if final_score >= 55 and risk_penalty <= 50:
        return "Avoid Chase"
    return "Avoid"


def is_etf_row(row: Dict[str, Any]) -> bool:
    ticker = clean_text(row.get("ticker")).upper()
    sector = clean_text(row.get("sector")).lower()
    return ticker in ETF_TICKERS or sector == "etf"


def high_volatility_name(row: Dict[str, Any]) -> bool:
    price = as_number(row, "price")
    atr_14 = as_number(row, "atr_14")
    if price not in (None, 0) and atr_14 is not None and atr_14 / price > 0.06:
        return True
    sector = clean_text(row.get("sector")).lower()
    ticker = clean_text(row.get("ticker")).upper()
    return any(token in sector for token in ["high volatility", "crypto", "growth"]) or ticker in {"COIN", "MSTR", "IONQ", "SOUN", "SMCI", "ARKK"}


def position_size_text(row: Dict[str, Any], final_score: float, market_score: float, strategy: str) -> str:
    if strategy == "Buy/Add":
        return "Staged 5%-10% planned position; human review required"
    if strategy == "Ranked Buy Candidate":
        return "2%-4% starter only after human review"
    if strategy == "ETF Trend Candidate":
        return "Staggered ETF allocation; 5%-15% planned allocation only if suitable"
    if strategy == "High-Quality Watch":
        return "0% automatic; review valuation and catalyst"
    if strategy == "Pullback Buy":
        return "0% now; wait for 5%-12% pullback or consolidation"
    if strategy == "Avoid Chase":
        return "0%; wait/review"
    if strategy == "Avoid":
        return "0%"
    if strategy == "Defined-Risk Options":
        suffix = ""
        days = days_to_event(row.get("earnings_date"))
        if days is not None and 0 <= days <= 7:
            suffix = "; reduce 50% for earnings event risk"
        return "$500-$1,500 max spread risk; never exceed $5,000 max loss" + suffix

    price = as_number(row, "price")
    atr_14 = as_number(row, "atr_14")
    if price in (None, 0) or atr_14 in (None, 0):
        return "N/A - ATR unavailable"

    base_risk = 1.0
    atr_risk = max(atr_14 / price, 0.01)
    raw_size = base_risk * (final_score / 100.0) * (market_score / 100.0) / atr_risk
    cap = 5.0 if high_volatility_name(row) else 10.0

    days = days_to_event(row.get("earnings_date"))
    event_note = ""
    if days is not None and 0 <= days <= 7:
        raw_size *= 0.5
        event_note = "; reduced 50% for earnings"

    size = min(raw_size, cap)
    return f"{size:.1f}% of account; cap {cap:.0f}%{event_note}"


def entry_zone_text(row: Dict[str, Any], strategy: str) -> str:
    price = as_number(row, "price")
    atr_14 = as_number(row, "atr_14")
    ma20 = as_number(row, "ma20")
    ma50 = as_number(row, "ma50")
    ma200 = as_number(row, "ma200")

    if strategy == "Avoid":
        return "N/A - no entry"
    if strategy == "Avoid Chase":
        return "No entry; wait for reset, pullback, or improved risk/reward"
    if strategy == "Defined-Risk Options":
        supports = [value for value in [ma50, ma200] if value is not None and value > 0]
        support = max(supports) if supports else None
        return (
            f"Defined-risk put credit spread below support near {fmt_price(support)}; "
            "target 0.20-0.30 short delta; 30-45 DTE"
        )
    if strategy == "High-Quality Watch":
        return "No automatic entry; review valuation, catalyst, and missing data first"
    if strategy == "ETF Trend Candidate":
        return "Stagger allocation across tranches; avoid chasing extended daily moves"
    if strategy == "Pullback Buy":
        return "Wait for 5%-12% pullback or consolidation before entry"
    if strategy == "Ranked Buy Candidate":
        if price is None:
            return "Starter only after human review; price unavailable"
        upper = price + (0.25 * atr_14 if atr_14 is not None else 0)
        return f"Starter review zone near {fmt_price(price)} to {fmt_price(upper)}; no automatic buy"
    if price is None:
        return "N/A - price unavailable"
    upper = price + (0.5 * atr_14 if atr_14 is not None else 0)
    lower = min(price, ma20) if ma20 is not None else price
    return f"{fmt_price(lower)} to {fmt_price(upper)}"


def stop_or_exit_text(row: Dict[str, Any], strategy: str) -> str:
    price = as_number(row, "price")
    atr_14 = as_number(row, "atr_14")
    ma50 = as_number(row, "ma50")
    ma200 = as_number(row, "ma200")

    if strategy == "Avoid":
        return "No trade; revisit after score and risk improve"
    if strategy == "Avoid Chase":
        return "No trade; wait for lower-risk setup or score improvement"
    if strategy == "High-Quality Watch":
        return "No automatic trade; require human review of valuation, catalyst, and data gaps"
    if strategy == "ETF Trend Candidate":
        return "Use staggered tranches; reduce if trend breaks below MA50 or risk rises"
    if strategy == "Ranked Buy Candidate":
        return "Human review required; stop or reduce if price breaks MA50 or score falls below 60"
    if strategy == "Pullback Buy":
        return "No entry now; reassess after 5%-12% pullback, base, or trend reset"
    if strategy == "Defined-Risk Options":
        return (
            "Max gain = net credit; max loss = spread width minus credit; breakeven = short strike minus credit; "
            "exit at 50-70% max profit, stop near 2x credit loss, close/reduce before earnings"
        )
    stop_candidates = []
    if price is not None and atr_14 is not None:
        stop_candidates.append(price - 2.0 * atr_14)
    if ma50 is not None:
        stop_candidates.append(ma50)
    if not stop_candidates and ma200 is not None:
        stop_candidates.append(ma200)
    if not stop_candidates:
        return "N/A - stop data unavailable; use human-defined exit"
    stop = min(stop_candidates)
    return f"Exit below {fmt_price(stop)} or if final score falls below 60"


def confidence_label(row: Dict[str, Any], final_score: float) -> str:
    available = 0
    applicable = 0
    for field in DATA_FIELDS:
        if field in {"ticker", "name", "sector"}:
            continue
        applicable += 1
        if not is_missing(row.get(field)):
            available += 1
    coverage = available / applicable if applicable else 0
    if coverage >= 0.75 and final_score >= 70:
        return "High"
    if coverage >= 0.45:
        return "Medium"
    return "Low"


def key_reason(row: Dict[str, Any], scores: Dict[str, float]) -> str:
    reasons = []
    if scores["market_score"] >= 65:
        reasons.append("constructive market gate")
    if scores["quality_score"] >= 70:
        reasons.append("strong quality factors")
    if scores["valuation_score"] >= 65:
        reasons.append("valuation support")
    if scores["trend_score"] >= 70:
        reasons.append("positive trend and relative strength")
    if scores["catalyst_score"] >= 60:
        reasons.append("positive catalyst inputs")
    if scores["options_score"] >= 70:
        reasons.append("defined-risk options setup screened well")
    if not reasons:
        reasons.append("insufficient edge after neutral/missing inputs")
    source_count = len(row.get("_sources", []))
    data_note = "multi-source inputs" if source_count > 1 else "limited local inputs"
    return "; ".join(reasons[:3]) + f"; {data_note}"


def key_risk(row: Dict[str, Any], risk_details: Dict[str, Any]) -> str:
    reasons = risk_details.get("reasons") or []
    if not reasons:
        risk = "No single dominant modeled risk"
    else:
        risk = "; ".join(reasons[:4])
    return f"{risk}. {CSV_DISCLAIMER}"


def data_gaps(row: Dict[str, Any]) -> List[str]:
    gaps = []
    for field in DATA_FIELDS:
        if field == "ticker":
            continue
        if is_missing(row.get(field)):
            gaps.append(field)
    return gaps


def cad_mapping_for_ticker(ticker: str) -> Tuple[str, str]:
    return CAD_MAPPING.get(clean_text(ticker).upper(), (NO_CAD_MAPPING, NO_CAD_MAPPING_NOTE))


def compute_scores(rows: List[Dict[str, Any]], market_metrics: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    market_score, market_details = compute_market_gate(rows, market_metrics)
    spy_20d = parse_float(market_metrics.get("SPY", {}).get("20d_return"))

    fcf_values = [as_number(row, "fcf_yield") for row in rows]
    ev_sales_values = [as_number(row, "ev_to_sales") for row in rows]
    forward_pe_values = [as_number(row, "forward_pe") for row in rows]
    peg_values = []
    for row in rows:
        forward_pe = as_number(row, "forward_pe")
        revenue_growth = as_number(row, "revenue_growth")
        if forward_pe is not None and revenue_growth is not None and revenue_growth > 0:
            peg_values.append(forward_pe / revenue_growth)

    scored: List[Dict[str, Any]] = []
    for row in rows:
        quality_score, quality_details = score_quality(row)
        valuation_score, valuation_details = score_valuation(row, fcf_values, ev_sales_values, forward_pe_values, peg_values)
        trend_score, trend_details = score_trend(row, spy_20d)
        catalyst_score, catalyst_details = score_catalyst(row)
        options_score, options_details = score_options(row)
        risk_penalty, risk_details = compute_risk_penalty(row)

        final_score = (
            0.20 * market_score
            + 0.20 * quality_score
            + 0.15 * valuation_score
            + 0.20 * trend_score
            + 0.10 * catalyst_score
            + 0.10 * options_score
            - 0.15 * risk_penalty
        )
        final_score = round_score(final_score)
        strategy = choose_strategy(
            row["ticker"],
            is_etf_row(row),
            market_score,
            final_score,
            quality_score,
            trend_score,
            options_score,
            risk_penalty,
        )

        score_payload = {
            "market_score": market_score,
            "quality_score": quality_score,
            "valuation_score": valuation_score,
            "trend_score": trend_score,
            "catalyst_score": catalyst_score,
            "options_score": options_score,
        }
        cad_alternative, cad_note = cad_mapping_for_ticker(row["ticker"])

        output = {
            "ticker": row["ticker"],
            "final_score": final_score,
            "market_score": market_score,
            "quality_score": quality_score,
            "valuation_score": valuation_score,
            "trend_score": trend_score,
            "catalyst_score": catalyst_score,
            "options_score": options_score,
            "risk_penalty": round(risk_penalty, 2),
            "strategy": strategy,
            "confidence": confidence_label(row, final_score),
            "position_size": position_size_text(row, final_score, market_score, strategy),
            "entry_zone": entry_zone_text(row, strategy),
            "stop_or_exit": stop_or_exit_text(row, strategy),
            "key_reason": key_reason(row, score_payload),
            "key_risk": key_risk(row, risk_details),
            "cad_alternative": cad_alternative,
            "cad_note": cad_note,
            "_row": row,
            "_quality_details": quality_details,
            "_valuation_details": valuation_details,
            "_trend_details": trend_details,
            "_catalyst_details": catalyst_details,
            "_options_details": options_details,
            "_risk_details": risk_details,
            "_data_gaps": data_gaps(row),
        }
        scored.append(output)

    scored.sort(key=lambda item: (item["final_score"], -item["risk_penalty"]), reverse=True)
    context = {
        "market_score": market_score,
        "market_details": market_details,
        "market_metrics": market_metrics,
    }
    return scored, context


def write_scores(path: Path, scored_rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCORE_COLUMNS)
        writer.writeheader()
        for row in scored_rows:
            writer.writerow({column: row[column] for column in SCORE_COLUMNS})


def regime_label(market_score: float) -> str:
    if market_score >= 70:
        return "Risk-on / constructive"
    if market_score >= 55:
        return "Neutral / selective"
    return "Defensive / cash discipline"


def markdown_table(rows: List[Dict[str, Any]], columns: List[Tuple[str, str]], limit: int = 10) -> str:
    selected = rows[:limit]
    headers = [label for label, _ in columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    if not selected:
        lines.append("| " + " | ".join(["None"] + [""] * (len(headers) - 1)) + " |")
        return "\n".join(lines)
    for row in selected:
        values = []
        for _, key in columns:
            value = row.get(key, "")
            text = str(value).replace("\n", " ").replace("|", "/")
            values.append(text)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def strategy_rows(scored: List[Dict[str, Any]], strategy: str) -> List[Dict[str, Any]]:
    return [row for row in scored if row["strategy"] == strategy]


def avoid_rows(scored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in scored if row["strategy"] == "Avoid"]


def report_data_gaps(scored: List[Dict[str, Any]]) -> str:
    field_counts: Dict[str, int] = {}
    ticker_gaps: List[Tuple[str, List[str]]] = []
    for row in scored:
        gaps = row.get("_data_gaps", [])
        ticker_gaps.append((row["ticker"], gaps))
        for gap in gaps:
            field_counts[gap] = field_counts.get(gap, 0) + 1

    if not field_counts:
        return "No material data gaps detected."

    top_fields = sorted(field_counts.items(), key=lambda item: item[1], reverse=True)[:12]
    lines = ["Most common unavailable fields marked as N/A or neutral in scoring:"]
    lines.extend(f"- {field}: missing for {count} tickers" for field, count in top_fields)

    most_gap_tickers = sorted(ticker_gaps, key=lambda item: len(item[1]), reverse=True)[:8]
    lines.append("")
    lines.append("Tickers with the widest data gaps:")
    for ticker, gaps in most_gap_tickers:
        shown = ", ".join(gaps[:10])
        suffix = "..." if len(gaps) > 10 else ""
        lines.append(f"- {ticker}: {shown}{suffix}")
    return "\n".join(lines)


def report_risk_notes(scored: List[Dict[str, Any]]) -> str:
    risky = sorted(scored, key=lambda row: row["risk_penalty"], reverse=True)[:10]
    lines = []
    for row in risky:
        reasons = row.get("_risk_details", {}).get("reasons") or ["No single dominant modeled risk"]
        lines.append(f"- {row['ticker']}: risk penalty {row['risk_penalty']} - {'; '.join(reasons[:4])}")
    return "\n".join(lines)


def report_cad_alternatives() -> str:
    lines = [
        "| Exposure | CAD-listed alternatives to verify | Notes |",
        "| --- | --- | --- |",
    ]
    for item in CAD_ALTERNATIVES:
        lines.append(f"| {item['exposure']} | {item['tickers']} | {item['note']} |")
    return "\n".join(lines)


def report_top_cad_mappings(scored: List[Dict[str, Any]], limit: int = 20) -> str:
    columns = [
        ("Ticker", "ticker"),
        ("Strategy", "strategy"),
        ("Final", "final_score"),
        ("Risk", "risk_penalty"),
        ("CAD Alternative", "cad_alternative"),
        ("CAD Note", "cad_note"),
    ]
    return markdown_table(scored, columns, limit)


def options_plan(row: Dict[str, Any]) -> str:
    ticker = row["ticker"]
    entry = row["entry_zone"]
    return (
        f"- {ticker}: {entry}. Max loss = spread width minus credit; max gain = net credit; "
        "breakeven = short put strike minus credit; target 0.20-0.30 short delta; "
        "30-45 DTE; exit at 50-70% max profit or near 2x credit loss. "
        "Avoid premium selling directly before earnings unless the spread is explicitly defined-risk."
    )


def write_report(path: Path, scored: List[Dict[str, Any]], context: Dict[str, Any], source_label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    market_score = context["market_score"]
    market_details = context["market_details"]
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    top_columns = [
        ("Ticker", "ticker"),
        ("Final", "final_score"),
        ("Strategy", "strategy"),
        ("Risk", "risk_penalty"),
        ("Confidence", "confidence"),
        ("Position", "position_size"),
        ("Reason", "key_reason"),
    ]
    options_columns = [
        ("Ticker", "ticker"),
        ("Final", "final_score"),
        ("Options", "options_score"),
        ("Risk", "risk_penalty"),
        ("Entry", "entry_zone"),
        ("Exit", "stop_or_exit"),
    ]
    avoid_columns = [
        ("Ticker", "ticker"),
        ("Final", "final_score"),
        ("Risk", "risk_penalty"),
        ("Key Risk", "key_risk"),
    ]

    buy_add = strategy_rows(scored, "Buy/Add")
    ranked_buy = strategy_rows(scored, "Ranked Buy Candidate")
    etf_trend = strategy_rows(scored, "ETF Trend Candidate")
    high_quality_watch = strategy_rows(scored, "High-Quality Watch")
    pullbacks = strategy_rows(scored, "Pullback Buy")
    defined_risk = strategy_rows(scored, "Defined-Risk Options")
    avoid_chase = strategy_rows(scored, "Avoid Chase")
    avoid = avoid_rows(scored)

    option_plan_text = "\n".join(options_plan(row) for row in defined_risk[:10])
    if not option_plan_text:
        option_plan_text = "No defined-risk options candidates passed the score and risk thresholds. No naked options are recommended."

    report = f"""# Daily Investment Ranking Report

Generated: {generated}

{DISCLAIMER_LINES[0]}

{DISCLAIMER_LINES[1]}

{DISCLAIMER_LINES[2]}

Research-only output. No brokerage execution, no private-account scraping, no margin use, and no trade placement are performed.

## Market Regime Summary

- MarketGateScore: {market_score}
- Regime: {regime_label(market_score)}
- SPY_Trend: {market_details['SPY_Trend']}
- QQQ_Trend: {market_details['QQQ_Trend']}
- SMH_Trend: {market_details['SMH_Trend']}
- Breadth: {market_details['Breadth']}
- Volatility: {market_details['Volatility']}
- Rates: {market_details['Rates']}
- Data source used: {source_label}

## CAD Alternatives For Top Ranked Names

CAD alternatives must be verified in the broker before trading. CDRs may have different liquidity, spread, CDR ratio, and hedging behavior than the U.S. underlying.

{report_top_cad_mappings(scored, 20)}

## Top 10 Buy/Add

{markdown_table(buy_add, top_columns, 10)}

## Top 10 Ranked Buy Candidate

Eligible for human review and possible small staged starter entries; not automatic buy signals.

{markdown_table(ranked_buy, top_columns, 10)}

## Top 10 ETF Trend Candidate

Constructive ETF trend candidates for staggered allocation review; not automatic buy signals.

{markdown_table(etf_trend, top_columns, 10)}

## Top 10 High-Quality Watch

Quality screens well, but valuation, trend, catalyst, risk, or data gaps do not support immediate buying.

{markdown_table(high_quality_watch, top_columns, 10)}

## Top 10 Pullback Buy

{markdown_table(pullbacks, top_columns, 10)}

## Top 10 Defined-Risk Options

{markdown_table(defined_risk, options_columns, 10)}

Options strategy notes:

{option_plan_text}

## Avoid Chase List

Do not chase current price. Wait for pullback, consolidation, risk improvement, or better data.

{markdown_table(avoid_chase, avoid_columns, 10)}

## Avoid List

{markdown_table(avoid, avoid_columns, 10)}

## CAD-listed Alternatives If Available

Availability, fees, holdings, currency hedge status, and liquidity must be verified before use.

{report_cad_alternatives()}

## Risk Notes

{report_risk_notes(scored)}

## Data Gaps

{report_data_gaps(scored)}

## Final Human-review Checklist

- Confirm the CSV watchlist loaded successfully.
- Confirm all ticker symbols are correct and tradable in the intended market.
- Confirm no final score is NaN or blank.
- Confirm every generated strategy has a risk_penalty.
- Confirm every options idea is defined-risk; no naked options.
- Check live price, spread, volume, news, and earnings timing before acting.
- Validate any CAD-listed alternative for liquidity, fees, holdings, and hedge status.
- Keep max single stock position at or below 10% for core names and 5% for high-volatility names.
- Keep single spread risk within the user-defined limit, default $500-$1,500, and never above $5,000 max loss.
- Treat this as research only: Not financial advice; Model output requires human review; Data quality may affect results.
"""
    path.write_text(report, encoding="utf-8")


def split_memberships(value: str) -> List[str]:
    memberships = []
    for part in clean_text(value).replace(",", ";").split(";"):
        item = part.strip()
        if item:
            memberships.append(item)
    return memberships


def load_index_universe(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Index universe not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [canonicalize_row(row) for row in reader]
    if not rows:
        raise ValueError(f"Index universe is empty: {path}")

    deduped: Dict[str, Dict[str, Any]] = {}
    for index, row in enumerate(rows, start=2):
        ticker = clean_text(row.get("ticker")).upper()
        if not ticker:
            continue
        row["ticker"] = ticker
        existing = deduped.get(ticker)
        if not existing:
            deduped[ticker] = row
            continue
        merged_memberships = sorted(
            set(split_memberships(existing.get("index_memberships"))) | set(split_memberships(row.get("index_memberships")))
        )
        existing["index_memberships"] = "; ".join(merged_memberships)
        for field in ["company_name", "name", "sector", "industry", "theme", "source", "universe_tier"]:
            if not clean_text(existing.get(field)) and clean_text(row.get(field)):
                existing[field] = row[field]
        existing["_load_note"] = f"merged duplicate ticker from CSV row {index}"
    return sorted(deduped.values(), key=lambda item: item["ticker"])


def load_default_market_regime_score() -> float:
    if not DEFAULT_SCORES.exists():
        return 60.0
    try:
        with DEFAULT_SCORES.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        values = [parse_float(row.get("market_score")) for row in rows]
        numeric = [value for value in values if value is not None]
        if numeric:
            return round_score(statistics.mean(numeric))
    except Exception:
        return 60.0
    return 60.0


def load_index_earnings_lookup(path: Path = BASE_DIR / "outputs" / "index_weekly_earnings_calendar.csv") -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    lookup: Dict[str, Dict[str, Any]] = {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                ticker = clean_text(row.get("ticker")).upper()
                if ticker:
                    lookup[ticker] = canonicalize_row(row)
    except Exception:
        return {}
    return lookup


def expanded_prefilter_score(row: Dict[str, Any]) -> int:
    ticker = clean_text(row.get("ticker")).upper()
    memberships = set(split_memberships(row.get("index_memberships")))
    sector = clean_text(row.get("sector")).lower()
    theme = clean_text(row.get("theme")).lower()
    universe_tier = clean_text(row.get("universe_tier")).lower()
    source = clean_text(row.get("source")).lower()

    score = 0
    if "Local Watchlist" in memberships or "watchlist" in source:
        score += 40
    if universe_tier in {"theme_watch", "core_watchlist"}:
        score += 30
    if ticker in HIGH_PRIORITY_EXPANDED_TICKERS:
        score += 25
    if "Nasdaq-100" in memberships:
        score += 20
    if "Dow 30" in memberships:
        score += 18
    if "S&P 500" in memberships:
        score += 15
    if "semiconductor" in theme or "ai" in theme or "mega-cap" in theme:
        score += 20
    elif "software" in theme or "cybersecurity" in theme:
        score += 14
    if "information technology" in sector or "communication services" in sector:
        score += 10
    return score


def prefilter_expanded_candidates(rows: List[Dict[str, Any]], limit: int) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (-expanded_prefilter_score(row), clean_text(row.get("ticker")).upper()),
    )
    selected = ranked[:limit]
    metadata = {
        "source_rows": len(rows),
        "selected_rows": len(selected),
        "limit": limit,
        "method": (
            "Deterministic prefilter by local watchlist membership, universe tier, high-priority "
            "AI/semi/mega-cap tickers, index memberships, theme, sector, then ticker."
        ),
    }
    return selected, metadata


def expanded_data_quality_score(row: Dict[str, Any]) -> float:
    score = 35.0
    for field in ["company_name", "sector", "industry", "theme", "index_memberships", "source"]:
        if clean_text(row.get(field)):
            score += 9.0
    if clean_text(row.get("universe_tier")):
        score += 6.0
    return round_score(score)


def expanded_quality_score(row: Dict[str, Any]) -> float:
    theme = clean_text(row.get("theme")).lower()
    tier = clean_text(row.get("universe_tier")).lower()
    memberships = split_memberships(row.get("index_memberships"))
    ticker = clean_text(row.get("ticker")).upper()

    score = 55.0
    if tier == "theme_watch":
        score += 15.0
    elif tier == "core_watchlist":
        score += 12.0
    elif tier == "core_index":
        score += 8.0
    if len(memberships) >= 3:
        score += 12.0
    elif len(memberships) == 2:
        score += 8.0
    elif len(memberships) == 1:
        score += 4.0
    if ticker in HIGH_PRIORITY_EXPANDED_TICKERS:
        score += 8.0
    if "mega-cap" in theme or "semiconductor" in theme or "ai" in theme:
        score += 8.0
    elif "software" in theme or "cybersecurity" in theme:
        score += 5.0
    return round_score(score)


def expanded_earnings_status(ticker: str, earnings_lookup: Dict[str, Dict[str, Any]]) -> Tuple[float, str, List[str]]:
    row = earnings_lookup.get(ticker, {})
    data_status = clean_text(row.get("data_status"))
    days = parse_float(row.get("days_until_earnings"))
    earnings_date = clean_text(row.get("earnings_date"))
    flags: List[str] = []

    if earnings_date and earnings_date.upper() != "N/A" and days is not None and 0 <= days <= 7:
        flags.append(f"confirmed earnings event within {int(days)} days")
        return 20.0, "Earnings Event Risk", flags
    if data_status == "Data Gap / Watch":
        flags.append("earnings date not confirmed in index earnings radar")
        return 45.0, "", flags
    flags.append("earnings timing requires manual verification")
    return 50.0, "", flags


def expanded_action_bias(row: Dict[str, Any], action_score: float, data_quality_score: float, event_bias: str, risk_flags: List[str]) -> str:
    if event_bias:
        return event_bias
    if data_quality_score < 65:
        return "Data Gap Review"
    if action_score >= 76:
        return "Buy/Add Watch"
    if action_score >= 68:
        return "Pullback Buy Watch"
    if "No live price, valuation, or momentum feed used in expanded mode" in risk_flags and action_score < 58:
        return "Avoid Chase"
    if action_score >= 55:
        return "Hold / Monitor"
    if action_score >= 48:
        return "Reduce Risk Watch"
    return "Sell Review"


def expanded_confidence(data_quality_score: float, action_score: float) -> str:
    if data_quality_score >= 85 and action_score >= 70:
        return "Medium-High"
    if data_quality_score >= 70:
        return "Medium"
    return "Low"


def score_expanded_candidate(
    row: Dict[str, Any],
    market_regime_score: float,
    earnings_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    ticker = clean_text(row.get("ticker")).upper()
    company_name = clean_text(row.get("company_name")) or clean_text(row.get("name")) or "N/A"
    quality_score = expanded_quality_score(row)
    valuation_score = 50.0
    momentum_score = 50.0
    earnings_risk_score, event_bias, risk_flags = expanded_earnings_status(ticker, earnings_lookup)
    data_quality_score = expanded_data_quality_score(row)
    action_score = round_score(
        0.20 * quality_score
        + 0.10 * valuation_score
        + 0.15 * momentum_score
        + 0.15 * earnings_risk_score
        + 0.20 * data_quality_score
        + 0.20 * market_regime_score
    )
    risk_flags.extend(
        [
            "No live price, valuation, or momentum feed used in expanded mode",
            "No options data used; options analysis unavailable",
            "Research-only output requires human review",
        ]
    )
    action_bias = expanded_action_bias(row, action_score, data_quality_score, event_bias, risk_flags)
    memberships = clean_text(row.get("index_memberships")) or "N/A"
    theme = clean_text(row.get("theme")) or "Other"
    cad_alternative, cad_note = cad_mapping_for_ticker(ticker)
    primary_reason = (
        f"{company_name} is in {memberships}; theme={theme}; "
        f"deterministic prefilter score={expanded_prefilter_score(row)}."
    )
    invalidation_check = (
        "Verify ticker, index membership, earnings date, liquidity, and current price action before any action; "
        "re-run the full daily ranker or research desk if the thesis changes."
    )

    return {
        "ticker": ticker,
        "company_name": company_name,
        "sector": clean_text(row.get("sector")) or "N/A",
        "industry": clean_text(row.get("industry")) or "N/A",
        "theme": theme,
        "index_memberships": memberships,
        "source": clean_text(row.get("source")) or "N/A",
        "universe_tier": clean_text(row.get("universe_tier")) or "N/A",
        "quality_score": quality_score,
        "valuation_score": valuation_score,
        "momentum_score": momentum_score,
        "earnings_risk_score": earnings_risk_score,
        "data_quality_score": data_quality_score,
        "market_regime_score": market_regime_score,
        "action_score": action_score,
        "action_bias": action_bias,
        "confidence": expanded_confidence(data_quality_score, action_score),
        "primary_reason": primary_reason,
        "risk_flags": "; ".join(dict.fromkeys(risk_flags)),
        "invalidation_check": invalidation_check,
        "backtest_status": "not_run",
        "options_analysis_status": "unavailable",
        "options_bias": "No Options Analysis",
        "cad_alternative": cad_alternative,
        "cad_note": cad_note,
    }


def write_expanded_scores(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPANDED_SCORE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in EXPANDED_SCORE_COLUMNS})


def write_action_bias_explanation(path: Path) -> None:
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"""# Action Bias Explanation

Generated: {generated}

Not financial advice

Model output requires human review

Data quality may affect results

Research-only output. These labels are not trade orders and do not connect to a brokerage.

## Purpose

Expanded-universe mode turns the broad index universe into a research queue. It does not replace the default 38-row daily ranker and does not use live options analytics.

## Action Bias Labels

- Buy/Add Watch: candidate is high priority for human research review; no automatic entry.
- Pullback Buy Watch: candidate is constructive but should be reviewed for pullback/consolidation first.
- Hold / Monitor: maintain research visibility and wait for stronger evidence.
- Avoid Chase: do not chase current price; wait for better setup/data.
- Reduce Risk Watch: review exposure and risk because action evidence is weak.
- Sell Review: review thesis deterioration; this is not an order.
- Data Gap Review: missing data is too important to ignore.
- Earnings Event Risk: confirmed near-term earnings require timing/risk verification.

## Options Status

Expanded-universe mode sets options_analysis_status=unavailable and options_bias=No Options Analysis because it does not fetch real options chains, IV, Greeks, skew, or liquidity. It never recommends naked options.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_expanded_report(
    path: Path,
    rows: List[Dict[str, Any]],
    prefilter: Dict[str, Any],
    universe_path: Path,
    market_regime_score: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    action_counts: Dict[str, int] = {}
    for row in rows:
        action_counts[row["action_bias"]] = action_counts.get(row["action_bias"], 0) + 1
    counts_text = "\n".join(f"- {label}: {count}" for label, count in sorted(action_counts.items()))

    top_columns = [
        ("Ticker", "ticker"),
        ("Company", "company_name"),
        ("Action Score", "action_score"),
        ("Action Bias", "action_bias"),
        ("Confidence", "confidence"),
        ("Theme", "theme"),
        ("Reason", "primary_reason"),
    ]
    cad_columns = [
        ("Ticker", "ticker"),
        ("Action Bias", "action_bias"),
        ("CAD Alternative", "cad_alternative"),
        ("CAD Note", "cad_note"),
    ]
    gap_rows = [row for row in rows if row["action_bias"] == "Data Gap Review"]
    earnings_rows = [row for row in rows if row["action_bias"] == "Earnings Event Risk"]

    report = f"""# Expanded Universe Daily Investment Research Report

Generated: {generated}

Not financial advice

Model output requires human review

Data quality may affect results

Research-only output. No brokerage execution, no private-account scraping, no margin use, no trade placement, and no naked options recommendations are performed.

## Expanded Universe Summary

- Universe file: {universe_path}
- Source rows loaded: {prefilter['source_rows']}
- Rows scored: {prefilter['selected_rows']}
- Deterministic prefilter limit: {prefilter['limit']}
- Market regime score used: {market_regime_score}
- Options analysis status: unavailable
- Backtest status: not_run

## Deterministic Prefilter

{prefilter['method']}

The expanded mode is intentionally a research queue, not a full execution model. Missing price, valuation, momentum, and options feeds are scored neutrally or marked as data gaps instead of being inferred.

## Action Bias Counts

{counts_text}

## Top 20 Research Queue

{markdown_table(rows, top_columns, 20)}

## Earnings Event Risk

These rows have confirmed near-term earnings in the index earnings calendar and require timing verification before any research action.

{markdown_table(earnings_rows, top_columns, 20)}

## Data Gap Review

These rows are not rejected, but missing data lowers confidence and requires manual review.

{markdown_table(gap_rows, top_columns, 20)}

## CAD Alternatives

CAD alternatives must be verified in the broker before trading. CDRs and CAD ETFs may have different liquidity, spreads, ratios, fees, holdings, and hedge behavior than U.S. tickers.

{markdown_table(rows, cad_columns, 20)}

## Risk Notes

- Do not treat action_bias as a buy/sell instruction.
- Do not chase solely because a ticker appears in the expanded research queue.
- Verify current price, spread, volume, fundamentals, earnings timing, and news before any decision.
- No options edge is inferred. options_analysis_status is unavailable and options_bias is No Options Analysis.
- Re-run the default daily ranker or research desk for focused names before human review.

## Human Review Checklist

- Confirm ticker and index membership from a trusted source.
- Confirm current price, liquidity, earnings timing, and company news.
- Confirm CAD alternatives directly in the broker before use.
- Confirm no output is interpreted as direct trading advice.
- Confirm options are not used unless real options data is reviewed separately.
- Treat this as research only: Not financial advice; Model output requires human review; Data quality may affect results.
"""
    path.write_text(report, encoding="utf-8")


def run_expanded_universe_mode(args: argparse.Namespace) -> int:
    start = time.time()
    rows = load_index_universe(args.index_universe)
    selected_rows, prefilter = prefilter_expanded_candidates(rows, args.max_expanded_candidates)
    market_regime_score = load_default_market_regime_score()
    earnings_lookup = load_index_earnings_lookup()

    scored_rows = [
        score_expanded_candidate(row, market_regime_score, earnings_lookup)
        for row in selected_rows
    ]
    scored_rows.sort(key=lambda item: (item["action_score"], item["data_quality_score"], item["ticker"]), reverse=True)

    write_expanded_scores(args.scores, scored_rows)
    write_expanded_report(args.report, scored_rows, prefilter, args.index_universe, market_regime_score)
    write_action_bias_explanation(args.action_bias_explanation)

    print(f"Loaded {len(rows)} tickers from {args.index_universe}")
    print(f"Scored {len(scored_rows)} deterministic expanded-universe candidates")
    print(f"Scores saved: {args.scores}")
    print(f"Report saved: {args.report}")
    print(f"Action bias explanation saved: {args.action_bias_explanation}")
    print("\nTop 20 expanded research queue")
    print("rank,ticker,action_score,action_bias,confidence,options_analysis_status,options_bias")
    for index, row in enumerate(scored_rows[:20], start=1):
        print(
            f"{index},{row['ticker']},{row['action_score']},{row['action_bias']},"
            f"{row['confidence']},{row['options_analysis_status']},{row['options_bias']}"
        )
    elapsed = time.time() - start
    print(f"\nExpanded universe analyzed in {elapsed:.1f}s")
    if not args.scores.exists() or not args.report.exists() or not args.action_bias_explanation.exists():
        return 1
    return 0


def has_nan_score(row: Dict[str, Any]) -> bool:
    for field in [
        "final_score",
        "market_score",
        "quality_score",
        "valuation_score",
        "trend_score",
        "catalyst_score",
        "options_score",
        "risk_penalty",
    ]:
        value = row.get(field)
        if value is None:
            return True
        if isinstance(value, float) and not math.isfinite(value):
            return True
        if isinstance(value, str) and value.lower() == "nan":
            return True
    return False


def verify_outputs(
    watchlist_path: Path,
    scores_path: Path,
    report_path: Path,
    source_rows: List[Dict[str, Any]],
    scored_rows: List[Dict[str, Any]],
) -> Dict[str, bool]:
    verification = {
        "CSV loads successfully": False,
        "No missing ticker symbols": False,
        "No NaN scores in final output": False,
        "No strategy generated without risk_penalty": False,
        "No options strategy is naked": False,
        "All outputs are saved": False,
    }

    try:
        reloaded = load_watchlist(watchlist_path)
        verification["CSV loads successfully"] = len(reloaded) > 0
    except Exception:
        verification["CSV loads successfully"] = False

    verification["No missing ticker symbols"] = all(clean_text(row.get("ticker")) for row in source_rows)
    verification["No NaN scores in final output"] = all(not has_nan_score(row) for row in scored_rows)
    verification["No strategy generated without risk_penalty"] = all(row.get("risk_penalty") is not None for row in scored_rows)

    naked_options = False
    for row in scored_rows:
        if row["strategy"] == "Defined-Risk Options":
            text = f"{row['entry_zone']} {row['stop_or_exit']}".lower()
            if "defined-risk" not in text:
                naked_options = True
    verification["No options strategy is naked"] = not naked_options
    verification["All outputs are saved"] = scores_path.exists() and report_path.exists()
    return verification


def print_top_20(scored_rows: List[Dict[str, Any]]) -> None:
    print("\nTop 20 ranked tickers")
    print(
        "rank,ticker,final_score,risk_penalty,strategy,cad_alternative,cad_note"
    )
    for index, row in enumerate(scored_rows[:20], start=1):
        print(
            f"{index},{row['ticker']},{row['final_score']},{row['risk_penalty']},"
            f"{row['strategy']},{row['cad_alternative']},{row['cad_note']}"
        )


def source_label(rows: List[Dict[str, Any]], offline: bool) -> str:
    if offline:
        return "Local CSV only; public data fetch skipped by offline mode. Missing fields marked N/A/neutral."
    sources = set()
    fetch_errors = 0
    for row in rows:
        sources.update(row.get("_sources", []))
        fetch_errors += len(row.get("_fetch_errors", []))
    ordered_sources = sorted(sources)
    if not ordered_sources:
        ordered_sources = ["local watchlist"]
    suffix = ""
    if fetch_errors:
        suffix = f"; {fetch_errors} public-data fetch gaps/errors recorded"
    return ", ".join(ordered_sources) + suffix


def print_verification(verification: Dict[str, bool]) -> None:
    print("\nVerification")
    for key, passed in verification.items():
        print(f"{key}: {'PASS' if passed else 'FAIL'}")


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a daily investment ranking report from a CSV watchlist.")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST, help="Path to input watchlist CSV.")
    parser.add_argument("--index-universe", type=Path, default=DEFAULT_INDEX_UNIVERSE, help="Path to expanded index universe CSV.")
    parser.add_argument("--scores", type=Path, default=DEFAULT_SCORES, help="Path to output scores CSV.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Path to output Markdown report.")
    parser.add_argument("--action-bias-explanation", type=Path, default=DEFAULT_ACTION_BIAS_EXPLANATION, help="Path to expanded-mode action bias explanation Markdown.")
    parser.add_argument("--expanded-universe", action="store_true", help="Run expanded-universe daily research queue mode.")
    parser.add_argument("--max-expanded-candidates", type=int, default=150, help="Deterministic expanded-universe candidate limit.")
    parser.add_argument("--offline", action="store_true", help="Skip public data fetches and use local CSV only.")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent public-data fetch workers.")
    return parser.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    if args.expanded_universe:
        if args.scores == DEFAULT_SCORES:
            args.scores = DEFAULT_EXPANDED_SCORES
        if args.report == DEFAULT_REPORT:
            args.report = DEFAULT_EXPANDED_REPORT
        return run_expanded_universe_mode(args)

    rows = load_watchlist(args.watchlist)
    missing_tickers = [row.get("_load_error") for row in rows if row.get("_load_error")]
    if missing_tickers:
        for error in missing_tickers:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    start = time.time()
    print(f"Loaded {len(rows)} tickers from {args.watchlist}")
    print("Enriching with public market data where available..." if not args.offline else "Using local CSV only...")

    enriched_rows = enrich_watchlist(rows, offline=args.offline, workers=args.workers)
    market_metrics = fetch_market_metrics(offline=args.offline)
    scored_rows, context = compute_scores(enriched_rows, market_metrics)

    write_scores(args.scores, scored_rows)
    write_report(args.report, scored_rows, context, source_label(enriched_rows, args.offline))

    verification = verify_outputs(args.watchlist, args.scores, args.report, enriched_rows, scored_rows)
    print_verification(verification)
    print_top_20(scored_rows)

    elapsed = time.time() - start
    print(f"\nAnalyzed {len(scored_rows)} tickers in {elapsed:.1f}s")
    print(f"Scores saved: {args.scores}")
    print(f"Report saved: {args.report}")

    if not all(verification.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
