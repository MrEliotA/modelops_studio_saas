FROM python:3.11-slim
WORKDIR /app

# TLS root CAs for in-cluster HTTPS endpoints (if any).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY libs/common /app/libs/common
COPY workers/run-orchestrator /app/workers/run-orchestrator
RUN pip install --no-cache-dir -r /app/workers/run-orchestrator/requirements.txt

WORKDIR /app/workers/run-orchestrator
CMD ["python","main.py"]
