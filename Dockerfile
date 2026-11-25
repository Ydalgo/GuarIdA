# Dockerfile - GuarIdA Service (Web + API Local + Túnel opcional)
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1 \
    GUARIDA_HOME=/app/datos

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    ripgrep \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 10001 guarida && \
    useradd -u 10001 -g guarida -m -s /bin/bash guarida

WORKDIR /app

COPY pyproject.toml README.md LICENSE main.py /app/
COPY guarida_manager/ /app/guarida_manager/

RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -e ".[web]" && \
    mkdir -p /app/datos/bin /app/datos/models /app/datos/logs /app/datos/cache_proyectos && \
    chown -R guarida:guarida /app

USER guarida

VOLUME ["/app/datos"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/api/status || exit 1

ENTRYPOINT ["python", "main.py", "--web", "--host", "0.0.0.0", "--port", "8080", "--no-browser"]
