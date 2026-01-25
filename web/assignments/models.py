from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
import os
import uuid
from datetime import datetime


def assignment_submission_upload_path(instance, filename):
    """Generate serialized filename for assignment submissions"""
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    instance.original_filename = filename
    return f'assignments/submissions/{unique_filename}'


class Assignment(models.Model):
    """Model for assignments/tasks created by teachers within units"""
    title = models.CharField(max_length=200, verbose_name='Título')
    description = models.TextField(verbose_name='Descripción')
    unit = models.ForeignKey(
        'units.Unit',
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Unidad'
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name='Curso'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_assignments',
        verbose_name='Creado por'
    )
    due_date = models.DateTimeField(verbose_name='Fecha Límite de Entrega')
    final_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha Final (No se pueden subir más archivos después de esta fecha)'
    )
    allow_group_work = models.BooleanField(
        default=False,
        verbose_name='Permitir Trabajo en Grupo'
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    is_published = models.BooleanField(
        default=False,
        verbose_name='Publicado',
        help_text='Si está desactivado, los estudiantes no podrán ver esta tarea'
    )
    scheduled_publish_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha/Hora de Publicación Programada',
        help_text='Si se establece, la tarea se publicará automáticamente en esta fecha y hora'
    )
    send_notification_email = models.BooleanField(
        default=False,
        verbose_name='Enviar Notificación por Correo',
        help_text='Si está activado, se enviará un correo a los estudiantes cuando se publique la tarea'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        verbose_name = 'Tarea'
        verbose_name_plural = 'Tareas'
        ordering = ['due_date', 'created_at']

    def __str__(self):
        return f"{self.title} - {self.unit.title}"

    def clean(self):
        if self.created_by_id is not None:
            User = get_user_model()
            try:
                user = User.objects.get(pk=self.created_by_id)
            except User.DoesNotExist:
                return

            if not (user.is_teacher() or user.user_type == 'admin'):
                raise ValidationError('Solo los profesores pueden crear tareas.')

            # Validate that creator is instructor or collaborator
            if self.course_id is not None:
                from courses.models import Course
                try:
                    course = Course.objects.get(pk=self.course_id)
                except Course.DoesNotExist:
                    return

                is_instructor = course.instructor_id == self.created_by_id
                is_collaborator = self.created_by_id in course.collaborators.values_list('id', flat=True)
                is_admin = user.user_type == 'admin'

                if not (is_instructor or is_collaborator or is_admin):
                    raise ValidationError('Solo el instructor, colaboradores o administradores pueden crear tareas en este curso.')

            # Validate dates
            if self.final_date and self.due_date:
                if self.final_date < self.due_date:
                    raise ValidationError('La fecha final no puede ser anterior a la fecha límite de entrega.')

    def save(self, *args, **kwargs):
        if self.created_by_id is not None:
            self.clean()
        super().save(*args, **kwargs)

    def can_be_managed_by(self, user):
        """Check if user can manage this assignment"""
        return (
            self.course.instructor == user or
            user in self.course.collaborators.all() or
            user.user_type == 'admin'
        )

    def is_submission_allowed(self):
        """Check if submissions are still allowed"""
        from django.utils import timezone
        if self.final_date:
            return timezone.now() <= self.final_date
        return True

    def is_late_submission(self):
        """Check if current time is past due date"""
        from django.utils import timezone
        return timezone.now() > self.due_date


class AssignmentSubmission(models.Model):
    """Model for student submissions of assignments with versioning"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('submitted', 'Entregado'),
        ('returned', 'Devuelto'),
        ('resubmitted', 'Reentregado'),
    ]

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='submissions',
        verbose_name='Tarea'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_submissions',
        verbose_name='Estudiante'
    )
    version = models.PositiveIntegerField(default=1, verbose_name='Versión')
    file = models.FileField(
        upload_to=assignment_submission_upload_path,
        verbose_name='Archivo'
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Nombre Original del Archivo'
    )
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name='Entregado en')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='submitted',
        verbose_name='Estado'
    )
    feedback = models.TextField(
        blank=True,
        null=True,
        verbose_name='Devolución del Docente'
    )
    needs_resubmission = models.BooleanField(
        default=False,
        verbose_name='Requiere Reentrega'
    )
    feedback_given_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Devolución dada en'
    )
    feedback_given_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='given_feedbacks',
        verbose_name='Devolución dada por'
    )

    class Meta:
        verbose_name = 'Entrega de Tarea'
        verbose_name_plural = 'Entregas de Tareas'
        ordering = ['-submitted_at']
        unique_together = ['assignment', 'student', 'version']

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title} (v{self.version})"

    def clean(self):
        if self.student_id is not None:
            User = get_user_model()
            try:
                user = User.objects.get(pk=self.student_id)
            except User.DoesNotExist:
                return

            if not user.is_student():
                raise ValidationError('Solo los estudiantes pueden entregar tareas.')

            # Validate that student is enrolled in the course
            if self.assignment_id is not None:
                from courses.models import Enrollment
                enrollment = Enrollment.objects.filter(
                    student_id=self.student_id,
                    course_id=self.assignment.course_id,
                    status='approved'
                ).first()
                if not enrollment:
                    raise ValidationError('El estudiante debe estar inscrito y aprobado en el curso.')

    def save(self, *args, **kwargs):
        if self.student_id is not None:
            self.clean()
        super().save(*args, **kwargs)

    def is_late(self):
        """Check if this submission was late"""
        if not self.submitted_at or not self.assignment.due_date:
            return False
        return self.submitted_at > self.assignment.due_date

    def get_next_version(self):
        """Get the next version number for this student's submission"""
        max_version = AssignmentSubmission.objects.filter(
            assignment=self.assignment,
            student=self.student
        ).aggregate(models.Max('version'))['version__max']
        return (max_version or 0) + 1


class AssignmentCollaborator(models.Model):
    """Model for group work collaborators in assignments"""
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='collaborators',
        verbose_name='Entrega'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='collaborated_submissions',
        verbose_name='Estudiante Colaborador'
    )
    added_at = models.DateTimeField(auto_now_add=True, verbose_name='Agregado en')

    class Meta:
        verbose_name = 'Colaborador de Entrega'
        verbose_name_plural = 'Colaboradores de Entregas'
        unique_together = ['submission', 'student']
        ordering = ['added_at']

    def __str__(self):
        return f"{self.student.username} - {self.submission}"

    def clean(self):
        if self.student_id is not None:
            User = get_user_model()
            try:
                user = User.objects.get(pk=self.student_id)
            except User.DoesNotExist:
                return

            if not user.is_student():
                raise ValidationError('Solo los estudiantes pueden ser colaboradores.')

            # Validate that the assignment allows group work
            if self.submission_id is not None:
                if not self.submission.assignment.allow_group_work:
                    raise ValidationError('Esta tarea no permite trabajo en grupo.')

            # Validate that collaborator is enrolled in the course
            if self.submission_id is not None:
                from courses.models import Enrollment
                enrollment = Enrollment.objects.filter(
                    student_id=self.student_id,
                    course_id=self.submission.assignment.course_id,
                    status='approved'
                ).first()
                if not enrollment:
                    raise ValidationError('El colaborador debe estar inscrito y aprobado en el curso.')

    def save(self, *args, **kwargs):
        if self.student_id is not None:
            self.clean()
        super().save(*args, **kwargs)


