class StudentViewMiddleware:
    """
    Inyecta request.viewing_as_student=True cuando un docente/admin activa
    el modo 'Ver como alumno'. Esto permite que las vistas filtren contenido
    igual que lo harían para un alumno inscripto.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        viewing = False
        if request.user.is_authenticated:
            user = request.user
            if (getattr(user, 'user_type', None) in ('teacher', 'admin') or
                    (hasattr(user, 'is_teacher') and user.is_teacher())):
                viewing = bool(request.session.get('view_as_student', False))
        request.viewing_as_student = viewing
        response = self.get_response(request)
        return response


class MaintenanceModeMiddleware:
    """
    Si MAINTENANCE_MODE=True (env) o existe el archivo .maintenance_on,
    responde 503 con página de mantenimiento para todas las rutas excepto estáticos.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from pathlib import Path
        from django.conf import settings
        from django.http import HttpResponse
        from django.template.loader import render_to_string

        # Durante la suite de tests el mantenimiento nunca aplica, ni siquiera si el
        # archivo existe: si no, correr tests con el sitio en mantenimiento devuelve
        # 503 en todos y confunde el diagnostico.
        if getattr(settings, 'TESTING', False):
            return self.get_response(request)

        maintenance_file = Path(settings.BASE_DIR) / '.maintenance_on'
        enabled = bool(getattr(settings, 'MAINTENANCE_MODE', False) or maintenance_file.exists())
        if enabled:
            path = request.path or ''
            # /healthz queda exento: es el healthcheck de Docker. Si devolviera 503
            # durante el mantenimiento, Docker marcaria el contenedor como unhealthy
            # justo cuando el mantenimiento es intencional.
            if not (path.startswith('/static/')
                    or path.startswith('/favicon')
                    or path == '/healthz'):
                # Sin request: evita context processors que requieren request.user
                html = render_to_string('maintenance.html', {})
                return HttpResponse(html, status=503)
        return self.get_response(request)
