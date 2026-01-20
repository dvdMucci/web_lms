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
