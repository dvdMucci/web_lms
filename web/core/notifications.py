from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .services.mailgun import MailgunClient


def _full_name_or_username(user):
    full_name = user.get_full_name()
    return full_name or user.username


def _can_receive_student_email(student):
    return (
        bool(student.email)
        and student.is_student()
        and student.is_email_verified()
    )


def notify_enrollment_created(enrollment):
    student = enrollment.student
    if not _can_receive_student_email(student):
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
    if not _can_receive_student_email(student):
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


def notify_material_published(material):
    """
    Envía notificaciones por correo a los estudiantes inscritos cuando se publica un material.
    """
    from courses.models import Enrollment
    
    # Obtener todos los estudiantes inscritos y aprobados en el curso
    enrollments = Enrollment.objects.filter(
        course=material.course,
        status='approved'
    ).select_related('student')
    
    if not enrollments.exists():
        return 0
    
    sent_count = 0
    material_url = None
    
    # Construir URL del material (necesitarás ajustar según tu estructura de URLs)
    try:
        from django.urls import reverse
        from django.contrib.sites.models import Site
        from django.conf import settings
        
        # Intentar construir la URL completa
        if material.tema:
            material_url = (
                f"{settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://marinaojeda.ar'}"
                f"/courses/{material.course.id}/units/{material.tema.unit.id}/temas/{material.tema.id}/"
            )
        else:
            material_url = f"{settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://marinaojeda.ar'}/courses/{material.course.id}/materials/"
    except Exception:
        pass
    
    subject = f"Nuevo material disponible: {material.title}"
    
    for enrollment in enrollments:
        student = enrollment.student
        if not _can_receive_student_email(student):
            continue
        
        context = {
            "recipient_name": _full_name_or_username(student),
            "material": material,
            "course": material.course,
            "material_url": material_url,
            "project_name": "Marina Ojeda LMS",
        }
        
        try:
            html = render_to_string("emails/material_published.html", context)
        except Exception:
            # Si no existe el template, crear uno simple
            html = f"""
            <html>
            <body>
                <h2>Nuevo Material Disponible</h2>
                <p>Hola {context['recipient_name']},</p>
                <p>Se ha publicado un nuevo material en el curso <strong>{material.course.title}</strong>:</p>
                <h3>{material.title}</h3>
                {f'<p>{material.description}</p>' if material.description else ''}
                {f'<p><a href="{material_url}">Ver material</a></p>' if material_url else ''}
                <p>Saludos,<br>Marina Ojeda LMS</p>
            </body>
            </html>
            """
        
        text = strip_tags(html)
        
        if MailgunClient().send_message(
            to_email=student.email,
            subject=subject,
            text=text,
            html=html,
            tags=["material", "published"],
        ):
            sent_count += 1
    
    return sent_count


def notify_forum_post(post):
    """
    Envía notificación cuando un docente crea una publicación en el foro.
    - Post general: envía a todos los alumnos inscritos.
    - Post privado (docente → alumno): envía solo al alumno participante.
    - Post privado (alumno → docentes): envía al instructor y colaboradores.
    """
    from courses.models import Enrollment
    from django.conf import settings as django_settings

    author = post.author
    course = post.course
    site_url = getattr(django_settings, 'SITE_URL', 'https://marinaojeda.ar')
    post_url = f"{site_url}/forum/{post.pk}/"

    subject = f"Nuevo mensaje en el foro: {post.title}"
    context_base = {
        'post': post,
        'course': course,
        'post_url': post_url,
        'project_name': 'Marina Ojeda LMS',
    }

    recipients = []

    if post.is_private:
        if author.is_student():
            # Student notifies teachers
            teachers = list(course.collaborators.all())
            teachers.append(course.instructor)
            for teacher in teachers:
                if teacher.email:
                    recipients.append(teacher)
        else:
            # Teacher notifies target student
            student = post.student_participant
            if student and _can_receive_student_email(student):
                recipients.append(student)
    else:
        # General post: notify all enrolled students
        enrollments = Enrollment.objects.filter(
            course=course, status='approved'
        ).select_related('student')
        for enrollment in enrollments:
            if _can_receive_student_email(enrollment.student):
                recipients.append(enrollment.student)

    sent = 0
    for recipient in recipients:
        context = {
            **context_base,
            'recipient_name': _full_name_or_username(recipient),
        }
        html = render_to_string('emails/forum_notification.html', context)
        text = strip_tags(html)
        if MailgunClient().send_message(
            to_email=recipient.email,
            subject=subject,
            text=text,
            html=html,
            tags=['forum', 'post'],
        ):
            sent += 1
    return sent


