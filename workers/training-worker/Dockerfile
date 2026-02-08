FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY workers/training-worker /app/workers/training-worker
RUN pip install --no-cache-dir -r /app/workers/training-worker/requirements.txt
WORKDIR /app/workers/training-worker
CMD ["python","main.py"]
