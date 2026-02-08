FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir nats-py==2.11.0
# Only copy the lightweight NATS helper module so the bootstrap image stays small.
# (We intentionally avoid installing the full "mlops-common" dependency graph here.)
COPY libs/common/mlops_common /app/mlops_common
COPY scripts/bootstrap_nats.py /app/bootstrap_nats.py
ENV NATS_URL=nats://nats:4222
CMD ["python","/app/bootstrap_nats.py"]
