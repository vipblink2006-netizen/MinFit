#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

export MINFIT_SQL_SERVER="${MINFIT_SQL_SERVER:-sqlite}"
export MINFIT_SQLITE_PATH="${MINFIT_SQLITE_PATH:-$(pwd)/data/minfit.sqlite3}"
export PORT="${PORT:-5173}"

echo "======================================================="
echo " Khởi động MinFit PropTech Web Application..."
echo "======================================================="

exec "$PYTHON_BIN" frontend_server.py

  
