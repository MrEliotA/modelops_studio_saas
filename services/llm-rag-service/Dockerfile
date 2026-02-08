FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/llm-rag-service /app/services/llm-rag-service
RUN pip install --no-cache-dir -r /app/services/llm-rag-service/requirements.txt
WORKDIR /app/services/llm-rag-service
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
