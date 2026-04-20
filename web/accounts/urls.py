from django.urls import path
from . import views # Importa las vistas de tu aplicación

urlpatterns = [
    path('_theme/login-bg.jpg', views.login_background_image, name='login_background'),
    path('register/', views.register_view, name='register'),
    path('register/<str:token>/', views.register_with_token_view, name='register_with_token'),
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
    path('users/<int:user_id>/activity/', views.user_activity_list, name='user_activity_list'),
    path('users/create/', views.user_create, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:user_id>/delete/', views.user_delete, name='user_delete'),
    path('registration-tokens/', views.registration_token_list_create, name='registration_token_list'),
    path('registration-tokens/<int:token_id>/cancel/', views.registration_token_cancel, name='registration_token_cancel'),
    path('notifications/test/', views.test_notification, name='test_notification'),
]