#!/bin/sh
# Arranque del contenedor web.
#
# Reemplaza al `runserver --noreload` que corria en produccion. runserver es el
# servidor de desarrollo: sin workers, sin timeouts y sin manejo de carga.
set -e

mkdir -p /app/logs

echo "[entrypoint] collectstatic..."
python manage.py collectstatic --no-input --clear

echo "[entrypoint] migrate..."
python manage.py migrate --no-input

echo "[entrypoint] arrancando gunicorn..."
# gthread y no el worker sync por defecto: casi todo lo que hace la app es I/O
# bloqueante (leer archivos del bucket s3fs en Ashburn, consultas a MariaDB), asi que
# los hilos rinden mucho mas que sumar procesos.
# timeout alto porque subir un archivo de 50 MB al bucket transatlantico tarda.
exec gunicorn web.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --worker-class gthread \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --capture-output
