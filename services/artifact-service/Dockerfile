FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/artifact-service /app/services/artifact-service
RUN pip install --no-cache-dir -r /app/services/artifact-service/requirements.txt
WORKDIR /app/services/artifact-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
