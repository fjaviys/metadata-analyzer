# Metadata Analyzer — backend (FastAPI + exiftool)
FROM python:3.11-slim

# exiftool (perl) + utilidades mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
        libimage-exiftool-perl \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SHARED_PYTHON_DIR=/app/shared/python

WORKDIR /app

# Dependencias primero (cache de capas)
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Código: backend + lógica compartida
COPY backend /app/backend
COPY shared /app/shared

WORKDIR /app/backend

EXPOSE 8000

# Healthcheck del propio contenedor
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
