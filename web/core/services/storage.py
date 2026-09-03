import os
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

User = get_user_model()

CACHE_KEY = 'storage_usage_stats'
CACHE_TTL_SECONDS = 300

# Un solo hilo: el escaneo del bucket es caro y no tiene sentido correr dos a la vez.
_STORAGE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='storage')


def get_directory_size(path):
    """
    Calcula el tamaño total de un directorio en bytes.

    OJO: MEDIA_ROOT es un bucket de Oracle montado con s3fs (y ademas en otra region,
    us-ashburn-1). Cada os.path.getsize() de aca es una llamada HTTP a traves de FUSE,
    asi que recorrer el arbol entero cuesta miles de round-trips transatlanticos.
    Nunca llamar a esto desde el hilo que atiende un request: usar get_storage_usage()
    (que cachea) o check_storage_threshold_async().
    """
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
                except (OSError, IOError) as e:
                    logger.warning(f"No se pudo obtener el tamaño del archivo {filepath}: {e}")
    except (OSError, IOError) as e:
        logger.error(f"Error al calcular el tamaño del directorio {path}: {e}")
    return total_size


def get_storage_usage():
    """
    Calcula el uso actual del almacenamiento en el bucket.
    Retorna un diccionario con información detallada.
    
    Cachéa el resultado por 5 minutos para evitar cálculos repetidos costosos.
    """
    cache_key = CACHE_KEY
    cached_result = cache.get(cache_key)

    if cached_result is not None:
        return cached_result

    try:
        media_root = settings.MEDIA_ROOT
        
        if not os.path.exists(media_root):
            return {
                'total_bytes': 0,
                'total_gb': 0.0,
                'total_mb': 0.0,
                'available_bytes': 0,
                'available_gb': 0.0,
                'used_percent': 0.0,
                'error': 'El directorio media no existe'
            }
        
        # Calcular el tamaño usado
        used_bytes = get_directory_size(media_root)
        used_gb = used_bytes / (1024 ** 3)
        used_mb = used_bytes / (1024 ** 2)
        
        # Obtener el espacio total del bucket desde la configuración
        from core.models import StorageConfig
        
        try:
            config = StorageConfig.objects.first()
            if config:
                total_gb = config.total_storage_gb
                total_bytes = total_gb * (1024 ** 3)
                available_bytes = max(0, total_bytes - used_bytes)
                available_gb = available_bytes / (1024 ** 3)
                used_percent = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0
            else:
                # Si no hay configuración, usar un valor por defecto
                total_gb = 20
                total_bytes = total_gb * (1024 ** 3)
                available_bytes = max(0, total_bytes - used_bytes)
                available_gb = available_bytes / (1024 ** 3)
                used_percent = 0
        except Exception as e:
            logger.error(f"Error al obtener configuración de almacenamiento: {e}")
            total_gb = 20
            total_bytes = total_gb * (1024 ** 3)
            available_bytes = max(0, total_bytes - used_bytes)
            available_gb = available_bytes / (1024 ** 3)
            used_percent = 0
        
        result = {
            'total_bytes': total_bytes,
            'total_gb': total_gb,
            'total_mb': total_gb * 1024,
            'used_bytes': used_bytes,
            'used_gb': round(used_gb, 2),
            'used_mb': round(used_mb, 2),
            'available_bytes': available_bytes,
            'available_gb': round(available_gb, 2),
            'available_mb': round(available_gb * 1024, 2),
            'used_percent': round(used_percent, 2),
            'error': None
        }
        
        # Cachear el resultado por 5 minutos
        cache.set(cache_key, result, CACHE_TTL_SECONDS)

        return result
    
    except Exception as e:
        logger.error(f"Error al calcular uso de almacenamiento: {e}")
        return {
            'total_bytes': 0,
            'total_gb': 0.0,
            'total_mb': 0.0,
            'available_bytes': 0,
            'available_gb': 0.0,
            'used_percent': 0.0,
            'error': str(e)
        }


def get_cached_storage_usage():
    """Devuelve el uso cacheado o None si todavia no se calculo.

    Sirve para que una vista pueda pintar la pagina sin arriesgarse a disparar el
    os.walk del bucket dentro del request.
    """
    return cache.get(CACHE_KEY)


