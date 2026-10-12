#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,15), "Requiere Python 3.11 a 3.14"'
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
if [ ! -f .env ]; then cp .env.example .env; fi
printf '\nInstalacion completada. Ejecuta: .venv/bin/python run.py\n'
