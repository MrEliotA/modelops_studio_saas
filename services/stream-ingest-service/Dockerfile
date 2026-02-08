FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/stream-ingest-service /app/services/stream-ingest-service
RUN pip install --no-cache-dir -r /app/services/stream-ingest-service/requirements.txt
WORKDIR /app/services/stream-ingest-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
