#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== PIXIU DEV LOOP STATUS ==="
date
echo
echo "=== WORKDIR ==="
pwd
echo
echo "=== GIT BRANCH ==="
git branch --show-current
echo
echo "=== GIT STATUS ==="
git status --short
echo
echo "=== LATEST COMMITS ==="
git log --oneline -8
echo
echo "=== BLOCKED TRACKED FILE CHECK ==="
git ls-files | grep -E "(^outputs/|^backups/|^snapshots/|\\.duckdb|\\.env|\\.tar\\.gz|\\.log$)" && {
  echo "ERROR: generated/sensitive files are tracked"
  exit 1
} || echo "PASS: no generated/sensitive files tracked"
echo
echo "=== RECENT COMMAND LOGS ==="
ls -t ~/Desktop/command-results/*.txt 2>/dev/null | head -10 || true
