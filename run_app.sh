#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PYTHON=".venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "[1/3] Tạo môi trường Python local..."
  "$PYTHON_BIN" -m venv .venv
fi

echo "[2/3] Kiểm tra thư viện..."
if ! "$VENV_PYTHON" -c "import streamlit, pandas" >/dev/null 2>&1; then
  "$VENV_PYTHON" -m pip install streamlit pandas
fi

export MINFIT_SQL_SERVER="${MINFIT_SQL_SERVER:-sqlite}"
export MINFIT_SQLITE_PATH="${MINFIT_SQLITE_PATH:-$(pwd)/data/minfit.sqlite3}"
export STREAMLIT_BROWSER_GATHER_USAGE_STATS="false"

if curl --silent --fail --max-time 1 http://127.0.0.1:8501 >/dev/null 2>&1; then
  echo "MinFit đang chạy tại http://127.0.0.1:8501"
  exit 0
fi

echo "[3/3] Khởi động MinFit tại http://127.0.0.1:8501"
exec "$VENV_PYTHON" -m streamlit run app.py \
  --server.address 127.0.0.1 \
  --server.port 8501 \
  --server.headless true \
  --browser.gatherUsageStats false
