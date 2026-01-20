from django.shortcuts import redirect
from django.urls import reverse


class StudentEmailVerificationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            if user.is_student() and not user.is_email_verified():
                if not self._is_allowed_path(request):
                    return redirect('email_verification_required')
        return self.get_response(request)

    def _is_allowed_path(self, request):
        allowed_names = [
            'login',
            'logout',
            'email_verification_required',
            'email_verification_resend',
            'email_verify',
        ]
        allowed_paths = {reverse(name) for name in allowed_names}
        if request.path in allowed_paths:
            return True
        if request.path.startswith('/admin/'):
            return True
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return True
        return False
