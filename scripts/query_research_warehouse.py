#!/usr/bin/env python3
"""Plain-text query CLI for the Pixiu DuckDB warehouse."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "pixiu.duckdb"
LEGACY_DB_PATH = PROJECT_ROOT / "data" / "investment_ranker.duckdb"
REQUIRED_TABLES = [
    "warehouse_runs",
    "daily_investment_scores",
    "daily_ranker_scores",
    "index_weekly_earnings_calendar",
    "research_desk_tasks",
    "koyfin_watchlists",
    "warehouse_load_errors",
]

LOW_CONFIDENCE_PREDICATE = """
(
    confidence ILIKE '%Low%'
    OR action_bias = 'Data Gap Review'
    OR data_quality_score < 70
    OR primary_reason ILIKE '%Data Gap%'
    OR primary_reason ILIKE '%Missing%'
    OR primary_reason ILIKE '%Unavailable%'
    OR primary_reason ILIKE '%Insufficient%'
    OR risk_flags ILIKE '%Data Gap%'
    OR risk_flags ILIKE '%Missing%'
    OR (risk_flags ILIKE '%Unavailable%' AND risk_flags NOT ILIKE '%options analysis unavailable%')
    OR risk_flags ILIKE '%Insufficient%'
)
AND NOT (
    confidence = 'Medium-High'
    AND COALESCE(data_quality_score, 100) >= 80
    AND action_bias IN ('Buy/Add Watch', 'Pullback Buy Watch')
    AND NOT (
        primary_reason ILIKE '%Data Gap%'
        OR primary_reason ILIKE '%Missing%'
        OR primary_reason ILIKE '%Unavailable%'
        OR primary_reason ILIKE '%Insufficient%'
        OR risk_flags ILIKE '%Data Gap%'
        OR risk_flags ILIKE '%Missing%'
        OR (risk_flags ILIKE '%Unavailable%' AND risk_flags NOT ILIKE '%options analysis unavailable%')
        OR risk_flags ILIKE '%Insufficient%'
    )
)
"""


def load_duckdb():
    try:
        import duckdb  # type: ignore
    except ImportError:
        print("DuckDB Python package is required.", file=sys.stderr)
        print("pip install duckdb", file=sys.stderr)
        raise SystemExit(2)
    return duckdb


def connect() -> Any:
    db_path = DB_PATH if DB_PATH.exists() else LEGACY_DB_PATH
    if not db_path.exists():
        print(f"Warehouse database not found: {DB_PATH}", file=sys.stderr)
        print(f"Legacy fallback also missing: {LEGACY_DB_PATH}", file=sys.stderr)
        print("Run ./scripts/run_research_warehouse_update.sh first.", file=sys.stderr)
        raise SystemExit(1)
    return load_duckdb().connect(str(db_path), read_only=True)


def latest_run_id(conn: Any) -> str | None:
    row = conn.execute("SELECT run_id FROM warehouse_runs ORDER BY loaded_at DESC LIMIT 1").fetchone()
    return row[0] if row else None


def print_rows(headers: list[str], rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        print("- None")
        return
    widths = [len(header) for header in headers]
    text_rows = [[format_value(value) for value in row] for row in rows]
    for row in text_rows:
        for idx, value in enumerate(row):
            widths[idx] = min(max(widths[idx], len(value)), 36)
    print("  ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)))
    print("  ".join("-" * widths[idx] for idx in range(len(headers))))
    for row in text_rows:
        print("  ".join(row[idx][: widths[idx]].ljust(widths[idx]) for idx in range(len(headers))))


def format_value(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def command_latest_run(conn: Any) -> None:
    row = conn.execute(
        """
        SELECT run_id, loaded_at, status, daily_scores_rows, earnings_rows, research_tasks_rows, koyfin_rows, notes
        FROM warehouse_runs
        ORDER BY loaded_at DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        print("No warehouse runs found.")
        return
    headers = [
        "run_id",
        "loaded_at",
        "status",
        "daily",
        "earnings",
        "tasks",
        "koyfin",
        "notes",
    ]
    print_rows(headers, [row])


