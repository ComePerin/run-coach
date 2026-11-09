#!/usr/bin/env bash
# One-time setup: fetch the official COROS MCP helper, create a venv, start login.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .vendor/COROS-MCP ]; then
  echo "→ fetching official COROS MCP helper (coroslab/COROS-MCP)"
  git clone --depth 1 https://github.com/coroslab/COROS-MCP.git .vendor/COROS-MCP
else
  echo "→ updating .vendor/COROS-MCP"
  git -C .vendor/COROS-MCP pull --ff-only --quiet || true
fi

if [ ! -d .venv ]; then
  echo "→ creating .venv"
  python3 -m venv .venv
fi
.venv/bin/pip install --quiet -e '.[dev]'

if .venv/bin/python scripts/coros.py status 2>/dev/null; then
  echo "✓ already logged in"
  exit 0
fi

echo "→ starting COROS login"
.venv/bin/python scripts/coros.py login
echo
echo "Open the link above in any browser and sign in with your COROS account."
echo "Then run:  .venv/bin/python scripts/coros.py login-finish"
