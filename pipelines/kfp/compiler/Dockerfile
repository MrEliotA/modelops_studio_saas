# Pipeline compiler image: produces IR YAML from pipeline sources.
FROM python:3.11-slim
WORKDIR /work
RUN pip install --no-cache-dir kfp==2.12.1
ENTRYPOINT ["python", "-c"]
