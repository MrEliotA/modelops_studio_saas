FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY config /app/config
COPY services/training-service /app/services/training-service
RUN pip install --no-cache-dir -r /app/services/training-service/requirements.txt
WORKDIR /app/services/training-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
