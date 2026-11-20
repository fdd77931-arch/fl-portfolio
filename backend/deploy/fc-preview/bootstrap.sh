#!/bin/sh
set -eu
cd /code/backend
export PYTHONPATH="/code/backend/vendor:/code/backend"
export HEALTH_AI_DB="/tmp/health-ai/knowledge.db"
exec /var/fc/lang/python3.12/bin/python3.12 -m uvicorn preview:app --host 0.0.0.0 --port 9000 --no-access-log
