FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/llm-labeling-service /app/services/llm-labeling-service
RUN pip install --no-cache-dir -r /app/services/llm-labeling-service/requirements.txt
WORKDIR /app/services/llm-labeling-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
