FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY pelanggan-service/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY common /app/common
COPY pelanggan-service /app/pelanggan-service
ENV PYTHONPATH=/app
ENV DATA_DIR=/data
RUN mkdir -p /data
EXPOSE 8002
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/health').status==200 else 1)"
WORKDIR /app/pelanggan-service
CMD ["python", "app.py"]
