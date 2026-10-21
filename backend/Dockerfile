FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
COPY backend/constraints.txt /app/constraints.txt
RUN pip install -r requirements.txt && useradd --create-home --uid 10001 road
COPY backend /app/backend
COPY alembic.ini /app/alembic.ini
RUN mkdir -p /app/data/media && chown -R road:road /app/data
USER road
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