def invalidate_storage_usage_cache():
    cache.delete(CACHE_KEY)


def bump_cached_usage(delta_bytes):
    """Ajusta el total cacheado sin volver a escanear el bucket.

    Cuando se sube un archivo ya sabemos cuanto ocupa, asi que sumarlo al valor
    cacheado da un numero suficientemente exacto por una fraccion del costo. Antes el
    codigo hacia cache.delete() en cada subida, lo que forzaba un os.walk completo del
    bucket en el siguiente acceso, justo en el peor momento.
    """
    if not delta_bytes:
        return
    cached = cache.get(CACHE_KEY)
    if cached is None:
        return

    used_bytes = max(0, cached.get('used_bytes', 0) + delta_bytes)
    total_bytes = cached.get('total_bytes', 0)
    available_bytes = max(0, total_bytes - used_bytes)

    cached.update({
        'used_bytes': used_bytes,
        'used_gb': round(used_bytes / (1024 ** 3), 2),
        'used_mb': round(used_bytes / (1024 ** 2), 2),
        'available_bytes': available_bytes,
        'available_gb': round(available_bytes / (1024 ** 3), 2),
        'available_mb': round(available_bytes / (1024 ** 2), 2),
        'used_percent': round((used_bytes / total_bytes * 100) if total_bytes else 0, 2),
    })
    cache.set(CACHE_KEY, cached, CACHE_TTL_SECONDS)


def check_storage_threshold_async(added_bytes=0):
    """Version para llamar desde signals: no bloquea el request.

    El chequeo de umbral implicaba potencialmente un escaneo completo del bucket
    dentro del post_save, o sea dentro de la transaccion del request. Ahora suma el
    tamano del archivo al cache (instantaneo) y evalua el umbral en un hilo aparte.
    """
    bump_cached_usage(added_bytes)

    def _run():
        try:
            check_storage_threshold()
        except Exception:
            logger.exception("Error al verificar umbral de almacenamiento en background")

    _STORAGE_POOL.submit(_run)


def check_storage_threshold():
    """
    Verifica si el uso del almacenamiento ha alcanzado el umbral de alerta.
    Si es así, envía una notificación por email.

    Retorna True si se envió una alerta, False en caso contrario.
    """
    try:
        from core.models import StorageConfig
        from core.notifications import notify_storage_alert
        from django.utils import timezone
        from datetime import timedelta
        
        config = StorageConfig.objects.first()
        if not config or not config.alert_enabled:
            return False
        
        # Obtener el uso actual
        usage = get_storage_usage()
        
        if usage.get('error'):
            logger.warning(f"No se pudo verificar el umbral: {usage['error']}")
            return False
        
        # Verificar si se alcanzó el umbral
        if usage['used_percent'] >= config.alert_threshold_percent:
            # Verificar si ya se envió una alerta recientemente (evitar spam)
            # Solo enviar si han pasado al menos 24 horas desde la última alerta
            should_send = True
            if config.last_alert_sent:
                time_since_last_alert = timezone.now() - config.last_alert_sent
                if time_since_last_alert < timedelta(hours=24):
                    should_send = False
                    logger.info(f"Alerta de almacenamiento omitida: se envió hace {time_since_last_alert}")
            
            if should_send:
                # Obtener el email de destino
                alert_email = config.alert_email
                if not alert_email:
                    # Si no hay email configurado, usar el del primer superusuario
                    try:
                        superuser = User.objects.filter(is_superuser=True, is_active=True).first()
                        if superuser and superuser.email:
                            alert_email = superuser.email
                    except Exception as e:
                        logger.error(f"Error al obtener email del superusuario: {e}")
                
                if alert_email:
                    success = notify_storage_alert(usage, config)
                    if success:
                        # Actualizar la fecha de la última alerta
                        config.last_alert_sent = timezone.now()
                        config.save(update_fields=['last_alert_sent'])
                        # Invalidar el caché de uso
                        cache.delete('storage_usage_stats')
                        return True
                    else:
                        logger.warning("No se pudo enviar la alerta de almacenamiento")
        
        return False
    
    except Exception as e:
        logger.error(f"Error al verificar umbral de almacenamiento: {e}")
        return False
