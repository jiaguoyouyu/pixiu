#!/usr/bin/env python3
"""
Pixiu v2.2F.1 local command queue and AI clipboard bundle helper.

Local-only dev-loop utility:
- Executes local command queues.
- Refuses Level 3 queues unless explicit --yes-level3 is provided.
- Writes logs under outputs/dev_loop_queue/.
- Optionally copies AI bundle to macOS clipboard through pbcopy.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_ROOT = ROOT / "outputs" / "dev_loop_queue"
BRIDGE_LOG_ROOT = ROOT / "outputs" / "dev_loop_bridge"

LEVEL3_PATTERNS = [
    r"\bgit\s+commit\b",
    r"\bgit\s+push\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+clean\b",
    r"\brm\s+-rf\b",
    r"\bsudo\b",
    r"\bsnapshot\b",
    r"\bsnapshots/",
    r"\btar\s+-c",
    r"\bmigration\b",
    r"\bschema\b",
    r"\.env\b",
    r"\bAPI[_ -]?KEY\b",
    r"\btoken\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bprovider\b",
    r"\bbroker\b",
    r"\btrade\b",
    r"\border\b",
]

LEVEL2_PATTERNS = [
    r"verify_daily_production_research\.sh",
    r"run_daily_production_research\.sh",
    r"run_daily_report\.sh",
    r"track_signal_outcomes\.py",
    r"generate_partnership_catalyst_report\.py",
    r"apply_patch",
    r"cat\s+>",
    r"tee\s+",
    r"python3?\s+-\s*<<",
]


@dataclass(frozen=True)
class QueueCommand:
    label: str
    command: str
    declared_level: int | None
    effective_level: int


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def slug(value: str, fallback: str = "queue") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return cleaned[:80] or fallback


def run_capture(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def git_status() -> str:
    code, out, err = run_capture(["git", "status", "--short"])
    if code:
        return "git status failed: " + err.strip()
    return out.strip() or "clean"


def latest_commits(limit: int = 5) -> str:
    code, out, err = run_capture(["git", "log", "--oneline", f"-{limit}"])
    if code:
        return "git log failed: " + err.strip()
    return out.strip()


def infer_level(command: str) -> int:
    for pattern in LEVEL3_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return 3
    for pattern in LEVEL2_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return 2
    return 1


def normalize_level(value: Any) -> int | None:
    if value is None:
        return None
    try:
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"level must be 1, 2, or 3; got {value!r}") from exc
    if level not in (1, 2, 3):
        raise ValueError(f"level must be 1, 2, or 3; got {level}")
    return level


def resolve_queue_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def load_queue(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"queue file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("queue root must be object")
    commands = data.get("commands")
    if not isinstance(commands, list) or not commands:
        raise ValueError("queue.commands must be non-empty list")
    return data


def parse_commands(data: dict[str, Any]) -> list[QueueCommand]:
    parsed: list[QueueCommand] = []
    for idx, raw in enumerate(data["commands"], start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"command {idx} must be object")
        label = str(raw.get("label") or f"command-{idx}")
        command = str(raw.get("command") or "").strip()
        if not command:
            raise ValueError(f"command {idx} is empty")
        declared = normalize_level(raw.get("level"))
        effective = max(declared or 1, infer_level(command))
        parsed.append(QueueCommand(label=label, command=command, declared_level=declared, effective_level=effective))
    return parsed


def classify_text(data: dict[str, Any]) -> str:
    commands = parse_commands(data)
    max_level = max(c.effective_level for c in commands)
    lines = [
        "=== PIXIU DEV QUEUE CLASSIFICATION ===",
        f"time: {iso_now()}",
        f"queue_label: {data.get('queue_label', 'unnamed')}",
        f"command_count: {len(commands)}",
        f"max_level: {max_level}",
        f"requires_yes_level3: {'yes' if max_level >= 3 else 'no'}",
        "",
        "=== COMMANDS ===",
    ]
    for i, c in enumerate(commands, start=1):
        declared = c.declared_level if c.declared_level is not None else "auto"
        lines.extend(
            [
                f"{i}. label: {c.label}",
                f"   declared_level: {declared}",
                f"   effective_level: {c.effective_level}",
                f"   command: {c.command}",
            ]
        )
    return "\n".join(lines)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_clipboard(text: str) -> str:
    if not shutil.which("pbcopy"):
        return "pbcopy unavailable"
    proc = subprocess.run(["pbcopy"], input=text, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return "copied to clipboard" if proc.returncode == 0 else "pbcopy failed: " + proc.stderr.strip()


def status() -> int:
    print("=== PIXIU DEV QUEUE STATUS ===")
    print(f"time: {iso_now()}")
    print(f"project_root: {ROOT}")
    print(f"log_root: {LOG_ROOT}")
    print(f"template_exists: {(ROOT / 'templates' / 'pixiu_command_queue.template.json').exists()}")
    print()
    print("=== GIT STATUS ===")
    print(git_status())
    print()
    print("=== LATEST COMMITS ===")
    print(latest_commits(8))
    return 0


def execute(data: dict[str, Any], path: Path, yes_level3: bool, no_copy: bool, continue_on_error: bool) -> int:
    commands = parse_commands(data)
    max_level = max(c.effective_level for c in commands)
    if max_level >= 3 and not yes_level3:
        print("REFUSED: queue contains Level 3 command(s). Re-run only after explicit user approval with --yes-level3.")
        print(classify_text(data))
        return 2

    label = str(data.get("queue_label") or path.stem)
    run_dir = LOG_ROOT / f"{stamp()}-{slug(label)}"
    run_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "=== PIXIU DEV QUEUE AI BUNDLE ===",
        f"time: {iso_now()}",
        f"project_root: {ROOT}",
        f"queue_file: {path}",
        f"queue_label: {label}",
        f"command_count: {len(commands)}",
        f"max_level: {max_level}",
        f"git_status_before: {git_status()}",
        "",
        "=== CLASSIFICATION ===",
        classify_text(data),
        "",
        "=== EXECUTION RESULTS ===",
    ]

    overall = 0
    stop_on_error = bool(data.get("stop_on_error", True)) and not continue_on_error

    for i, c in enumerate(commands, start=1):
        proc = subprocess.run(c.command, cwd=ROOT, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0 and overall == 0:
            overall = proc.returncode

        block = [
            f"--- COMMAND {i}: {c.label} ---",
            f"level: {c.effective_level}",
            f"command: {c.command}",
            "",
            "STDOUT:",
            proc.stdout.rstrip(),
            "",
            "STDERR:",
            proc.stderr.rstrip(),
            "",
            f"EXIT_CODE: {proc.returncode}",
            "",
        ]
        text = "\n".join(block)
        write_text(run_dir / f"{i:02d}-{slug(c.label, f'command-{i}')}.txt", text)
        lines.append(text)

        if proc.returncode != 0 and stop_on_error:
            lines.append("Queue stopped after first non-zero exit code.")
            break

    lines.extend(
        [
            "=== GIT STATUS AFTER ===",
            git_status(),
            "",
            "=== LATEST COMMITS ===",
            latest_commits(5),
            "",
            f"run_dir: {run_dir}",
            f"overall_exit_code: {overall}",
        ]
    )

    bundle = "\n".join(lines).rstrip() + "\n"
    bundle_path = run_dir / "AI_BUNDLE.txt"
    write_text(bundle_path, bundle)

    copy_status = "copy skipped (--no-copy)" if no_copy else copy_clipboard(bundle)
    print(bundle)
    print(f"ai_bundle: {bundle_path}")
    print(f"copy_status: {copy_status}")
    return overall


def latest_bundle(limit: int, no_copy: bool) -> int:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    logs: list[Path] = []
    for base in (LOG_ROOT, BRIDGE_LOG_ROOT):
        if base.exists():
            logs.extend([p for p in base.rglob("*.txt") if p.is_file()])
    logs = sorted(logs, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]

    lines = [
        "=== PIXIU LATEST DEV LOGS AI BUNDLE ===",
        f"time: {iso_now()}",
        f"project_root: {ROOT}",
        f"git_status: {git_status()}",
        f"log_count: {len(logs)}",
        "",
    ]

    for path in logs:
        try:
            display = path.relative_to(ROOT)
        except ValueError:
            display = path
        lines.extend([f"--- LOG: {display} ---", path.read_text(encoding="utf-8", errors="replace").rstrip(), ""])

    bundle = "\n".join(lines).rstrip() + "\n"
    out = LOG_ROOT / f"{stamp()}-latest-ai-bundle.txt"
    write_text(out, bundle)

    copy_status = "copy skipped (--no-copy)" if no_copy else copy_clipboard(bundle)
    print(bundle)
    print(f"ai_bundle: {out}")
    print(f"copy_status: {copy_status}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pixiu local command queue and AI bundle helper.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    classify = sub.add_parser("classify")
    classify.add_argument("--queue", required=True, type=Path)

    execute_parser = sub.add_parser("execute")
    execute_parser.add_argument("--queue", required=True, type=Path)
    execute_parser.add_argument("--yes-level3", action="store_true")
    execute_parser.add_argument("--no-copy", action="store_true")
    execute_parser.add_argument("--continue-on-error", action="store_true")

    bundle = sub.add_parser("bundle")
    bundle.add_argument("--limit", type=int, default=5)
    bundle.add_argument("--no-copy", action="store_true")

    args = parser.parse_args()

    try:
        if args.cmd == "status":
            return status()
        if args.cmd == "classify":
            data = load_queue(resolve_queue_path(args.queue))
            print(classify_text(data))
            return 0
        if args.cmd == "execute":
            path = resolve_queue_path(args.queue)
            data = load_queue(path)
            return execute(data, path, args.yes_level3, args.no_copy, args.continue_on_error)
        if args.cmd == "bundle":
            return latest_bundle(max(1, args.limit), args.no_copy)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
