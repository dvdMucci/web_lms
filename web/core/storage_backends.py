"""Backends de almacenamiento propios."""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class ResilientManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """Manifest storage que no explota si falta una entrada.

    Se usa Manifest (y no el CompressedStaticFilesStorage que habia antes) para tener
    nombres con hash: sin eso el cache-busting no funciona y el navegador se queda con
    el CSS viejo despues de un deploy.

    manifest_strict=False porque web/urls.py resuelve {% static 'img/favicon.ico' %}
    al importar el URLconf. Con el modo estricto, cualquier arranque previo a un
    collectstatic exitoso tiraba ValueError y el contenedor no levantaba: un problema
    de huevo y gallina que convertia un detalle de estaticos en una caida total.
    Sin estricto, devuelve la ruta sin hash y sigue andando.
    """

    manifest_strict = False
