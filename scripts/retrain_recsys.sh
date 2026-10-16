#!/usr/bin/env bash
# Weekly recsys retrain wrapper for EC2
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV="${VENV:-/home/ec2-user/flask-app/env}"
PY="${PY:-$VENV/bin/python}"

exec "$PY" scripts/retrain_recsys.py "$@"
