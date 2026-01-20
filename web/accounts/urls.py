from django.urls import path
from . import views # Importa las vistas de tu aplicación

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('verify-email/', views.email_verify, name='email_verify'),
    path('verify-email/required/', views.email_verification_required, name='email_verification_required'),
    path('verify-email/resend/', views.email_verification_resend, name='email_verification_resend'),
    path('profile/', views.profile_view, name='profile'),
    path('change-password/', views.change_password, name='change_password'),
    path('setup-2fa/', views.setup_2fa, name='setup_2fa'),
    path('disable-2fa/', views.disable_2fa, name='disable_2fa'),
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('notifications/test/', views.test_notification, name='test_notification'),
]