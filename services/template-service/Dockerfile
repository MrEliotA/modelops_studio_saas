FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/template-service /app/services/template-service
RUN pip install --no-cache-dir -r /app/services/template-service/requirements.txt
WORKDIR /app/services/template-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