class AssignmentComment(models.Model):
    """Model for comments/chat on assignment submissions"""
    submission = models.ForeignKey(
        AssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='Entrega'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assignment_comments',
        verbose_name='Usuario'
    )
    comment = models.TextField(verbose_name='Comentario')
    parent_comment = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name='Comentario Padre'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        verbose_name = 'Comentario de Entrega'
        verbose_name_plural = 'Comentarios de Entregas'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username} - {self.submission} - {self.created_at}"

    def clean(self):
        """Validate that user can comment on this submission"""
        if self.user_id is not None and self.submission_id is not None:
            User = get_user_model()
            try:
                user = User.objects.get(pk=self.user_id)
                submission = AssignmentSubmission.objects.get(pk=self.submission_id)
            except (User.DoesNotExist, AssignmentSubmission.DoesNotExist):
                return

            # Check if user is student (owner or collaborator), teacher, or admin
            is_submission_owner = submission.student_id == self.user_id
            is_collaborator = submission.collaborators.filter(student_id=self.user_id).exists()
            is_teacher = submission.assignment.can_be_managed_by(user)
            is_admin = user.user_type == 'admin'

            if not (is_submission_owner or is_collaborator or is_teacher or is_admin):
                raise ValidationError('No tienes permiso para comentar en esta entrega.')

    def save(self, *args, **kwargs):
        if self.user_id is not None and self.submission_id is not None:
            self.clean()
        super().save(*args, **kwargs)


@receiver(post_save, sender=AssignmentSubmission)
def check_storage_after_submission(sender, instance, created, **kwargs):
    """Verificar umbral de almacenamiento después de subir un archivo"""
    if created and instance.file:
        try:
            from core.services.storage import check_storage_threshold
            # Invalidar caché para obtener datos frescos
            from django.core.cache import cache
            cache.delete('storage_usage_stats')
            # Verificar el umbral de almacenamiento
            check_storage_threshold()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error al verificar umbral de almacenamiento: {e}")


@receiver(post_delete, sender=AssignmentSubmission)
def delete_submission_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
