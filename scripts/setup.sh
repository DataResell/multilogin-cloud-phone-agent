#!/usr/bin/env bash
# Bootstrap the mlxphone toolkit from a fresh clone: create a venv and install deps.
# Uses `python -m pip` (portable; avoids non-executable .venv/bin/pip under some sandboxes).
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: '$PYTHON' not found. Install Python 3.9+ (3.11+ recommended) and retry." >&2
  exit 1
fi

# Require Python 3.9+; 3.11+ is recommended (avoids the LibreSSL urllib3 warning).
read -r major minor < <("$PYTHON" -c 'import sys; print(sys.version_info[0], sys.version_info[1])')
if [ "$major" -ne 3 ] || [ "$minor" -lt 9 ]; then
  echo "error: Python $major.$minor found; this toolkit needs Python 3.9+ (3.11+ recommended)." >&2
  exit 1
fi

echo "[setup] creating .venv with $PYTHON (3.$minor)"
"$PYTHON" -m venv .venv

echo "[setup] upgrading pip and installing dependencies"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

cat <<'DONE'

[setup] done. Next steps:
  cp .env.example .env      # then fill in real values (email/password or MLX_TOKEN, MOBILE_PROFILE_ID)
  make doctor               # validate before spending any mobile minutes
  make dry-run              # walk the flow with no network/device
  make demo                 # real end-to-end demo
DONE
