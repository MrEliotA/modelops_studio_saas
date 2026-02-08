FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY workers/gpu-runner /app/workers/gpu-runner
RUN pip install --no-cache-dir -r /app/workers/gpu-runner/requirements.txt
WORKDIR /app/workers/gpu-runner
CMD ["python","main.py"]
