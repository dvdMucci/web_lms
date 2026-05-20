from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta


def create_notification(user, notification_type, title, message, url=''):
    """Create a notification, avoiding duplicates within 10 minutes."""
    from notifications.models import Notification
    ten_min_ago = timezone.now() - timedelta(minutes=10)
    exists = Notification.objects.filter(
        user=user,
        notification_type=notification_type,
        url=url,
        is_read=False,
        created_at__gte=ten_min_ago,
    ).exists()
    if not exists:
        Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            url=url,
        )


# ─── AssignmentComment ────────────────────────────────────────────────────────
@receiver(post_save, sender='assignments.AssignmentComment')
def on_comment_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        submission = instance.submission
        assignment = submission.assignment
        tema = assignment.tema
        unit = tema.unit
        course = unit.course
        commenter = instance.user

        url = reverse('assignments:submission_detail', kwargs={
            'course_id': course.id,
            'unit_id': unit.id,
            'tema_id': tema.id,
            'assignment_id': assignment.id,
            'submission_id': submission.id,
        })

        if commenter.is_teacher() or commenter.user_type == 'admin':
            # Teacher commented → notify student
            student = submission.student
            if student != commenter:
                create_notification(
                    user=student,
                    notification_type='comment',
                    title=f'Comentario en "{assignment.title}"',
                    message=f'{commenter.get_full_name() or commenter.username} comentó en tu entrega.',
                    url=url,
                )
        else:
            # Student commented → notify course teachers
            teachers = set()
            if course.instructor:
                teachers.add(course.instructor)
            for collab in course.collaborators.all():
                teachers.add(collab)
            for teacher in teachers:
                if teacher != commenter:
                    create_notification(
                        user=teacher,
                        notification_type='comment',
                        title=f'Comentario en "{assignment.title}"',
                        message=f'{commenter.get_full_name() or commenter.username} comentó en una entrega.',
                        url=url,
                    )
    except Exception:
        pass