def notify_forum_reply(reply):
    """
    Envía notificación cuando alguien responde en el foro.
    Misma lógica de destinatarios que notify_forum_post pero el autor del reply
    no se notifica a sí mismo.
    """
    from courses.models import Enrollment
    from django.conf import settings as django_settings

    author = reply.author
    post = reply.post
    course = post.course
    site_url = getattr(django_settings, 'SITE_URL', 'https://marinaojeda.ar')
    post_url = f"{site_url}/forum/{post.pk}/"

    subject = f"Nueva respuesta en el foro: {post.title}"
    context_base = {
        'reply': reply,
        'post': post,
        'course': course,
        'post_url': post_url,
        'project_name': 'Marina Ojeda LMS',
        'is_reply': True,
    }

    recipients = []

    if post.is_private:
        if author.is_student():
            teachers = list(course.collaborators.all())
            teachers.append(course.instructor)
            for teacher in teachers:
                if teacher.email and teacher != author:
                    recipients.append(teacher)
        else:
            student = post.student_participant
            if student and _can_receive_student_email(student) and student != author:
                recipients.append(student)
    else:
        # General post: notify all enrolled students (only teacher replies reach here)
        enrollments = Enrollment.objects.filter(
            course=course, status='approved'
        ).select_related('student')
        for enrollment in enrollments:
            student = enrollment.student
            if _can_receive_student_email(student) and student != author:
                recipients.append(student)

    sent = 0
    for recipient in recipients:
        context = {
            **context_base,
            'recipient_name': _full_name_or_username(recipient),
        }
        html = render_to_string('emails/forum_notification.html', context)
        text = strip_tags(html)
        if MailgunClient().send_message(
            to_email=recipient.email,
            subject=subject,
            text=text,
            html=html,
            tags=['forum', 'reply'],
        ):
            sent += 1
    return sent


def notify_assignment_published(assignment):
    """
    Envía notificaciones por correo a los estudiantes inscritos cuando se publica una tarea.
    """
    from courses.models import Enrollment
    
    # Obtener todos los estudiantes inscritos y aprobados en el curso
    enrollments = Enrollment.objects.filter(
        course=assignment.course,
        status='approved'
    ).select_related('student')
    
    if not enrollments.exists():
        return 0
    
    sent_count = 0
    assignment_url = None
    
    # Construir URL de la tarea
    try:
        from django.urls import reverse
        from django.conf import settings
        
        assignment_url = (
            f"{settings.SITE_URL if hasattr(settings, 'SITE_URL') else 'https://marinaojeda.ar'}"
            f"/courses/{assignment.course.id}/units/{assignment.tema.unit.id}/temas/{assignment.tema.id}/assignments/{assignment.id}/"
        )
    except Exception:
        pass
    
    subject = f"Nueva tarea disponible: {assignment.title}"
    
    for enrollment in enrollments:
        student = enrollment.student
        if not _can_receive_student_email(student):
            continue
        
        context = {
            "recipient_name": _full_name_or_username(student),
            "assignment": assignment,
            "course": assignment.course,
            "tema": assignment.tema,
            "assignment_url": assignment_url,
            "due_date": assignment.due_date,
            "project_name": "Marina Ojeda LMS",
        }
        
        try:
            html = render_to_string("emails/assignment_published.html", context)
        except Exception:
            # Si no existe el template, crear uno simple
            html = f"""
            <html>
            <body>
                <h2>Nueva Tarea Disponible</h2>
                <p>Hola {context['recipient_name']},</p>
                <p>Se ha publicado una nueva tarea en el curso <strong>{assignment.course.title}</strong>:</p>
                <h3>{assignment.title}</h3>
                {f'<p>{assignment.description}</p>' if assignment.description else ''}
                <p><strong>Fecha límite de entrega:</strong> {assignment.due_date.strftime('%d/%m/%Y %H:%M')}</p>
                {f'<p><a href="{assignment_url}">Ver tarea</a></p>' if assignment_url else ''}
                <p>Saludos,<br>Marina Ojeda LMS</p>
            </body>
            </html>
            """
        
        text = strip_tags(html)
        
        if MailgunClient().send_message(
            to_email=student.email,
            subject=subject,
            text=text,
            html=html,
            tags=["assignment", "published"],
        ):
            sent_count += 1
    
    return sent_count
