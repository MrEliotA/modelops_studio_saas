FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/registry-service /app/services/registry-service
RUN pip install --no-cache-dir -r /app/services/registry-service/requirements.txt
WORKDIR /app/services/registry-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
