#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = BASE_DIR / "templates" / "pixiu_command_packet.template.json"
LOG_DIR = BASE_DIR / "outputs" / "dev_loop_bridge"

LEVEL3_KEYWORDS = [
    "git commit",
    "git push",
    "snapshot",
    "rm ",
    "rm -",
    "duckdb",
    "schema",
    "migration",
    "provider",
    "api integration",
    "scoring formula",
    "brokerage",
    "order",
    "credential",
]


def run_command(command: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(command, cwd=BASE_DIR, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def git_status() -> str:
    _, out, _ = run_command(["git", "status", "--short"])
    return out.strip()


def git_commits() -> str:
    _, out, _ = run_command(["git", "log", "--oneline", "-8"])
    return out.strip()


def blocked_tracked_file_check() -> tuple[bool, str]:
    code, out, _ = run_command([
        "bash",
        "-lc",
        r"git ls-files | grep -E '(^outputs/|^backups/|^snapshots/|\.duckdb|\.env|\.tar\.gz|\.log$)'",
    ])
    if code == 0 and out.strip():
        return False, out.strip()
    return True, "PASS: no generated/sensitive files tracked"


def command_packet_level(packet: dict[str, Any]) -> int:
    level = int(packet.get("level", 1))
    command = str(packet.get("command", "")).lower()
    if any(keyword in command for keyword in LEVEL3_KEYWORDS):
        return max(level, 3)
    return level


def load_packet(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        packet = json.load(handle)
    required = {"label", "level", "purpose", "command", "requires_yes"}
    missing = required - set(packet)
    if missing:
        raise ValueError(f"packet missing required keys: {sorted(missing)}")
    return packet


def write_bridge_log(label: str, body: str) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in label).strip("-")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = LOG_DIR / f"{timestamp}-{safe_label or 'dev-loop'}.txt"
    path.write_text(body, encoding="utf-8")
    return path


def status() -> int:
    ok, safety = blocked_tracked_file_check()
    print("=== PIXIU DEV BRIDGE STATUS ===")
    print(f"time: {datetime.now().isoformat(timespec='seconds')}")
    print(f"workdir: {BASE_DIR}")
    print()
    print("=== GIT STATUS ===")
    print(git_status() or "clean")
    print()
    print("=== LATEST COMMITS ===")
    print(git_commits())
    print()
    print("=== TRACKED FILE SAFETY ===")
    print(safety)
    return 0 if ok else 1


def classify(path: Path) -> int:
    packet = load_packet(path)
    effective_level = command_packet_level(packet)
    requires_yes = bool(packet.get("requires_yes")) or effective_level >= 3

    print("=== PIXIU COMMAND PACKET CLASSIFICATION ===")
    print(f"packet: {path}")
    print(f"label: {packet.get('label')}")
    print(f"declared_level: {packet.get('level')}")
    print(f"effective_level: {effective_level}")
    print(f"requires_yes: {requires_yes}")
    print(f"purpose: {packet.get('purpose')}")
    return 0


def execute(path: Path, yes_level3: bool = False) -> int:
    packet = load_packet(path)
    effective_level = command_packet_level(packet)
    requires_yes = bool(packet.get("requires_yes")) or effective_level >= 3

    if requires_yes and not yes_level3:
        print("REFUSED: Level 3 or requires_yes packet needs explicit --yes-level3.")
        print(f"label: {packet.get('label')}")
        print(f"effective_level: {effective_level}")
        return 2

    command = str(packet["command"])
    started = datetime.now()
    code, out, err = run_command(["bash", "-lc", command])

    body = textwrap.dedent(
        f"""
        === PIXIU DEV BRIDGE EXECUTION ===
        time: {started.isoformat(timespec='seconds')}
        label: {packet.get('label')}
        level: {effective_level}
        command: {command}

        === STDOUT ===
        {out}

        === STDERR ===
        {err}

        === EXIT CODE ===
        {code}

        === GIT STATUS AFTER ===
        {git_status() or 'clean'}
        """
    ).strip() + "\n"

    log_path = write_bridge_log(str(packet.get("label", "packet")), body)
    print(body)
    print(f"bridge_log: {log_path}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Pixiu local dev-loop bridge.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    p_classify = sub.add_parser("classify")
    p_classify.add_argument("--packet", type=Path, default=DEFAULT_PACKET)

    p_execute = sub.add_parser("execute")
    p_execute.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    p_execute.add_argument("--yes-level3", action="store_true")

    args = parser.parse_args()

    if args.cmd == "status":
        return status()
    if args.cmd == "classify":
        return classify(args.packet)
    if args.cmd == "execute":
        return execute(args.packet, yes_level3=args.yes_level3)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
