from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.urls import reverse
from django.conf import settings
from urllib.parse import urlencode
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.util import random_hex # No usado directamente en el código provisto, pero útil para OTP
import qrcode
import io
import base64
import pyotp # Necesario para la generación de la URL de configuración, aunque TOTPDevice lo maneja
from .models import CustomUser
from core.services.mailgun import MailgunClient
from core.notifications import notify_email_verification
from .forms import CustomUserCreationForm, ProfileForm, LoginForm, ChangePasswordForm, StudentRegistrationForm


EMAIL_VERIFICATION_SIGNER = TimestampSigner(salt='email-verification')


def _build_email_verification_url(request, user):
    token = EMAIL_VERIFICATION_SIGNER.sign(f"{user.pk}:{user.email}")
    query = urlencode({'token': token})
    return request.build_absolute_uri(f"{reverse('email_verify')}?{query}")


def _email_verification_cooldown_seconds():
    return getattr(settings, 'EMAIL_VERIFICATION_COOLDOWN_SECONDS', 300)


def _can_send_verification_email(user):
    cooldown_seconds = _email_verification_cooldown_seconds()
    if not user.email_verification_sent_at:
        return True, 0
    delta = timezone.now() - user.email_verification_sent_at
    remaining = cooldown_seconds - int(delta.total_seconds())
    return remaining <= 0, max(0, remaining)


def _send_verification_email(request, user):
    can_send, remaining = _can_send_verification_email(user)
    if not can_send:
        return False, remaining

    user.email_verification_sent_at = timezone.now()
    user.save(update_fields=['email_verification_sent_at'])

    verification_url = _build_email_verification_url(request, user)
    sent = notify_email_verification(user, verification_url)
    return sent, 0

def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request.POST, request=request)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if user.is_student() and not user.is_email_verified():
                messages.warning(
                    request,
                    'Debes verificar tu correo para habilitar tu cuenta.'
                )
                return redirect('email_verification_required')
            return redirect('dashboard')
    else:
        form = LoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def register_view(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            sent, remaining = _send_verification_email(request, user)
            if sent:
                messages.success(
                    request,
                    'Registro exitoso. Te enviamos un correo para verificar tu cuenta.'
                )
            else:
                if remaining:
                    messages.info(
                        request,
                        f'Debes esperar {remaining} segundos para reenviar el correo.'
                    )
                else:
                    messages.warning(
                        request,
                        'Registro exitoso. No pudimos enviar el correo de verificación.'
                    )
            return redirect('login')
    else:
        form = StudentRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def email_verification_required(request):
    user = request.user
    if not user.is_student() or user.is_email_verified():
        return redirect('dashboard')

    _, remaining = _can_send_verification_email(user)
    context = {
        'cooldown_seconds': _email_verification_cooldown_seconds(),
        'remaining_seconds': remaining,
    }
    return render(request, 'accounts/email_verification_required.html', context)


@login_required
@require_http_methods(["POST"])
def email_verification_resend(request):
    user = request.user
    if not user.is_student():
        return redirect('dashboard')
    if user.is_email_verified():
        messages.info(request, 'Tu correo ya está verificado.')
        return redirect('dashboard')

    sent, remaining = _send_verification_email(request, user)
    if sent:
        messages.success(request, 'Correo de verificación enviado.')
    else:
        if remaining:
            messages.info(
                request,
                f'Debes esperar {remaining} segundos para reenviar el correo.'
            )
        else:
            messages.error(request, 'No se pudo enviar el correo de verificación.')

    return redirect('email_verification_required')


@require_http_methods(["GET"])
def email_verify(request):
    token = request.GET.get('token')
    if not token:
        messages.error(request, 'El enlace de verificación es inválido.')
        return redirect('login')

    max_age = getattr(settings, 'EMAIL_VERIFICATION_MAX_AGE_SECONDS', 172800)
    try:
        value = EMAIL_VERIFICATION_SIGNER.unsign(token, max_age=max_age)
    except SignatureExpired:
        messages.error(request, 'El enlace de verificación expiró. Solicita uno nuevo.')
        return redirect('login')
    except BadSignature:
        messages.error(request, 'El enlace de verificación es inválido.')
        return redirect('login')

    try:
        user_id, email = value.split(':', 1)
    except ValueError:
        messages.error(request, 'El enlace de verificación es inválido.')
        return redirect('login')

    user = CustomUser.objects.filter(pk=user_id, email=email).first()
    if not user:
        messages.error(request, 'No se encontró la cuenta a verificar.')
        return redirect('login')
    if not user.is_student():
        messages.error(request, 'La cuenta no requiere verificacion por correo.')
        return redirect('login')

    if user.is_email_verified():
        messages.info(request, 'Tu correo ya estaba verificado.')
        return redirect('login')

    user.email_verified_at = timezone.now()
    user.save(update_fields=['email_verified_at'])
    messages.success(request, 'Correo verificado correctamente. Ya podés iniciar sesión.')
    return redirect('login')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard(request):
    context = {
        'user': request.user,
        'user_count': CustomUser.objects.count() if request.user.can_manage_users() else None,
    }
    
    # Si el usuario es administrador, incluir información de almacenamiento
    if request.user.can_manage_users():
        try:
            from core.services.storage import get_storage_usage
            from core.models import StorageConfig
            
            usage = get_storage_usage()
            config = StorageConfig.objects.first()
            
            context['storage_usage'] = usage
            context['storage_config'] = config
        except Exception:
            # Si hay algún error, simplemente no mostramos la información
            pass
    
    return render(request, 'dashboard.html', context)

@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil actualizado correctamente')
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user)
    
    # Obtener dispositivo TOTP
    totp_device = request.user.totpdevice_set.filter(confirmed=True).first()
    
    context = {
        'form': form,
        'totp_device': totp_device,
        'is_2fa_enabled': request.user.is_2fa_enabled,
        'is_admin_user': request.user.can_manage_users(),
    }
    if request.user.is_teacher() or request.user.user_type == 'admin':
        from materials.models import Material
        from assignments.models import Assignment
        context['teacher_materials'] = Material.objects.filter(
            uploaded_by=request.user
        ).select_related('course', 'unit').order_by('-uploaded_at')[:10]
        context['teacher_assignments'] = Assignment.objects.filter(
            created_by=request.user
        ).select_related('course', 'unit').order_by('-created_at')[:10]
    return render(request, 'accounts/profile.html', context)

