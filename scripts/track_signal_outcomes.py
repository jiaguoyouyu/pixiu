#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
from statistics import mean

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PRICE_CSV = BASE_DIR / "data" / "manual_price_history.csv"
TEMPLATE_PRICE_CSV = BASE_DIR / "data" / "manual_price_history.template.csv"
DEFAULT_OUTPUT_CSV = BASE_DIR / "outputs" / "signal_outcomes.csv"
DEFAULT_OUTPUT_REPORT = BASE_DIR / "outputs" / "signal_outcomes_report.md"

HORIZONS = [1, 5, 10, 20, 60]
BENCHMARKS = ["SPY", "QQQ", "SMH"]
DISCLAIMER = "Research-only. Not financial advice. Model output requires human review."


def parse_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value.strip())


def load_prices(path: Path) -> dict[str, list[dict[str, object]]]:
    if not path.exists():
        raise FileNotFoundError(path)

    by_ticker: dict[str, list[dict[str, object]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"ticker", "date", "close", "source"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")

        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            by_ticker.setdefault(ticker, []).append(
                {
                    "ticker": ticker,
                    "date": parse_date(row["date"]),
                    "close": float(row["close"]),
                    "source": (row.get("source") or "unknown").strip(),
                }
            )

    for rows in by_ticker.values():
        rows.sort(key=lambda item: item["date"])

    return by_ticker


def find_price_on_or_after(rows: list[dict[str, object]], target: dt.date) -> dict[str, object] | None:
    for row in rows:
        if row["date"] >= target:
            return row
    return None


def pct_return(start: float, end: float) -> float:
    if start == 0:
        return 0.0
    return (end / start - 1.0) * 100.0


def build_sample_signals() -> list[dict[str, object]]:
    return [
        {
            "ticker": "NVDA",
            "signal_date": dt.date(2026, 5, 26),
            "action_bias": "Buy/Add Watch",
            "action_score": 77.48,
            "confidence": "Medium-High",
            "mode": "sample",
            "source": "sample_signal",
        }
    ]


def compute_outcomes(prices: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    outcomes: list[dict[str, object]] = []

    for signal in build_sample_signals():
        ticker = str(signal["ticker"]).upper()
        signal_date = signal["signal_date"]
        ticker_rows = prices.get(ticker, [])
        signal_price = find_price_on_or_after(ticker_rows, signal_date)

        if not signal_price:
            row = dict(signal)
            row["signal_date"] = signal_date.isoformat()
            row["outcome_status"] = "missing_signal_price"
            row["signal_close"] = ""
            outcomes.append(row)
            continue

        row: dict[str, object] = dict(signal)
        row["signal_date"] = signal_date.isoformat()
        row["signal_close"] = signal_price["close"]
        row["outcome_status"] = "ok"

        for horizon in HORIZONS:
            target_date = signal_date + dt.timedelta(days=horizon)
            future_price = find_price_on_or_after(ticker_rows, target_date)

            if future_price:
                forward_return = round(
                    pct_return(float(signal_price["close"]), float(future_price["close"])),
                    4,
                )
                row[f"close_{horizon}d"] = future_price["close"]
                row[f"forward_return_{horizon}d"] = forward_return
            else:
                row[f"close_{horizon}d"] = ""
                row[f"forward_return_{horizon}d"] = ""

            for benchmark in BENCHMARKS:
                bench_start = find_price_on_or_after(prices.get(benchmark, []), signal_date)
                bench_end = find_price_on_or_after(prices.get(benchmark, []), target_date)
                key = f"excess_return_vs_{benchmark}_{horizon}d"

                if bench_start and bench_end and row[f"forward_return_{horizon}d"] != "":
                    bench_return = pct_return(float(bench_start["close"]), float(bench_end["close"]))
                    row[key] = round(float(row[f"forward_return_{horizon}d"]) - bench_return, 4)
                else:
                    row[key] = ""

        outcomes.append(row)

    return outcomes


def outcome_fieldnames() -> list[str]:
    fields = [
        "ticker",
        "signal_date",
        "mode",
        "action_bias",
        "action_score",
        "confidence",
        "signal_close",
        "outcome_status",
    ]
    for horizon in HORIZONS:
        fields.append(f"close_{horizon}d")
        fields.append(f"forward_return_{horizon}d")
        for benchmark in BENCHMARKS:
            fields.append(f"excess_return_vs_{benchmark}_{horizon}d")
    return fields


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=outcome_fieldnames(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, rows: list[dict[str, object]], price_source: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    ok_rows = [row for row in rows if row.get("outcome_status") == "ok"]
    values_5d = [
        float(row["forward_return_5d"])
        for row in ok_rows
        if row.get("forward_return_5d") not in ("", None)
    ]
    avg_5d = round(mean(values_5d), 4) if values_5d else "N/A"

    lines = [
        "# Pixiu Signal Outcome Tracking Report",
        "",
        f"Price source: `{price_source}`",
        "",
        "## Summary",
        "",
        f"- Outcome rows: {len(rows)}",
        f"- OK rows: {len(ok_rows)}",
        f"- Average 5D forward return: {avg_5d}",
        "",
        "## Method",
        "",
        "Local price-history CSV only. No live provider dependency. No brokerage connection. No order automation.",
        "",
        "## Results",
        "",
        "| Ticker | Signal Date | Action Bias | Signal Close | 5D Return | 20D Return | Status |",
        "|---|---|---|---:|---:|---:|---|",
    ]

    for row in rows:
        ticker = row.get("ticker", "")
        signal_date = row.get("signal_date", "")
        action_bias = row.get("action_bias", "")
        signal_close = row.get("signal_close", "")
        return_5d = row.get("forward_return_5d", "")
        return_20d = row.get("forward_return_20d", "")
        status = row.get("outcome_status", "")
        lines.append(f"| {ticker} | {signal_date} | {action_bias} | {signal_close} | {return_5d} | {return_20d} | {status} |")

    lines.extend(["", "## Boundary", "", DISCLAIMER, ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Track Pixiu signal outcomes from local price history.")
    parser.add_argument("--price-csv", type=Path, default=DEFAULT_PRICE_CSV)
    parser.add_argument("--allow-template", action="store_true")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_OUTPUT_REPORT)
    args = parser.parse_args()

    price_csv = args.price_csv
    if not price_csv.exists() and args.allow_template:
        price_csv = TEMPLATE_PRICE_CSV

    if not price_csv.exists():
        print(f"DATA GAP: manual price history file not found: {args.price_csv}")
        print("Create data/manual_price_history.csv or run with --allow-template for verifier/sample mode.")
        return 0

    prices = load_prices(price_csv)
    outcomes = compute_outcomes(prices)
    write_csv(args.output_csv, outcomes)
    write_report(args.output_report, outcomes, price_csv)

    print(f"Signal outcomes CSV: {args.output_csv}")
    print(f"Signal outcomes report: {args.output_report}")
    print(f"Outcome rows: {len(outcomes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
