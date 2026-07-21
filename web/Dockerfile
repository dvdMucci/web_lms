# ---------------------------------------------------------------------------
# Etapa 1: build. Compila las dependencias (mysqlclient necesita toolchain de C)
# dentro de un venv que despues se copia entero. Asi el compilador y los headers
# no quedan en la imagen final.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        pkg-config \
        default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ---------------------------------------------------------------------------
# Etapa 2: runtime. Solo Python + la libreria cliente de MariaDB + el venv.
#
# La imagen anterior pesaba 10 GB porque instalaba torch (918 MB) y sus wheels de
# nvidia (2.9 GB) para faster-whisper, que nunca se activo, mas ffmpeg, libsndfile1,
# git, htop, build-essential y cron.
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libmariadb3 es lo unico que mysqlclient necesita en runtime (el -dev era solo
# para compilar). curl queda para el healthcheck del compose.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmariadb3 \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Usuario sin privilegios. uid/gid 1001 coincide con el usuario `ubuntu` del host,
# que es el dueno del bind mount ./web:/app y del bucket montado por s3fs (remontado
# con uid=1001). Antes el contenedor corria como root con el bucket montado rw: una
# ejecucion remota de codigo daba control total del almacenamiento.
RUN groupadd --gid 1001 app && \
    useradd --uid 1001 --gid 1001 --create-home --shell /bin/bash app

WORKDIR /app

# El codigo real llega por el bind mount ./web:/app del compose; este COPY existe
# para que la imagen sea autocontenida y se pueda correr sin el mount.
COPY --chown=app:app . .

COPY --chown=app:app entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER app

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