@login_required
def setup_2fa(request):
    # Crear o obtener dispositivo TOTP
    device, created = TOTPDevice.objects.get_or_create(
        user=request.user,
        name='default',
        defaults={'confirmed': False}
    )
    
    if not device.confirmed:
        # Generar QR code
        qr_code_url = device.config_url
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_code_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_code_data = base64.b64encode(buffer.getvalue()).decode()
        
        if request.method == 'POST':
            token = request.POST.get('token')
            if device.verify_token(token):
                device.confirmed = True
                device.save()
                request.user.is_2fa_enabled = True
                request.user.save()
                messages.success(request, '2FA configurado correctamente')
                return redirect('profile')
            else:
                messages.error(request, 'Código inválido')
        
        context = {
            'qr_code_data': qr_code_data,
            'secret_key': device.key, # La clave secreta es útil para depuración o si el usuario no puede escanear el QR
        }
        return render(request, 'accounts/setup_2fa.html', context)
    else:
        messages.info(request, '2FA ya está configurado')
        return redirect('profile')

@login_required
def disable_2fa(request):
    if request.method == 'POST':
        request.user.totpdevice_set.all().delete() # Elimina todos los dispositivos 2FA del usuario
        request.user.is_2fa_enabled = False
        request.user.save()
        messages.success(request, '2FA deshabilitado correctamente')
    return redirect('profile')

# Función de ayuda para verificar si el usuario es administrador
def is_admin(user):
    return user.is_authenticated and user.can_manage_users()

@user_passes_test(is_admin) # Decorador para restringir el acceso solo a administradores
def user_list(request):
    users = CustomUser.objects.all().order_by('-date_joined')
    paginator = Paginator(users, 10) # Paginación de 10 usuarios por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'accounts/user_list.html', {'page_obj': page_obj})

@user_passes_test(is_admin)
def user_create(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Usuario {user.username} creado correctamente')
            return redirect('user_list')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'accounts/user_form.html', {'form': form, 'title': 'Crear Usuario'})

@user_passes_test(is_admin)
def user_edit(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=user)
        user_type = request.POST.get('user_type')
        is_active = request.POST.get('is_active') == 'on' # Los checkboxes envían 'on' o nada
        
        if form.is_valid():
            user = form.save(commit=False) # Guarda el formulario pero no en la BD aún
            user.user_type = user_type
            user.is_active = is_active
            user.save() # Ahora guarda en la BD
            messages.success(request, f'Usuario {user.username} actualizado correctamente')
            return redirect('user_list')
    else:
        form = ProfileForm(instance=user)
    
    context = {
        'form': form,
        'user_obj': user,
        'user_types': CustomUser.USER_TYPES, # Pasa los tipos de usuario para el select
        'title': f'Editar Usuario: {user.username}'
    }
    return render(request, 'accounts/user_edit.html', context)

@user_passes_test(is_admin)
@require_http_methods(["POST"]) # Solo permite peticiones POST para eliminar
def user_delete(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    
    if user == request.user:
        messages.error(request, 'No puedes eliminar tu propia cuenta')
    else:
        username = user.username
        user.delete()
        messages.success(request, f'Usuario {username} eliminado correctamente')
    
    return redirect('user_list')


@user_passes_test(is_admin)
@require_http_methods(["POST"])
def test_notification(request):
    to_email = (request.POST.get('to_email') or '').strip() or request.user.email
    if not to_email:
        messages.error(request, 'Debes indicar un email de destino válido.')
        return redirect('profile')

    context = {
        'recipient_name': request.user.get_full_name() or request.user.username,
        'project_name': 'Marina Ojeda LMS',
        'sender_username': request.user.username,
    }
    html = render_to_string('emails/test_notification.html', context)
    text = strip_tags(html)

    sent = MailgunClient().send_message(
        to_email=to_email,
        subject='Test de notificación - Mailgun',
        text=text,
        html=html,
        tags=['test', 'notifications'],
    )
    if sent:
        messages.success(request, f'Email de prueba enviado a {to_email}.')
    else:
        messages.error(request, 'No se pudo enviar el email de prueba.')

    return redirect('profile')

@login_required
def change_password(request):
    if request.method == 'POST':
        # El PasswordChangeForm requiere la instancia del usuario
        form = ChangePasswordForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Importante: Esto actualiza el hash de autenticación de la sesión del usuario
            # para evitar que se cierre la sesión después de cambiar la contraseña.
            update_session_auth_hash(request, user)
            messages.success(request, 'Tu contraseña ha sido actualizada correctamente.')
            return redirect('profile') # Redirige al perfil o a una página de éxito
        else:
            messages.error(request, 'Por favor, corrige los errores a continuación.')
    else:
        form = ChangePasswordForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form, 'title': 'Cambiar Contraseña'})
