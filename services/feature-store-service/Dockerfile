FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/feature-store-service /app/services/feature-store-service
RUN pip install --no-cache-dir -r /app/services/feature-store-service/requirements.txt
WORKDIR /app/services/feature-store-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
