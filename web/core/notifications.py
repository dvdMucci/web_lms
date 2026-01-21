from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .services.mailgun import MailgunClient


def _full_name_or_username(user):
    full_name = user.get_full_name()
    return full_name or user.username


def notify_enrollment_created(enrollment):
    student = enrollment.student
    if not student.email:
        return False

    subject = f"Inscripción recibida: {enrollment.course.title}"
    context = {
        "student": student,
        "course": enrollment.course,
        "status": enrollment.get_status_display(),
        "recipient_name": _full_name_or_username(student),
    }
    html = render_to_string("emails/enrollment_created.html", context)
    text = strip_tags(html)

    return MailgunClient().send_message(
        to_email=student.email,
        subject=subject,
        text=text,
        html=html,
        tags=["enrollment", "created"],
    )


def notify_enrollment_status_changed(enrollment, previous_status=None):
    student = enrollment.student
    if not student.email:
        return False

    status_display = enrollment.get_status_display()
    subject = f"Inscripción {status_display.lower()}: {enrollment.course.title}"
    context = {
        "student": student,
        "course": enrollment.course,
        "status": status_display,
        "previous_status": previous_status,
        "recipient_name": _full_name_or_username(student),
    }
    html = render_to_string("emails/enrollment_status_changed.html", context)
    text = strip_tags(html)

    return MailgunClient().send_message(
        to_email=student.email,
        subject=subject,
        text=text,
        html=html,
        tags=["enrollment", "status"],
    )


def notify_email_verification(user, verification_url):
    if not user.email:
        return False

    subject = "Verifica tu correo"
    context = {
        "recipient_name": _full_name_or_username(user),
        "verification_url": verification_url,
        "project_name": "Marina Ojeda LMS",
    }
    html = render_to_string("emails/email_verification.html", context)
    text = strip_tags(html)

    return MailgunClient().send_message(
        to_email=user.email,
        subject=subject,
        text=text,
        html=html,
        tags=["email-verification"],
    )


def notify_storage_alert(usage_stats, storage_config):
    """
    Envía una notificación cuando el uso del almacenamiento alcanza el umbral configurado.
    """
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Obtener el email de destino
    alert_email = storage_config.alert_email
    if not alert_email:
        # Si no hay email configurado, usar el del primer superusuario
        try:
            superuser = User.objects.filter(is_superuser=True, is_active=True).first()
            if superuser and superuser.email:
                alert_email = superuser.email
        except Exception:
            pass
    
    if not alert_email:
        return False
    
    subject = f"⚠️ Alerta de Almacenamiento: {usage_stats['used_percent']:.1f}% utilizado"
    context = {
        "usage": usage_stats,
        "config": storage_config,
        "recipient_name": "Administrador",
        "project_name": "Marina Ojeda LMS",
    }
    
    try:
        html = render_to_string("emails/storage_alert.html", context)
    except Exception:
        # Si no existe el template, crear uno simple en texto
        html = f"""
        <html>
        <body>
            <h2>Alerta de Almacenamiento</h2>
            <p>El uso del bucket de almacenamiento ha alcanzado el umbral configurado.</p>
            <ul>
                <li><strong>Uso actual:</strong> {usage_stats['used_percent']:.1f}%</li>
                <li><strong>Espacio usado:</strong> {usage_stats['used_gb']:.2f} GB de {usage_stats['total_gb']:.0f} GB</li>
                <li><strong>Espacio disponible:</strong> {usage_stats['available_gb']:.2f} GB</li>
                <li><strong>Umbral configurado:</strong> {storage_config.alert_threshold_percent}%</li>
            </ul>
            <p>Por favor, considera liberar espacio o aumentar el plan de almacenamiento.</p>
        </body>
        </html>
        """
    
    text = strip_tags(html)
    
    return MailgunClient().send_message(
        to_email=alert_email,
        subject=subject,
        text=text,
        html=html,
        tags=["storage", "alert"],
    )
