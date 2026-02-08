FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY workers/stream-feast-writer /app/workers/stream-feast-writer
RUN pip install --no-cache-dir -r /app/workers/stream-feast-writer/requirements.txt
WORKDIR /app/workers/stream-feast-writer
CMD ["python","-m","main"]
