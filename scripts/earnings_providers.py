#!/usr/bin/env python3
"""
Provider-based earnings calendar helpers for Pixiu.

Research-only. Reads API keys from environment variables only.
Never prints, stores, or returns API keys.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


FMP_URL = "https://financialmodelingprep.com/stable/earnings-calendar"
FINNHUB_URL = "https://finnhub.io/api/v1/calendar/earnings"
TIMEOUT_SECONDS = 20


def _redact(value: Any) -> str:
    text = str(value or "")
    for key_name in ("FMP_API_KEY", "FINNHUB_API_KEY", "EODHD_API_KEY"):
        key = os.environ.get(key_name)
        if key:
            text = text.replace(key, "[REDACTED]")
    return text.replace("apikey=", "apikey=[REDACTED]&").replace("token=", "token=[REDACTED]&")


def _http_get_json(url: str, params: Dict[str, str]) -> Any:
    query = urllib.parse.urlencode(params)
    request_url = f"{url}?{query}"
    req = urllib.request.Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "pixiu-research/1.5",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _status_from_http_error(exc: urllib.error.HTTPError) -> str:
    if exc.code == 429:
        return "http_429"
    if exc.code == 403:
        return "http_403"
    return "error"


def _empty_result(provider: str, status: str, error: str = "") -> Dict[str, Any]:
    return {
        "provider": provider,
        "status": status,
        "error": _redact(error),
        "rows": [],
        "raw_count": 0,
        "intersected_count": 0,
        "fallback_used": False,
    }


def fetch_fmp_earnings_calendar(start_date: dt.date, end_date: dt.date) -> Dict[str, Any]:
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        return _empty_result("fmp", "missing_api_key", "FMP_API_KEY is not set")

    try:
        payload = _http_get_json(
            FMP_URL,
            {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "apikey": api_key,
            },
        )
        if not isinstance(payload, list):
            return _empty_result("fmp", "error", "Malformed FMP response: expected list")
        rows = normalize_provider_earnings(payload, "fmp")
        if not rows:
            result = _empty_result("fmp", "empty", "FMP returned no usable earnings rows")
            result["raw_count"] = len(payload)
            return result
        return {
            "provider": "fmp",
            "status": "success",
            "error": "",
            "rows": rows,
            "raw_count": len(payload),
            "intersected_count": 0,
            "fallback_used": False,
        }
    except urllib.error.HTTPError as exc:
        return _empty_result("fmp", _status_from_http_error(exc), f"FMP HTTP error {exc.code}: {exc.reason}")
    except TimeoutError as exc:
        return _empty_result("fmp", "timeout", f"FMP timeout: {exc}")
    except Exception as exc:
        if "timed out" in str(exc).lower():
            return _empty_result("fmp", "timeout", f"FMP timeout: {exc}")
        return _empty_result("fmp", "error", f"FMP error: {exc}")


def fetch_finnhub_earnings_calendar(start_date: dt.date, end_date: dt.date) -> Dict[str, Any]:
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        return _empty_result("finnhub", "missing_api_key", "FINNHUB_API_KEY is not set")

    try:
        payload = _http_get_json(
            FINNHUB_URL,
            {
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "symbol": "",
                "token": api_key,
            },
        )
        raw_rows = payload.get("earningsCalendar") if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            return _empty_result("finnhub", "error", "Malformed Finnhub response: expected earningsCalendar list")
        rows = normalize_provider_earnings(raw_rows, "finnhub")
        if not rows:
            result = _empty_result("finnhub", "empty", "Finnhub returned no usable earnings rows")
            result["raw_count"] = len(raw_rows)
            return result
        return {
            "provider": "finnhub",
            "status": "success",
            "error": "",
            "rows": rows,
            "raw_count": len(raw_rows),
            "intersected_count": 0,
            "fallback_used": False,
        }
    except urllib.error.HTTPError as exc:
        return _empty_result("finnhub", _status_from_http_error(exc), f"Finnhub HTTP error {exc.code}: {exc.reason}")
    except TimeoutError as exc:
        return _empty_result("finnhub", "timeout", f"Finnhub timeout: {exc}")
    except Exception as exc:
        if "timed out" in str(exc).lower():
            return _empty_result("finnhub", "timeout", f"Finnhub timeout: {exc}")
        return _empty_result("finnhub", "error", f"Finnhub error: {exc}")


def _first_value(row: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def normalize_provider_earnings(raw_rows: List[Dict[str, Any]], provider: str) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue

        ticker = _first_value(raw, ["symbol", "ticker"]).upper()
        earnings_date = _first_value(raw, ["date", "earningsDate", "reportDate"])
        if not ticker or not earnings_date:
            continue

        timing = _first_value(raw, ["time", "hour", "reportTiming"]).lower()
        if timing in {"bmo", "before market open", "before_market"}:
            report_timing = "before_market"
        elif timing in {"amc", "after market close", "after_market"}:
            report_timing = "after_market"
        elif timing in {"dmh", "during market hours", "during_market"}:
            report_timing = "during_market"
        else:
            report_timing = "unknown"

        normalized.append(
            {
                "ticker": ticker,
                "company_name": _first_value(raw, ["company", "companyName", "name"]),
                "earnings_date": earnings_date[:10],
                "report_timing": report_timing,
                "eps_estimate": _first_value(raw, ["epsEstimated", "epsEstimate", "eps_estimate"]),
                "revenue_estimate": _first_value(raw, ["revenueEstimated", "revenueEstimate", "revenue_estimate"]),
                "provider": provider,
                "earnings_date_source": provider,
                "provider_status": "success",
                "source": provider,
                "updated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return normalized


def fetch_provider_earnings_calendar(start_date: dt.date, end_date: dt.date) -> Dict[str, Any]:
    has_fmp = bool(os.environ.get("FMP_API_KEY"))
    has_finnhub = bool(os.environ.get("FINNHUB_API_KEY"))

    if not has_fmp and not has_finnhub:
        return _empty_result("none", "missing_api_key", "No earnings provider key found. Set FMP_API_KEY or FINNHUB_API_KEY.")

    attempts: List[Dict[str, Any]] = []

    if has_fmp:
        fmp = fetch_fmp_earnings_calendar(start_date, end_date)
        attempts.append(fmp)
        if fmp["status"] == "success":
            fmp["attempts"] = attempts
            return fmp

    if has_finnhub:
        finnhub = fetch_finnhub_earnings_calendar(start_date, end_date)
        attempts.append(finnhub)
        if finnhub["status"] == "success":
            finnhub["attempts"] = attempts
            return finnhub

    result = attempts[-1] if attempts else _empty_result("none", "missing_api_key")
    result = dict(result)
    result["attempts"] = attempts
    return result
