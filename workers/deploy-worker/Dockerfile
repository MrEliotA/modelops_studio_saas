FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY workers/deploy-worker /app/workers/deploy-worker
RUN pip install --no-cache-dir -r /app/workers/deploy-worker/requirements.txt
WORKDIR /app/workers/deploy-worker
CMD ["python","main.py"]
