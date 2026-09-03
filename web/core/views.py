from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from core.models import StorageConfig
from core.services.storage import (
    get_cached_storage_usage,
    get_storage_usage,
    invalidate_storage_usage_cache,
)


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


@login_required
def storage_status(request):
    """Pagina de estado del bucket.

    Nunca calcula en el request: si el cache esta frio la plantilla arranca vacia y
    pide el dato por AJAX a storage_status_data.
    """
    if not request.user.can_manage_users():
        raise PermissionDenied

    config = StorageConfig.objects.first()
    return render(
        request,
        'core/storage_status.html',
        {
            'initial_data': {
                'usage': get_cached_storage_usage(),
                'alert_threshold_percent': config.alert_threshold_percent if config else None,
            },
        },
    )


@login_required
def storage_status_data(request):
    if not request.user.can_manage_users():
        raise PermissionDenied

    if request.GET.get('refresh') == '1':
        invalidate_storage_usage_cache()

    usage = get_storage_usage()
    config = StorageConfig.objects.first()
    return JsonResponse(
        {
            'usage': usage,
            'alert_threshold_percent': config.alert_threshold_percent if config else None,
        }
    )
