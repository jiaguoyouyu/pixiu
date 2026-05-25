#!/usr/bin/env python3
"""Load Pixiu research outputs into a local DuckDB warehouse."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
DB_PATH = DATA_DIR / "pixiu.duckdb"
LEGACY_DB_PATH = DATA_DIR / "investment_ranker.duckdb"

CSV_INPUTS = {
    "daily_investment_scores": OUTPUT_DIR / "daily_investment_scores.csv",
    "index_weekly_earnings_calendar": OUTPUT_DIR / "index_weekly_earnings_calendar.csv",
    "research_desk_tasks": OUTPUT_DIR / "research_desk_tasks.csv",
    "koyfin_watchlists": OUTPUT_DIR / "koyfin_watchlists.csv",
}

DAILY_RANKER_INPUTS = {
    "default_watchlist": OUTPUT_DIR / "daily_investment_scores.csv",
    "expanded_universe": OUTPUT_DIR / "expanded_daily_investment_scores.csv",
}

MARKDOWN_INPUTS = [
    OUTPUT_DIR / "daily_investment_report.md",
    OUTPUT_DIR / "index_weekly_earnings_report.md",
    OUTPUT_DIR / "daily_wall_street_desk_brief.md",
    OUTPUT_DIR / "fiscal_ai_research_questions.md",
]


def load_duckdb():
    try:
        import duckdb  # type: ignore
    except ImportError:
        print("DuckDB Python package is required.", file=sys.stderr)
        print("pip install duckdb", file=sys.stderr)
        raise SystemExit(2)
    return duckdb


def ensure_database_path() -> Path:
    """Prefer the Pixiu database while preserving the legacy warehouse file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists() and LEGACY_DB_PATH.exists():
        shutil.copy2(LEGACY_DB_PATH, DB_PATH)
        print(f"Copied legacy warehouse to Pixiu database: {DB_PATH}")
    return DB_PATH


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_id_text() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def default_trading_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_float(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text.upper() == "N/A":
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def pick(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = clean_text(row.get(key))
        if value:
            return value
    return ""


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str | None]:
    if not path.exists():
        return [], "missing"
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                return [], "missing_header"
            rows = [
                {clean_text(key): clean_text(value) for key, value in row.items()}
                for row in reader
                if row
            ]
        return rows, None
    except Exception as exc:  # pragma: no cover - defensive daily runner guard
        return [], f"malformed_csv: {exc}"


def validate_trading_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        print(f"Invalid --trading-date: {value}. Expected YYYY-MM-DD.", file=sys.stderr)
        raise SystemExit(2)
    return value


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Pixiu research outputs into DuckDB.")
    parser.add_argument(
        "--run-type",
        choices=["production", "verification", "manual_test"],
        default="verification",
        help="Run classification for warehouse rows.",
    )
    parser.add_argument(
        "--trading-date",
        default=default_trading_date(),
        help="Trading date for daily ranker rows, in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--replace-production",
        action="store_true",
        help="Replace existing production daily-ranker rows for the same trading date/mode/source.",
    )
    args = parser.parse_args(argv)
    args.trading_date = validate_trading_date(args.trading_date)
    return args


def execute_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS warehouse_runs (
            run_id TEXT PRIMARY KEY,
            loaded_at TEXT,
            project_root TEXT,
            run_type TEXT,
            trading_date TEXT,
            daily_scores_rows INTEGER,
            earnings_rows INTEGER,
            research_tasks_rows INTEGER,
            koyfin_rows INTEGER,
            status TEXT,
            notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_investment_scores (
            run_id TEXT,
            loaded_at TEXT,
            source_file TEXT,
            ticker TEXT,
            company_name TEXT,
            strategy TEXT,
            final_score DOUBLE,
            sector TEXT,
            theme TEXT,
            cad_alternative TEXT,
            raw_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_ranker_scores (
            run_id TEXT,
            run_timestamp TEXT,
            loaded_at TEXT,
            source_file TEXT,
            run_type TEXT,
            trading_date TEXT,
            ranker_mode TEXT,
            ticker TEXT,
            company_name TEXT,
            index_memberships TEXT,
            sector TEXT,
            industry TEXT,
            quality_score DOUBLE,
            valuation_score DOUBLE,
            momentum_score DOUBLE,
            earnings_risk_score DOUBLE,
            data_quality_score DOUBLE,
            market_regime_score DOUBLE,
            action_score DOUBLE,
            action_bias TEXT,
            confidence TEXT,
            primary_reason TEXT,
            risk_flags TEXT,
            invalidation_check TEXT,
            backtest_status TEXT,
            options_analysis_status TEXT,
            options_bias TEXT,
            raw_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS index_weekly_earnings_calendar (
            run_id TEXT,
            loaded_at TEXT,
            source_file TEXT,
            ticker TEXT,
            company_name TEXT,
            earnings_date TEXT,
            provider TEXT,
            provider_status TEXT,
            importance_score DOUBLE,
            importance_bucket TEXT,
            data_status TEXT,
            raw_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_desk_tasks (
            run_id TEXT,
            loaded_at TEXT,
            source_file TEXT,
            task_type TEXT,
            ticker TEXT,
            priority TEXT,
            status TEXT,
            raw_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS koyfin_watchlists (
            run_id TEXT,
            loaded_at TEXT,
            source_file TEXT,
            group_name TEXT,
            ticker TEXT,
            company_name TEXT,
            strategy TEXT,
            final_score DOUBLE,
            importance_score DOUBLE,
            raw_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS warehouse_load_errors (
            run_id TEXT,
            loaded_at TEXT,
            source_file TEXT,
            error_type TEXT,
            message TEXT
        )
        """
    )
    ensure_column(conn, "warehouse_runs", "run_type", "TEXT")
    ensure_column(conn, "warehouse_runs", "trading_date", "TEXT")
    ensure_column(conn, "daily_ranker_scores", "run_type", "TEXT")
    ensure_column(conn, "daily_ranker_scores", "trading_date", "TEXT")
    backfill_run_metadata(conn)


def table_columns(conn: Any, table_name: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'main' AND table_name = ?
            """,
            [table_name],
        ).fetchall()
    }


def ensure_column(conn: Any, table_name: str, column_name: str, column_type: str) -> None:
    if column_name not in table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def backfill_run_metadata(conn: Any) -> None:
    conn.execute("UPDATE warehouse_runs SET run_type = 'verification' WHERE run_type IS NULL OR run_type = ''")
    conn.execute(
        """
        UPDATE warehouse_runs
        SET trading_date = SUBSTR(loaded_at, 1, 10)
        WHERE (trading_date IS NULL OR trading_date = '')
          AND loaded_at IS NOT NULL
          AND LENGTH(loaded_at) >= 10
        """
    )
    conn.execute("UPDATE daily_ranker_scores SET run_type = 'verification' WHERE run_type IS NULL OR run_type = ''")
    conn.execute(
        """
        UPDATE daily_ranker_scores
        SET trading_date = SUBSTR(run_timestamp, 1, 10)
        WHERE (trading_date IS NULL OR trading_date = '')
          AND run_timestamp IS NOT NULL
          AND LENGTH(run_timestamp) >= 10
        """
    )


def record_error(conn: Any, run_id: str, loaded_at: str, path: Path, error_type: str, message: str) -> None:
    conn.execute(
        "INSERT INTO warehouse_load_errors VALUES (?, ?, ?, ?, ?)",
        [run_id, loaded_at, str(path.relative_to(PROJECT_ROOT)), error_type, message],
    )


def raw_json(row: dict[str, str]) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=True)


def insert_daily_scores(conn: Any, run_id: str, loaded_at: str, path: Path, rows: list[dict[str, str]]) -> int:
    source_file = str(path.relative_to(PROJECT_ROOT))
    seen: set[tuple[str, str]] = set()
    count = 0
    for row in rows:
        ticker = pick(row, "ticker").upper()
        key = (source_file, ticker)
        if not ticker or key in seen:
            continue
        seen.add(key)
        conn.execute(
            "INSERT INTO daily_investment_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                loaded_at,
                source_file,
                ticker,
                pick(row, "company_name", "name", "ticker"),
                pick(row, "strategy"),
                parse_float(row.get("final_score")),
                pick(row, "sector"),
                pick(row, "theme"),
                pick(row, "cad_alternative"),
                raw_json(row),
            ],
        )
        count += 1
    return count


def default_action_bias(strategy: str) -> str:
    text = strategy.strip()
    if text in {"Buy/Add", "Ranked Buy Candidate"}:
        return "Buy/Add Watch"
    if text in {"ETF Trend Candidate", "High-Quality Watch"}:
        return "Hold / Monitor"
    if text == "Pullback Buy":
        return "Pullback Buy Watch"
    if text == "Avoid Chase":
        return "Avoid Chase"
    if text == "Avoid":
        return "Data Gap Review"
    return ""


def insert_daily_ranker_scores(
    conn: Any,
    run_id: str,
    loaded_at: str,
    run_type: str,
    trading_date: str,
    mode: str,
    path: Path,
    rows: list[dict[str, str]],
    replace_production: bool,
) -> int:
    source_file = str(path.relative_to(PROJECT_ROOT))
    if run_type == "production":
        existing = conn.execute(
            """
            SELECT COUNT(*)
            FROM daily_ranker_scores
            WHERE run_type = 'production'
              AND trading_date = ?
              AND ranker_mode = ?
              AND source_file = ?
            """,
            [trading_date, mode, source_file],
        ).fetchone()[0]
        if existing and not replace_production:
            print(
                "Duplicate production daily-ranker load skipped: "
                f"trading_date={trading_date} ranker_mode={mode} source_file={source_file} existing_rows={existing}"
            )
            return 0
        if existing and replace_production:
            conn.execute(
                """
                DELETE FROM daily_ranker_scores
                WHERE run_type = 'production'
                  AND trading_date = ?
                  AND ranker_mode = ?
                  AND source_file = ?
                """,
                [trading_date, mode, source_file],
            )

    seen: set[tuple[str, str, str]] = set()
    count = 0
    for row in rows:
        ticker = pick(row, "ticker").upper()
        key = (source_file, mode, ticker)
        if not ticker or key in seen:
            continue
        seen.add(key)

        strategy = pick(row, "strategy")
        action_bias = pick(row, "action_bias") or default_action_bias(strategy)
        market_regime_score = parse_float(row.get("market_regime_score"))
        if market_regime_score is None:
            market_regime_score = parse_float(row.get("market_score"))
        action_score = parse_float(row.get("action_score"))
        if action_score is None:
            action_score = parse_float(row.get("final_score"))
        momentum_score = parse_float(row.get("momentum_score"))
        if momentum_score is None:
            momentum_score = parse_float(row.get("trend_score"))

        conn.execute(
            """
            INSERT INTO daily_ranker_scores (
                run_id,
                run_timestamp,
                loaded_at,
                source_file,
                run_type,
                trading_date,
                ranker_mode,
                ticker,
                company_name,
                index_memberships,
                sector,
                industry,
                quality_score,
                valuation_score,
                momentum_score,
                earnings_risk_score,
                data_quality_score,
                market_regime_score,
                action_score,
                action_bias,
                confidence,
                primary_reason,
                risk_flags,
                invalidation_check,
                backtest_status,
                options_analysis_status,
                options_bias,
                raw_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            [
                run_id,
                loaded_at,
                loaded_at,
                source_file,
                run_type,
                trading_date,
                mode,
                ticker,
                pick(row, "company_name", "name", "ticker"),
                pick(row, "index_memberships"),
                pick(row, "sector"),
                pick(row, "industry"),
                parse_float(row.get("quality_score")),
                parse_float(row.get("valuation_score")),
                momentum_score,
                parse_float(row.get("earnings_risk_score")),
                parse_float(row.get("data_quality_score")),
                market_regime_score,
                action_score,
                action_bias,
                pick(row, "confidence"),
                pick(row, "primary_reason", "key_reason"),
                pick(row, "risk_flags", "key_risk"),
                pick(row, "invalidation_check", "stop_or_exit"),
                pick(row, "backtest_status") or "not_run",
                pick(row, "options_analysis_status") or "unavailable",
                pick(row, "options_bias") or "No Options Analysis",
                raw_json(row),
            ],
        )
        count += 1
    return count


def insert_earnings(conn: Any, run_id: str, loaded_at: str, path: Path, rows: list[dict[str, str]]) -> int:
    source_file = str(path.relative_to(PROJECT_ROOT))
    seen: set[tuple[str, str, str]] = set()
    count = 0
    for row in rows:
        ticker = pick(row, "ticker").upper()
        earnings_date = pick(row, "earnings_date") or "N/A"
        key = (source_file, ticker, earnings_date)
        if not ticker or key in seen:
            continue
        seen.add(key)
        conn.execute(
            "INSERT INTO index_weekly_earnings_calendar VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                loaded_at,
                source_file,
                ticker,
                pick(row, "company_name", "name", "ticker"),
                earnings_date,
                pick(row, "provider"),
                pick(row, "provider_status"),
                parse_float(row.get("importance_score")),
                pick(row, "importance_bucket"),
                pick(row, "data_status"),
                raw_json(row),
            ],
        )
        count += 1
    return count


def insert_tasks(conn: Any, run_id: str, loaded_at: str, path: Path, rows: list[dict[str, str]]) -> int:
    source_file = str(path.relative_to(PROJECT_ROOT))
    seen: set[tuple[str, str, str, str]] = set()
    count = 0
    for index, row in enumerate(rows):
        ticker = pick(row, "ticker").upper()
        task_type = pick(row, "task_type")
        priority = pick(row, "priority")
        key = (source_file, task_type, ticker, str(index))
        if key in seen:
            continue
        seen.add(key)
        conn.execute(
            "INSERT INTO research_desk_tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                loaded_at,
                source_file,
                task_type,
                ticker,
                priority,
                pick(row, "status"),
                raw_json(row),
            ],
        )
        count += 1
    return count


def insert_koyfin(conn: Any, run_id: str, loaded_at: str, path: Path, rows: list[dict[str, str]]) -> int:
    source_file = str(path.relative_to(PROJECT_ROOT))
    seen: set[tuple[str, str, str]] = set()
    count = 0
    for row in rows:
        group_name = pick(row, "group_name", "watchlist_name")
        ticker = pick(row, "ticker").upper()
        key = (source_file, group_name, ticker)
        if not ticker or not group_name or key in seen:
            continue
        seen.add(key)
        conn.execute(
            "INSERT INTO koyfin_watchlists VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                loaded_at,
                source_file,
                group_name,
                ticker,
                pick(row, "company_name", "name", "ticker"),
                pick(row, "strategy"),
                parse_float(row.get("final_score")),
                parse_float(row.get("importance_score")),
                raw_json(row),
            ],
        )
        count += 1
    return count


def unique_run_id(conn: Any, candidate: str) -> str:
    run_id = candidate
    suffix = 1
    while True:
        exists = conn.execute("SELECT COUNT(*) FROM warehouse_runs WHERE run_id = ?", [run_id]).fetchone()[0]
        if not exists:
            return run_id
        suffix += 1
        run_id = f"{candidate}-{suffix:02d}"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    duckdb = load_duckdb()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = ensure_database_path()
    conn = duckdb.connect(str(db_path))
    execute_schema(conn)

    loaded_at = now_text()
    run_id = unique_run_id(conn, run_id_text())
    counts = {
        "daily_scores_rows": 0,
        "earnings_rows": 0,
        "research_tasks_rows": 0,
        "koyfin_rows": 0,
    }
    notes: list[str] = []
    had_errors = False

    loaders = {
        "daily_investment_scores": insert_daily_scores,
        "index_weekly_earnings_calendar": insert_earnings,
        "research_desk_tasks": insert_tasks,
        "koyfin_watchlists": insert_koyfin,
    }
    count_keys = {
        "daily_investment_scores": "daily_scores_rows",
        "index_weekly_earnings_calendar": "earnings_rows",
        "research_desk_tasks": "research_tasks_rows",
        "koyfin_watchlists": "koyfin_rows",
    }

    for name, path in CSV_INPUTS.items():
        rows, error = read_csv_rows(path)
        if error:
            had_errors = True
            record_error(conn, run_id, loaded_at, path, error, f"{name} input unavailable or malformed")
            notes.append(f"{name}: {error}")
            continue
        try:
            inserted = loaders[name](conn, run_id, loaded_at, path, rows)
            counts[count_keys[name]] = inserted
            notes.append(f"{name}: {inserted} rows")
        except Exception as exc:  # pragma: no cover - defensive daily runner guard
            had_errors = True
            record_error(conn, run_id, loaded_at, path, "load_failed", str(exc))
            notes.append(f"{name}: load_failed")

    for mode, path in DAILY_RANKER_INPUTS.items():
        rows, error = read_csv_rows(path)
        if error:
            had_errors = True
            record_error(conn, run_id, loaded_at, path, error, f"daily_ranker_scores {mode} input unavailable or malformed")
            notes.append(f"daily_ranker_scores {mode}: {error}")
            continue
        try:
            inserted = insert_daily_ranker_scores(
                conn,
                run_id,
                loaded_at,
                args.run_type,
                args.trading_date,
                mode,
                path,
                rows,
                args.replace_production,
            )
            notes.append(f"daily_ranker_scores {mode}: {inserted} rows")
        except Exception as exc:  # pragma: no cover - defensive daily runner guard
            had_errors = True
            record_error(conn, run_id, loaded_at, path, "load_failed", str(exc))
            notes.append(f"daily_ranker_scores {mode}: load_failed")

    for path in MARKDOWN_INPUTS:
        if path.exists():
            notes.append(f"{path.name}: present")
        else:
            had_errors = True
            record_error(conn, run_id, loaded_at, path, "missing_input", "Markdown research input missing")
            notes.append(f"{path.name}: missing")

    status = "partial" if had_errors else "success"
    conn.execute(
        """
        INSERT INTO warehouse_runs (
            run_id,
            loaded_at,
            project_root,
            run_type,
            trading_date,
            daily_scores_rows,
            earnings_rows,
            research_tasks_rows,
            koyfin_rows,
            status,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            loaded_at,
            str(PROJECT_ROOT),
            args.run_type,
            args.trading_date,
            counts["daily_scores_rows"],
            counts["earnings_rows"],
            counts["research_tasks_rows"],
            counts["koyfin_rows"],
            status,
            "; ".join(notes),
        ],
    )
    conn.close()

    print("Research warehouse load complete")
    print(f"Database: {db_path}")
    print(f"Run ID: {run_id}")
    print(f"Loaded at: {loaded_at}")
    print(f"Run type: {args.run_type}")
    print(f"Trading date: {args.trading_date}")
    print(f"Status: {status}")
    print(f"Daily score rows: {counts['daily_scores_rows']}")
    print(f"Index earnings rows: {counts['earnings_rows']}")
    print(f"Research task rows: {counts['research_tasks_rows']}")
    print(f"Koyfin watchlist rows: {counts['koyfin_rows']}")
    if had_errors:
        print("Warnings were recorded in warehouse_load_errors.")
    print("Research-only. No brokerage connection, no orders, no API keys, no credentials.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
