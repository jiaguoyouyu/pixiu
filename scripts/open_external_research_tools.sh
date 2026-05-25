#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SETUP_DOC="${PROJECT_ROOT}/docs/external_research_tools_setup.md"

KOYFIN_URL="https://app.koyfin.com/register"
FISCAL_AI_URL="https://fiscal.ai/"
QUARTR_URL="https://quartr.com/"

open_target() {
  target="$1"

  if command -v open >/dev/null 2>&1; then
    open "${target}"
    return $?
  fi

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${target}"
    return $?
  fi

  echo "No supported opener found. Open manually: ${target}"
  return 0
}

echo "Opening external research tool pages for manual setup."
echo "Research-only: this script opens URLs/docs only."
echo "It does not register accounts, log in, bypass CAPTCHA, verify email, submit payment, scrape pages, or store credentials."
echo
echo "Koyfin: ${KOYFIN_URL}"
echo "Fiscal.ai: ${FISCAL_AI_URL}"
echo "Quartr: ${QUARTR_URL}"
echo "Setup doc: ${SETUP_DOC}"
echo

open_target "${KOYFIN_URL}"
open_target "${FISCAL_AI_URL}"
open_target "${QUARTR_URL}"

if [[ -f "${SETUP_DOC}" ]]; then
  open_target "${SETUP_DOC}"
else
  echo "Setup doc not found: ${SETUP_DOC}"
fi

echo
echo "Manual setup only. Do not paste passwords, API keys, tokens, or private account data into this project."
