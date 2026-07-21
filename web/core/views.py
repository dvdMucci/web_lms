from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """Chequeo de salud para el healthcheck de Docker.

    Verifica que el proceso responde Y que la base contesta: un worker vivo que no
    puede hablar con MariaDB no sirve de nada, y sin esto Docker lo daria por sano.
    Exento del modo mantenimiento (ver core.middleware.MaintenanceModeMiddleware).
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception as exc:
        return JsonResponse({'status': 'error', 'database': str(exc)}, status=503)

    return JsonResponse({'status': 'ok'})
