#!/usr/bin/env bash
set -euo pipefail

python -m uvicorn oj.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT
OJ_API_URL=http://127.0.0.1:8000 python -m streamlit run frontend/app.py \
  --server.address 127.0.0.1 --server.port 8501

