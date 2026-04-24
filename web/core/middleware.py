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
