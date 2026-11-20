FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && mkdir /data && chown 10001:10001 /data
COPY backend/health_ai backend/health_ai
COPY backend/data backend/data
COPY demos/xunji demos/xunji
WORKDIR /app/backend
ENV HEALTH_AI_DB=/data/knowledge.db PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
EXPOSE 8080
CMD ["sh", "-ec", "exec uvicorn health_ai.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --no-access-log"]
