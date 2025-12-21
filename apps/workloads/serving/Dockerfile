FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY apps/workloads/serving/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY apps/workloads/serving/serving /app/serving
ENV PYTHONPATH=/app

CMD ["uvicorn","serving.app:app","--host","0.0.0.0","--port","8080"]
