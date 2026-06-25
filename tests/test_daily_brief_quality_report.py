from __future__ import annotations

import csv
import importlib.util
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "generate_daily_brief_quality_report.py"


def load_module():
    spec = importlib.util.spec_from_file_location("daily_brief_quality", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def touch_date(path: Path, value: date) -> None:
    stamp = datetime.combine(value, datetime.min.time()).timestamp()
    os.utime(path, (stamp, stamp))


class DailyBriefQualityReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.outputs = self.root / "outputs"
        self.as_of_date = date(2026, 6, 24)
        self.write_valid_artifacts()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_valid_artifacts(self) -> None:
        default_rows = [
            {
                "ticker": f"DEF{i:02d}",
                "final_score": str(100 - i),
                "strategy": "Ranked Buy Candidate",
                "confidence": "Medium",
                "cad_alternative": "N/A",
                "cad_note": "Verify manually.",
                "key_risk": "Not financial advice; Model output requires human review.",
            }
            for i in range(38)
        ]
        default_rows[0]["ticker"] = "ALPHA"
        expanded_rows = [
            {
                "ticker": f"EXP{i:03d}",
                "action_score": str(100 - i / 10),
                "action_bias": "Buy/Add Watch",
                "confidence": "Medium-High",
                "data_quality_score": "95",
                "primary_reason": "deterministic prefilter score=100",
                "risk_flags": "Research-only output requires human review",
                "cad_alternative": "N/A",
            }
            for i in range(100)
        ]
        expanded_rows[0]["ticker"] = "BETA"
        write_csv(
            self.outputs / "daily_investment_scores.csv",
            ["ticker", "final_score", "strategy", "confidence", "cad_alternative", "cad_note", "key_risk"],
            default_rows,
        )
        write_csv(
            self.outputs / "expanded_daily_investment_scores.csv",
            [
                "ticker",
                "action_score",
                "action_bias",
                "confidence",
                "data_quality_score",
                "primary_reason",
                "risk_flags",
                "cad_alternative",
            ],
            expanded_rows,
        )
        write_csv(
            self.outputs / "signal_outcomes.csv",
            ["ticker", "signal_date", "action_bias", "action_score", "confidence", "outcome_status"],
            [
                {
                    "ticker": "ALPHA",
                    "signal_date": "2026-06-23",
                    "action_bias": "Buy/Add Watch",
                    "action_score": "80",
                    "confidence": "Medium-High",
                    "outcome_status": "ok",
                },
                {
                    "ticker": "BETA",
                    "signal_date": "2026-06-23",
                    "action_bias": "Buy/Add Watch",
                    "action_score": "79",
                    "confidence": "Medium-High",
                    "outcome_status": "ok",
                },
            ],
        )
        (self.outputs / "daily_brief_report.md").write_text(
            "\n".join(
                [
                    "# Pixiu Daily Brief Report",
                    "",
                    "- Safety: research-only; no broker connectivity, order placement, trade automation, or secret handling.",
                    "- Disclaimer: Not financial advice. Model output requires human review. Data quality may affect results.",
                    "",
                    "## 1. Executive Summary / Daily Summary",
                    "",
                    "- Default watchlist rows: **38**",
                    "- Expanded universe rows: **100**",
                    "- Top default watchlist candidate: **ALPHA**",
                    "- Top expanded-universe candidate: **BETA**",
                    "",
                    "## 2. Default Watchlist Top Candidates",
                    "| Ticker | Score |",
                    "| --- | --- |",
                    "| ALPHA | 100 |",
                    "| DEF01 | 99 |",
                    "| DEF02 | 98 |",
                    "| DEF03 | 97 |",
                    "| DEF04 | 96 |",
                    "| DEF05 | 95 |",
                    "| DEF06 | 94 |",
                    "| DEF07 | 93 |",
                    "| DEF08 | 92 |",
                    "| DEF09 | 91 |",
                    "",
                    "## 3. Expanded-Universe Top Candidates",
                    "| Ticker | Action Score |",
                    "| --- | --- |",
                    "| BETA | 100 |",
                    "| EXP001 | 99.9 |",
                    "| EXP002 | 99.8 |",
                    "| EXP003 | 99.7 |",
                    "| EXP004 | 99.6 |",
                    "| EXP005 | 99.5 |",
                    "| EXP006 | 99.4 |",
                    "| EXP007 | 99.3 |",
                    "| EXP008 | 99.2 |",
                    "| EXP009 | 99.1 |",
                    "",
                    "## 4. Action / Strategy Distribution",
                    "",
                    "## 5. Human Review Queue / Manual Review Queue",
                    "",
                    "## 6. Data Quality / Risk Notes",
                    "",
                    "## 7. Output References",
                    "",
                    "## 8. Next Human Checklist",
                    "",
                    "- Do not treat any row as an order or recommendation without independent review.",
                ]
            ),
            encoding="utf-8",
        )
        (self.outputs / "action_bias_drift_report.md").write_text(
            "\n".join(
                [
                    "# Action Bias Drift Report",
                    "",
                    "## Duplicate Production Guard",
                    "",
                    "- No duplicate production groups detected.",
                ]
            ),
            encoding="utf-8",
        )
        (self.outputs / "signal_outcomes_report.md").write_text(
            "# Pixiu Signal Outcome Tracking Report\n\nResearch-only. Not financial advice.\n",
            encoding="utf-8",
        )
        log_dir = self.outputs / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "pixiu-production-2026-06-24.log").write_text(
            "Pixiu Daily Production Research Run\nFinal script exit: 0\nDuplicate production check:\nNo duplicate production groups detected.\n",
            encoding="utf-8",
        )
        for path in self.outputs.rglob("*"):
            if path.is_file():
                touch_date(path, self.as_of_date)

    def build_report(self):
        quality = load_module()
        config = quality.AuditConfig(root=self.root, as_of_date=self.as_of_date)
        return quality.build_quality_audit(config)

    def test_valid_artifacts_can_produce_use_verdict(self) -> None:
        report = self.build_report()

        self.assertEqual(report.verdict, "USE")
        self.assertEqual(report.hard_failures, [])
        self.assertEqual(report.warnings, [])

    def test_stale_required_artifact_forces_do_not_use(self) -> None:
        touch_date(self.outputs / "daily_investment_scores.csv", self.as_of_date - timedelta(days=3))

        report = self.build_report()

        self.assertEqual(report.verdict, "DO NOT USE")
        self.assertTrue(any("stale" in item.lower() for item in report.hard_failures))

    def test_top_candidate_mismatch_forces_do_not_use(self) -> None:
        brief = (self.outputs / "daily_brief_report.md").read_text(encoding="utf-8")
        (self.outputs / "daily_brief_report.md").write_text(brief.replace("**ALPHA**", "**OMEGA**"), encoding="utf-8")
        touch_date(self.outputs / "daily_brief_report.md", self.as_of_date)

        report = self.build_report()

        self.assertEqual(report.verdict, "DO NOT USE")
        self.assertTrue(any("top default" in item.lower() for item in report.hard_failures))

    def test_missing_top_candidate_outcome_coverage_is_warning(self) -> None:
        write_csv(
            self.outputs / "signal_outcomes.csv",
            ["ticker", "signal_date", "action_bias", "action_score", "confidence", "outcome_status"],
            [
                {
                    "ticker": "ALPHA",
                    "signal_date": "2026-06-23",
                    "action_bias": "Buy/Add Watch",
                    "action_score": "80",
                    "confidence": "Medium-High",
                    "outcome_status": "ok",
                }
            ],
        )
        touch_date(self.outputs / "signal_outcomes.csv", self.as_of_date)

        report = self.build_report()

        self.assertEqual(report.verdict, "REVIEW CAREFULLY")
        self.assertTrue(any("missing signal-outcome coverage" in item.lower() for item in report.warnings))


if __name__ == "__main__":
    unittest.main()
