FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY apps/workloads/trainer/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY apps/workloads/trainer/trainer /app/trainer
ENV PYTHONPATH=/app

CMD ["python","-m","trainer.train"]
