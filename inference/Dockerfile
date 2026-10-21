FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 YOLO_CONFIG_DIR=/tmp/yolo
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
COPY backend/constraints.txt /app/constraints.txt
ARG INSTALL_YOLO=false
RUN pip install -r requirements.txt && if [ "$INSTALL_YOLO" = "true" ]; then \
    apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && \
    rm -rf /var/lib/apt/lists/* && pip install -c constraints.txt ultralytics==8.3.114; fi
RUN useradd --create-home --uid 10001 road
COPY backend /app/backend
COPY inference /app/inference
USER road
EXPOSE 8001
CMD ["uvicorn", "inference.service:app", "--host", "0.0.0.0", "--port", "8001", "--no-proxy-headers"]

