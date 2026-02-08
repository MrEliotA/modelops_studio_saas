FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/gpu-scheduler-service /app/services/gpu-scheduler-service
RUN pip install --no-cache-dir -r /app/services/gpu-scheduler-service/requirements.txt
WORKDIR /app/services/gpu-scheduler-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
