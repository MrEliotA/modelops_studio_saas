FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY workers/metering-worker /app/workers/metering-worker
RUN pip install --no-cache-dir -r /app/workers/metering-worker/requirements.txt
WORKDIR /app/workers/metering-worker
CMD ["python","main.py"]
