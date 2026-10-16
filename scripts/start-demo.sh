#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d venv ]]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements-demo.txt

exec gunicorn demo_app:app \
  --bind 0.0.0.0:5000 \
  --workers 2 \
  --timeout 60
