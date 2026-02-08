FROM python:3.11-slim
WORKDIR /app
COPY libs/common /app/libs/common
COPY services/control-plane-api /app/services/control-plane-api
RUN pip install --no-cache-dir -r /app/services/control-plane-api/requirements.txt
WORKDIR /app/services/control-plane-api
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