def command_table_counts(conn: Any) -> None:
    rows = []
    for table in REQUIRED_TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        rows.append((table, count))
    print_rows(["table", "rows"], rows)


def command_summary(conn: Any) -> None:
    run_id = latest_run_id(conn)
    if not run_id:
        print("No warehouse runs found.")
        return

    print("Research Warehouse Summary")
    db_path = DB_PATH if DB_PATH.exists() else LEGACY_DB_PATH
    print(f"Database: {db_path}")
    print()
    command_latest_run(conn)
    print()

    print("Strategy counts:")
    rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(strategy, ''), 'N/A') AS strategy, COUNT(*) AS rows
        FROM daily_investment_scores
        WHERE run_id = ?
        GROUP BY strategy
        ORDER BY rows DESC, strategy
        """,
        [run_id],
    ).fetchall()
    print_rows(["strategy", "rows"], rows)
    print()

    print("Top ranked names:")
    rows = conn.execute(
        """
        SELECT ticker, company_name, strategy, final_score, cad_alternative
        FROM daily_investment_scores
        WHERE run_id = ?
        ORDER BY final_score DESC NULLS LAST, ticker
        LIMIT 10
        """,
        [run_id],
    ).fetchall()
    print_rows(["ticker", "company", "strategy", "score", "cad"], rows)
    print()

    print("High-impact data gaps:")
    rows = conn.execute(
        """
        SELECT ticker, company_name, importance_score, importance_bucket, data_status
        FROM index_weekly_earnings_calendar
        WHERE run_id = ?
          AND (earnings_date IS NULL OR earnings_date = '' OR earnings_date = 'N/A' OR data_status ILIKE '%Data Gap%')
        ORDER BY importance_score DESC NULLS LAST, ticker
        LIMIT 10
        """,
        [run_id],
    ).fetchall()
    print_rows(["ticker", "company", "importance", "bucket", "status"], rows)
    print()

    print("Open research tasks:")
    rows = conn.execute(
        """
        SELECT priority, task_type, ticker, status
        FROM research_desk_tasks
        WHERE run_id = ?
        ORDER BY priority, task_type, ticker
        LIMIT 10
        """,
        [run_id],
    ).fetchall()
    print_rows(["priority", "task_type", "ticker", "status"], rows)


def command_top_ranked(conn: Any) -> None:
    run_id = latest_run_id(conn)
    if not run_id:
        print("No warehouse runs found.")
        return
    rows = conn.execute(
        """
        SELECT ticker, company_name, strategy, final_score, cad_alternative
        FROM daily_investment_scores
        WHERE run_id = ?
        ORDER BY final_score DESC NULLS LAST, ticker
        LIMIT 20
        """,
        [run_id],
    ).fetchall()
    print_rows(["ticker", "company", "strategy", "score", "cad"], rows)


def command_data_gaps(conn: Any) -> None:
    run_id = latest_run_id(conn)
    if not run_id:
        print("No warehouse runs found.")
        return
    rows = conn.execute(
        """
        SELECT ticker, company_name, earnings_date, importance_score, importance_bucket, data_status
        FROM index_weekly_earnings_calendar
        WHERE run_id = ?
          AND (earnings_date IS NULL OR earnings_date = '' OR earnings_date = 'N/A' OR data_status ILIKE '%Data Gap%')
        ORDER BY importance_score DESC NULLS LAST, ticker
        LIMIT 30
        """,
        [run_id],
    ).fetchall()
    print_rows(["ticker", "company", "earnings_date", "importance", "bucket", "status"], rows)


def latest_daily_ranker_run_id(conn: Any, mode: str | None = None) -> str | None:
    if mode:
        row = conn.execute(
            """
            SELECT run_id
            FROM daily_ranker_scores
            WHERE ranker_mode = ?
            ORDER BY loaded_at DESC
            LIMIT 1
            """,
            [mode],
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT run_id
            FROM daily_ranker_scores
            ORDER BY loaded_at DESC
            LIMIT 1
            """
        ).fetchone()
    return row[0] if row else None