# ─── AssignmentSubmission: new submission → notify teacher ───────────────────
@receiver(post_save, sender='assignments.AssignmentSubmission')
def on_submission_created(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        assignment = instance.assignment
        tema = assignment.tema
        unit = tema.unit
        course = unit.course
        student = instance.student

        url = reverse('assignments:submission_detail', kwargs={
            'course_id': course.id,
            'unit_id': unit.id,
            'tema_id': tema.id,
            'assignment_id': assignment.id,
            'submission_id': instance.id,
        })

        teachers = set()
        if course.instructor:
            teachers.add(course.instructor)
        for collab in course.collaborators.all():
            teachers.add(collab)
        for teacher in teachers:
            create_notification(
                user=teacher,
                notification_type='submission',
                title=f'Nueva entrega en "{assignment.title}"',
                message=f'{student.get_full_name() or student.username} subió una entrega.',
                url=url,
            )
    except Exception:
        pass


# ─── AssignmentSubmission: feedback added → notify student ───────────────────
@receiver(pre_save, sender='assignments.AssignmentSubmission')
def on_submission_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            from assignments.models import AssignmentSubmission
            old = AssignmentSubmission.objects.get(pk=instance.pk)
            instance._old_feedback = old.feedback
        except Exception:
            instance._old_feedback = None
    else:
        instance._old_feedback = None


@receiver(post_save, sender='assignments.AssignmentSubmission')
def on_submission_feedback(sender, instance, created, **kwargs):
    if created:
        return
    try:
        old_feedback = getattr(instance, '_old_feedback', None)
        if instance.feedback and not old_feedback:
            assignment = instance.assignment
            tema = assignment.tema
            unit = tema.unit
            course = unit.course
            url = reverse('assignments:submission_detail', kwargs={
                'course_id': course.id,
                'unit_id': unit.id,
                'tema_id': tema.id,
                'assignment_id': assignment.id,
                'submission_id': instance.id,
            })
            create_notification(
                user=instance.student,
                notification_type='grade',
                title=f'Devolución en "{assignment.title}"',
                message='El docente dejó una devolución en tu entrega.',
                url=url,
            )
    except Exception:
        pass


# ─── Material: published → notify enrolled students ──────────────────────────
@receiver(pre_save, sender='materials.Material')
def on_material_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            from materials.models import Material
            old = Material.objects.get(pk=instance.pk)
            instance._was_published = old.is_published
        except Exception:
            instance._was_published = False
    else:
        instance._was_published = False


@receiver(post_save, sender='materials.Material')
def on_material_published(sender, instance, created, **kwargs):
    try:
        # Don't notify for guide materials (attached to assignments)
        if instance.assignment_id:
            return
        was_published = getattr(instance, '_was_published', False)
        if instance.is_published and (created or not was_published):
            from courses.models import Enrollment
            tema = instance.tema
            unit = tema.unit
            course = instance.course

            url = reverse('units:tema_detail', kwargs={
                'course_id': course.id,
                'unit_id': unit.id,
                'tema_id': tema.id,
            })

            enrolled_students = Enrollment.objects.filter(
                course=course, status='approved'
            ).select_related('student')

            for enrollment in enrolled_students:
                create_notification(
                    user=enrollment.student,
                    notification_type='material',
                    title=f'Nuevo material: "{instance.title}"',
                    message=f'Se publicó nuevo material en {course.title} — {tema.title}.',
                    url=url,
                )
    except Exception:
        pass


# ─── Assignment: published → notify enrolled students ────────────────────────
@receiver(pre_save, sender='assignments.Assignment')
def on_assignment_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            from assignments.models import Assignment
            old = Assignment.objects.get(pk=instance.pk)
            instance._was_published = old.is_published
        except Exception:
            instance._was_published = False
    else:
        instance._was_published = False


@receiver(post_save, sender='assignments.Assignment')
def on_assignment_published(sender, instance, created, **kwargs):
    try:
        was_published = getattr(instance, '_was_published', False)
        if instance.is_published and (created or not was_published):
            from courses.models import Enrollment
            tema = instance.tema
            unit = tema.unit
            course = unit.course

            url = reverse('assignments:assignment_detail', kwargs={
                'course_id': course.id,
                'unit_id': unit.id,
                'tema_id': tema.id,
                'assignment_id': instance.id,
            })

            enrolled_students = Enrollment.objects.filter(
                course=course, status='approved'
            ).select_related('student')

            for enrollment in enrolled_students:
                create_notification(
                    user=enrollment.student,
                    notification_type='assignment',
                    title=f'Nueva tarea: "{instance.title}"',
                    message=f'Se publicó una nueva tarea en {course.title}.',
                    url=url,
                )
    except Exception:
        pass


# ─── ThemeExam: published → notify enrolled students ─────────────────────────
@receiver(pre_save, sender='quizzes.ThemeExam')
def on_exam_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            from quizzes.models import ThemeExam
            old = ThemeExam.objects.get(pk=instance.pk)
            instance._was_published = old.is_published
        except Exception:
            instance._was_published = False
    else:
        instance._was_published = False


@receiver(post_save, sender='quizzes.ThemeExam')
def on_exam_published(sender, instance, created, **kwargs):
    try:
        was_published = getattr(instance, '_was_published', False)
        if instance.is_published and (created or not was_published):
            from courses.models import Enrollment
            tema = instance.tema
            unit = tema.unit
            course = unit.course

            url = reverse('units:tema_detail', kwargs={
                'course_id': course.id,
                'unit_id': unit.id,
                'tema_id': tema.id,
            })

            enrolled_students = Enrollment.objects.filter(
                course=course, status='approved'
            ).select_related('student')

            for enrollment in enrolled_students:
                create_notification(
                    user=enrollment.student,
                    notification_type='exam',
                    title=f'Examen disponible: "{instance.title}"',
                    message=f'Se publicó un nuevo examen en {course.title} — {tema.title}.',
                    url=url,
                )
    except Exception:
        pass


# ─── Enrollment: status changed → notify student ─────────────────────────────
@receiver(pre_save, sender='courses.Enrollment')
def on_enrollment_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            from courses.models import Enrollment
            old = Enrollment.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except Exception:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender='courses.Enrollment')
def on_enrollment_status_changed(sender, instance, created, **kwargs):
    try:
        old_status = getattr(instance, '_old_status', None)
        course = instance.course
        student = instance.student

        if created and instance.status == 'pending':
            # New enrollment request → notify instructor
            url = reverse('course_detail', kwargs={'course_id': course.id})
            create_notification(
                user=course.instructor,
                notification_type='enrollment',
                title=f'Nueva solicitud en "{course.title}"',
                message=f'{student.get_full_name() or student.username} solicitó inscribirse.',
                url=url,
            )
        elif not created and old_status != instance.status:
            url = reverse('course_detail', kwargs={'course_id': course.id})
            if instance.status == 'approved':
                create_notification(
                    user=student,
                    notification_type='enrollment',
                    title=f'Inscripción aprobada en "{course.title}"',
                    message=f'Tu inscripción en {course.title} fue aprobada.',
                    url=url,
                )
            elif instance.status == 'rejected':
                create_notification(
                    user=student,
                    notification_type='enrollment',
                    title=f'Inscripción rechazada en "{course.title}"',
                    message=f'Tu inscripción en {course.title} fue rechazada.',
                    url=url,
                )
    except Exception:
        pass
