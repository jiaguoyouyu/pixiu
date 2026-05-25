#!/usr/bin/env python3
"""Backward-compatible wrapper for the Pixiu daily ranker entrypoint.

This file intentionally contains no scoring logic. Existing automations that
call scripts/investment_ranker.py continue to work while new runners call
scripts/pixiu.py directly.
"""

from __future__ import annotations

import runpy
from pathlib import Path


def main() -> int:
    pixiu_path = Path(__file__).with_name("pixiu.py")
    runpy.run_path(str(pixiu_path), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