def latest_production_run(conn: Any) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT run_id, trading_date
        FROM warehouse_runs
        WHERE run_type = 'production'
        ORDER BY trading_date DESC NULLS LAST, loaded_at DESC
        LIMIT 1
        """
    ).fetchone()
    return (row[0], row[1]) if row else None


def previous_production_run(conn: Any, latest_run_id: str) -> tuple[str, str] | None:
    row = conn.execute(
        """
        SELECT run_id, trading_date
        FROM warehouse_runs
        WHERE run_type = 'production'
          AND run_id <> ?
        ORDER BY trading_date DESC NULLS LAST, loaded_at DESC
        LIMIT 1
        """,
        [latest_run_id],
    ).fetchone()
    return (row[0], row[1]) if row else None


def command_daily_ranker_latest(conn: Any) -> None:
    run_id = latest_daily_ranker_run_id(conn)
    if not run_id:
        print("No daily ranker warehouse rows found.")
        return
    rows = conn.execute(
        """
        SELECT ranker_mode, ticker, company_name, action_score, action_bias, confidence, options_analysis_status
        FROM daily_ranker_scores
        WHERE run_id = ?
        ORDER BY ranker_mode, action_score DESC NULLS LAST, ticker
        LIMIT 40
        """,
        [run_id],
    ).fetchall()
    print_rows(["mode", "ticker", "company", "action_score", "action_bias", "confidence", "options"], rows)


def command_daily_ranker_expanded_latest(conn: Any) -> None:
    run_id = latest_daily_ranker_run_id(conn, "expanded_universe")
    if not run_id:
        print("No expanded daily ranker rows found.")
        return
    rows = conn.execute(
        """
        SELECT ticker, company_name, action_score, action_bias, confidence, data_quality_score, risk_flags
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND ranker_mode = 'expanded_universe'
        ORDER BY
            action_score DESC NULLS LAST,
            CASE confidence
                WHEN 'High' THEN 5
                WHEN 'Medium-High' THEN 4
                WHEN 'Medium' THEN 3
                WHEN 'Low' THEN 1
                ELSE 2
            END DESC,
            ticker
        LIMIT 30
        """,
        [run_id],
    ).fetchall()
    print_rows(["ticker", "company", "action_score", "action_bias", "confidence", "data_quality", "risk_flags"], rows)


def command_action_bias_summary(conn: Any) -> None:
    rows = conn.execute(
        """
        SELECT run_id, ranker_mode, COALESCE(NULLIF(action_bias, ''), 'N/A') AS action_bias, COUNT(*) AS rows
        FROM daily_ranker_scores
        GROUP BY run_id, ranker_mode, action_bias
        ORDER BY run_id DESC, ranker_mode, rows DESC, action_bias
        LIMIT 80
        """
    ).fetchall()
    print_rows(["run_id", "mode", "action_bias", "rows"], rows)


def command_ticker_daily_ranker_history(conn: Any, ticker: str) -> None:
    normalized = ticker.strip().upper()
    rows = conn.execute(
        """
        SELECT run_id, loaded_at, ranker_mode, action_score, action_bias, confidence, options_analysis_status
        FROM daily_ranker_scores
        WHERE ticker = ?
        ORDER BY loaded_at DESC, ranker_mode
        LIMIT 40
        """,
        [normalized],
    ).fetchall()
    print(f"Daily ranker history: {normalized}")
    print_rows(["run_id", "loaded_at", "mode", "action_score", "action_bias", "confidence", "options"], rows)


def command_action_bias_history(conn: Any, action_bias: str) -> None:
    rows = conn.execute(
        """
        SELECT run_id, loaded_at, ranker_mode, ticker, company_name, action_score, confidence
        FROM daily_ranker_scores
        WHERE action_bias = ?
        ORDER BY loaded_at DESC, action_score DESC NULLS LAST, ticker
        LIMIT 60
        """,
        [action_bias],
    ).fetchall()
    print(f"Action bias history: {action_bias}")
    print_rows(["run_id", "loaded_at", "mode", "ticker", "company", "action_score", "confidence"], rows)


def command_data_quality_watch(conn: Any) -> None:
    run_id = latest_daily_ranker_run_id(conn, "expanded_universe")
    if not run_id:
        print("No expanded daily ranker rows found.")
        return
    rows = conn.execute(
        """
        SELECT ticker, company_name, action_score, action_bias, confidence, data_quality_score, risk_flags
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND ranker_mode = 'expanded_universe'
          AND (
              confidence ILIKE '%Low%'
              OR action_bias = 'Data Gap Review'
              OR data_quality_score < 70
              OR risk_flags ILIKE '%No live price%'
          )
        ORDER BY data_quality_score ASC NULLS FIRST, action_score DESC NULLS LAST, ticker
        LIMIT 40
        """,
        [run_id],
    ).fetchall()
    print_rows(["ticker", "company", "action_score", "action_bias", "confidence", "data_quality", "risk_flags"], rows)


def command_production_latest(conn: Any) -> None:
    latest = latest_production_run(conn)
    if not latest:
        print("No production warehouse run found.")
        return
    run_id, _ = latest
    rows = conn.execute(
        """
        SELECT ranker_mode, ticker, company_name, action_score, action_bias, confidence, options_analysis_status
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND run_type = 'production'
        ORDER BY ranker_mode, action_score DESC NULLS LAST, ticker
        LIMIT 40
        """,
        [run_id],
    ).fetchall()
    print_rows(["mode", "ticker", "company", "action_score", "action_bias", "confidence", "options"], rows)


def command_production_action_bias_summary(conn: Any) -> None:
    rows = conn.execute(
        """
        SELECT trading_date, run_id, ranker_mode, COALESCE(NULLIF(action_bias, ''), 'N/A') AS action_bias, COUNT(*) AS rows
        FROM daily_ranker_scores
        WHERE run_type = 'production'
        GROUP BY trading_date, run_id, ranker_mode, action_bias
        ORDER BY trading_date DESC NULLS LAST, run_id DESC, ranker_mode, rows DESC, action_bias
        LIMIT 120
        """
    ).fetchall()
    print_rows(["trading_date", "run_id", "mode", "action_bias", "rows"], rows)


def production_rows_for_bias(conn: Any, run_id: str, action_bias: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            """
            SELECT ticker
            FROM daily_ranker_scores
            WHERE run_id = ?
              AND run_type = 'production'
              AND ranker_mode = 'expanded_universe'
              AND action_bias = ?
            """,
            [run_id, action_bias],
        ).fetchall()
    }


def command_action_bias_drift(conn: Any, write_report: bool = True) -> None:
    latest = latest_production_run(conn)
    if not latest:
        message = "No production warehouse run found. Run ./scripts/run_daily_production_research.sh first."
        if write_report:
            report_path = PROJECT_ROOT / "outputs" / "action_bias_drift_report.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                "# Action Bias Drift Report\n\n"
                "Not financial advice\n\n"
                "Model output requires human review\n\n"
                "Data quality may affect results\n\n"
                "Research-only output. No automatic trading, brokerage connection, or order placement is performed.\n\n"
                "## Action Bias Counts\n\n"
                "- None: no production run found.\n\n"
                "## Duplicate Production Guard\n\n"
                "- No production run found.\n\n"
                "## Low Confidence / Data Gap Watch\n\n"
                "- None.\n",
                encoding="utf-8",
            )
        print(message)
        return

    latest_run_id, trading_date = latest
    previous = previous_production_run(conn, latest_run_id)
    previous_run_id = previous[0] if previous else None

    counts = conn.execute(
        """
        SELECT ranker_mode, COALESCE(NULLIF(action_bias, ''), 'N/A') AS action_bias, COUNT(*) AS rows
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND run_type = 'production'
        GROUP BY ranker_mode, action_bias
        ORDER BY ranker_mode, rows DESC, action_bias
        """,
        [latest_run_id],
    ).fetchall()
    top = conn.execute(
        """
        SELECT ticker, company_name, action_score, action_bias, confidence
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND run_type = 'production'
          AND ranker_mode = 'expanded_universe'
        ORDER BY action_score DESC NULLS LAST, ticker
        LIMIT 20
        """,
        [latest_run_id],
    ).fetchall()
    low_confidence = conn.execute(
        f"""
        SELECT ticker, company_name, action_score, action_bias, confidence, data_quality_score
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND run_type = 'production'
          AND ranker_mode = 'expanded_universe'
          AND {LOW_CONFIDENCE_PREDICATE}
        ORDER BY data_quality_score ASC NULLS FIRST, action_score DESC NULLS LAST, ticker
        LIMIT 20
        """,
        [latest_run_id],
    ).fetchall()
    duplicate_rows = conn.execute(
        """
        SELECT trading_date, ranker_mode, source_file, COUNT(DISTINCT run_id) AS production_runs, COUNT(*) AS rows
        FROM daily_ranker_scores
        WHERE run_type = 'production'
        GROUP BY trading_date, ranker_mode, source_file
        HAVING COUNT(DISTINCT run_id) > 1
        ORDER BY trading_date DESC NULLS LAST, ranker_mode, source_file
        """
    ).fetchall()

    drift_sections: list[tuple[str, list[str]]] = []
    if previous_run_id:
        for label in ["Buy/Add Watch", "Avoid Chase", "Earnings Event Risk"]:
            latest_set = production_rows_for_bias(conn, latest_run_id, label)
            previous_set = production_rows_for_bias(conn, previous_run_id, label)
            if label == "Buy/Add Watch":
                title = "New Buy/Add Watch"
                values = sorted(latest_set - previous_set)
            elif label == "Avoid Chase":
                title = "Moved To Avoid Chase"
                values = sorted(latest_set - previous_set)
            else:
                title = "Moved To Earnings Event Risk"
                values = sorted(latest_set - previous_set)
            drift_sections.append((title, values[:20]))
        removed = sorted(production_rows_for_bias(conn, previous_run_id, "Buy/Add Watch") - production_rows_for_bias(conn, latest_run_id, "Buy/Add Watch"))
        drift_sections.append(("Removed Buy/Add Watch", removed[:20]))
        deterioration = [
            row[0]
            for row in conn.execute(
                """
                SELECT latest.ticker
                FROM daily_ranker_scores latest
                JOIN daily_ranker_scores previous
                  ON latest.ticker = previous.ticker
                 AND latest.ranker_mode = previous.ranker_mode
                WHERE latest.run_id = ?
                  AND previous.run_id = ?
                  AND latest.run_type = 'production'
                  AND previous.run_type = 'production'
                  AND latest.ranker_mode = 'expanded_universe'
                  AND previous.confidence NOT ILIKE '%Low%'
                  AND latest.confidence ILIKE '%Low%'
                ORDER BY latest.ticker
                LIMIT 20
                """,
                [latest_run_id, previous_run_id],
            ).fetchall()
        ]
        drift_sections.append(("Confidence Deterioration", deterioration))
    else:
        drift_sections.append(("Previous Production Comparison", ["No previous production run available."]))

    report_path = PROJECT_ROOT / "outputs" / "action_bias_drift_report.md"
    if write_report:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Action Bias Drift Report",
            "",
            "Not financial advice",
            "",
            "Model output requires human review",
            "",
            "Data quality may affect results",
            "",
            "Research-only output. No automatic trading, brokerage connection, or order placement is performed.",
            "",
            "## Latest Production Run Summary",
            "",
            f"- Trading date: {trading_date or 'N/A'}",
            f"- Latest run_id: {latest_run_id}",
            f"- Previous production run_id: {previous_run_id or 'N/A'}",
            "",
            "## Action Bias Counts",
            "",
        ]
        if counts:
            for mode, bias, count in counts:
                lines.append(f"- {mode} / {bias}: {count}")
        else:
            lines.append("- None")
        lines.extend(["", "## Counts By Ranker Mode", ""])
        mode_counts = conn.execute(
            """
            SELECT ranker_mode, COUNT(*)
            FROM daily_ranker_scores
            WHERE run_id = ? AND run_type = 'production'
            GROUP BY ranker_mode
            ORDER BY ranker_mode
            """,
            [latest_run_id],
        ).fetchall()
        for mode, count in mode_counts:
            lines.append(f"- {mode}: {count}")
        lines.extend(["", "## Top Expanded Candidates", ""])
        if top:
            for ticker, company, score, bias, confidence in top:
                lines.append(f"- {ticker} ({company}): action_score={format_value(score)}, action_bias={bias}, confidence={confidence}")
        else:
            lines.append("- None")
        lines.extend(["", "## Low Confidence / Data Gap Watch", ""])
        if low_confidence:
            for ticker, company, score, bias, confidence, data_quality in low_confidence:
                lines.append(
                    f"- {ticker} ({company}): action_score={format_value(score)}, action_bias={bias}, "
                    f"confidence={confidence}, data_quality={format_value(data_quality)}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Changes Vs Previous Production Run", ""])
        for title, values in drift_sections:
            lines.append(f"### {title}")
            if values:
                for value in values:
                    lines.append(f"- {value}")
            else:
                lines.append("- None")
            lines.append("")
        lines.extend(["## Duplicate Production Guard", ""])
        if duplicate_rows:
            lines.append("- Duplicate production groups found; review before using production history.")
            for trading, mode, source, runs, row_count in duplicate_rows:
                lines.append(f"- {trading} / {mode} / {source}: production_runs={runs}, rows={row_count}")
        else:
            lines.append("- No duplicate production groups detected.")
        lines.extend(["", "## Human Review Notes", ""])
        lines.append("- Do not treat action_bias as a buy/sell instruction.")
        lines.append("- Re-run focused research before acting.")
        lines.append("- Options analysis remains unavailable unless real options data is added later.")
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Action bias drift report: {report_path}")
    print()
    print("Action Bias Counts")
    print_rows(["mode", "action_bias", "rows"], counts)
    print()
    print("Top Expanded Candidates")
    print_rows(["ticker", "company", "action_score", "action_bias", "confidence"], top[:10])


def command_production_ticker_history(conn: Any, ticker: str) -> None:
    normalized = ticker.strip().upper()
    rows = conn.execute(
        """
        SELECT trading_date, run_id, ranker_mode, action_score, action_bias, confidence, options_analysis_status
        FROM daily_ranker_scores
        WHERE run_type = 'production'
          AND ticker = ?
        ORDER BY trading_date DESC NULLS LAST, loaded_at DESC, ranker_mode
        LIMIT 50
        """,
        [normalized],
    ).fetchall()
    print(f"Production ticker history: {normalized}")
    print_rows(["trading_date", "run_id", "mode", "action_score", "action_bias", "confidence", "options"], rows)


def command_low_confidence_latest(conn: Any) -> None:
    latest = latest_production_run(conn)
    if not latest:
        print("No production warehouse run found.")
        return
    run_id, _ = latest
    rows = conn.execute(
        f"""
        SELECT ticker, company_name, action_score, action_bias, confidence, data_quality_score
        FROM daily_ranker_scores
        WHERE run_id = ?
          AND run_type = 'production'
          AND ranker_mode = 'expanded_universe'
          AND {LOW_CONFIDENCE_PREDICATE}
        ORDER BY data_quality_score ASC NULLS FIRST, action_score DESC NULLS LAST, ticker
        LIMIT 40
        """,
        [run_id],
    ).fetchall()
    if not rows:
        print("No low-confidence/data-gap rows found for latest production run.")
        return
    print_rows(["ticker", "company", "action_score", "action_bias", "confidence", "data_quality"], rows)


def command_duplicate_production_check(conn: Any) -> None:
    rows = conn.execute(
        """
        SELECT trading_date, ranker_mode, source_file, COUNT(DISTINCT run_id) AS production_runs, COUNT(*) AS rows
        FROM daily_ranker_scores
        WHERE run_type = 'production'
        GROUP BY trading_date, ranker_mode, source_file
        HAVING COUNT(DISTINCT run_id) > 1
        ORDER BY trading_date DESC NULLS LAST, ranker_mode, source_file
        """
    ).fetchall()
    if rows:
        print("Duplicate production groups found:")
        print_rows(["trading_date", "mode", "source_file", "runs", "rows"], rows)
    else:
        print("No duplicate production groups detected.")


def command_ticker_history(conn: Any, ticker: str) -> None:
    normalized = ticker.strip().upper()
    print(f"Ticker history: {normalized}")
    print()
    print("Daily score history:")
    rows = conn.execute(
        """
        SELECT run_id, loaded_at, strategy, final_score, cad_alternative
        FROM daily_investment_scores
        WHERE ticker = ?
        ORDER BY loaded_at DESC
        LIMIT 20
        """,
        [normalized],
    ).fetchall()
    print_rows(["run_id", "loaded_at", "strategy", "score", "cad"], rows)
    print()
    print("Earnings calendar history:")
    rows = conn.execute(
        """
        SELECT run_id, loaded_at, earnings_date, provider, provider_status, importance_score, data_status
        FROM index_weekly_earnings_calendar
        WHERE ticker = ?
        ORDER BY loaded_at DESC
        LIMIT 20
        """,
        [normalized],
    ).fetchall()
    print_rows(["run_id", "loaded_at", "earnings", "provider", "provider_status", "importance", "status"], rows)
    print()
    print("Research task history:")
    rows = conn.execute(
        """
        SELECT run_id, loaded_at, priority, task_type, status
        FROM research_desk_tasks
        WHERE ticker = ?
        ORDER BY loaded_at DESC
        LIMIT 20
        """,
        [normalized],
    ).fetchall()
    print_rows(["run_id", "loaded_at", "priority", "task_type", "status"], rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query the Pixiu DuckDB research warehouse.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("latest-run")
    subparsers.add_parser("summary")
    subparsers.add_parser("top-ranked")
    subparsers.add_parser("data-gaps")
    subparsers.add_parser("daily-ranker-latest")
    subparsers.add_parser("daily-ranker-expanded-latest")
    subparsers.add_parser("action-bias-summary")
    subparsers.add_parser("data-quality-watch")
    subparsers.add_parser("production-latest")
    subparsers.add_parser("production-action-bias-summary")
    subparsers.add_parser("action-bias-drift")
    subparsers.add_parser("low-confidence-latest")
    subparsers.add_parser("duplicate-production-check")
    production_ticker_history = subparsers.add_parser("production-ticker-history")
    production_ticker_history.add_argument("ticker")
    ticker_daily_history = subparsers.add_parser("ticker-daily-ranker-history")
    ticker_daily_history.add_argument("ticker")
    action_bias_history = subparsers.add_parser("action-bias-history")
    action_bias_history.add_argument("action_bias")
    subparsers.add_parser("table-counts")
    ticker_history = subparsers.add_parser("ticker-history")
    ticker_history.add_argument("ticker")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect()
    try:
        if args.command == "latest-run":
            command_latest_run(conn)
        elif args.command == "summary":
            command_summary(conn)
        elif args.command == "top-ranked":
            command_top_ranked(conn)
        elif args.command == "data-gaps":
            command_data_gaps(conn)
        elif args.command == "daily-ranker-latest":
            command_daily_ranker_latest(conn)
        elif args.command == "daily-ranker-expanded-latest":
            command_daily_ranker_expanded_latest(conn)
        elif args.command == "action-bias-summary":
            command_action_bias_summary(conn)
        elif args.command == "ticker-daily-ranker-history":
            command_ticker_daily_ranker_history(conn, args.ticker)
        elif args.command == "action-bias-history":
            command_action_bias_history(conn, args.action_bias)
        elif args.command == "data-quality-watch":
            command_data_quality_watch(conn)
        elif args.command == "production-latest":
            command_production_latest(conn)
        elif args.command == "production-action-bias-summary":
            command_production_action_bias_summary(conn)
        elif args.command == "action-bias-drift":
            command_action_bias_drift(conn)
        elif args.command == "production-ticker-history":
            command_production_ticker_history(conn, args.ticker)
        elif args.command == "low-confidence-latest":
            command_low_confidence_latest(conn)
        elif args.command == "duplicate-production-check":
            command_duplicate_production_check(conn)
        elif args.command == "ticker-history":
            command_ticker_history(conn, args.ticker)
        elif args.command == "table-counts":
            command_table_counts(conn)
        else:
            raise SystemExit(f"Unknown command: {args.command}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
