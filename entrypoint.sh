#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for MySQL..."
python - <<'PY'
import os
import sys
import time

import pymysql

host = os.getenv("DB_HOST", "mysql")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER", "appuser")
password = os.getenv("DB_PASSWORD", "apppw")
database = os.getenv("DB_NAME", "code_platform")

deadline = time.time() + 120
while True:
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=3,
        )
        conn.close()
        print("MySQL is ready")
        break
    except Exception as exc:
        if time.time() >= deadline:
            print(f"MySQL wait timeout: {exc}", file=sys.stderr)
            raise
        time.sleep(2)
PY

echo "Running Alembic migrations..."
alembic -c alembic.ini upgrade head

echo "Starting FastAPI..."
exec python -m server.runtime_server --host 0.0.0.0 --workers "${UVICORN_WORKERS:-4}"
