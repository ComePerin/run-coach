#!/usr/bin/env bash
# One-time setup.
#   scripts/setup.sh            COROS: fetch the official COROS MCP helper, create a venv, start login
#   scripts/setup.sh --garmin   Garmin: create a venv with the Garmin Personal API client, store your API key
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" = "--garmin" ]; then
  PY=python3
  for v in python3.13 python3.12; do command -v "$v" >/dev/null && PY=$v && break; done
  if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then
    echo "✗ Garmin's Personal API client needs Python >= 3.12 (found $("$PY" -V))." >&2
    exit 1
  fi
  if [ ! -d .venv ]; then
    echo "→ creating .venv ($("$PY" -V))"
    "$PY" -m venv .venv
  fi
  .venv/bin/pip install --quiet -e '.[dev,garmin]'

  KEY_FILE="$HOME/.config/garmin/connect-personal-api-key"
  if [ -z "${GARMIN_PERSONAL_API_KEY:-}" ] && [ ! -s "$KEY_FILE" ]; then
    echo
    echo "Create a Personal API key in Garmin Connect (read-only access to your data):"
    echo "  https://connect.garmin.com/app/settings/personalApiToken"
    if [ -t 0 ]; then
      read -r -s -p "Paste the key here (input hidden), or press Enter to skip: " KEY; echo
      if [ -n "$KEY" ]; then
        mkdir -p "$(dirname "$KEY_FILE")"
        (umask 077 && printf '%s' "$KEY" > "$KEY_FILE")
        echo "→ key saved to $KEY_FILE (only readable by you)"
      fi
    fi
    if [ ! -s "$KEY_FILE" ]; then
      echo "Then save it with:  (umask 077; mkdir -p ~/.config/garmin; cat > $KEY_FILE)   # paste, Ctrl-D"
      echo "or export GARMIN_PERSONAL_API_KEY=… and run:  .venv/bin/python scripts/garmin.py status"
      exit 0
    fi
  fi
  .venv/bin/python scripts/garmin.py status
  exit 0
fi

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
