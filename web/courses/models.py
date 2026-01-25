from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

class Course(models.Model):
    title = models.CharField(max_length=200, verbose_name='Título')
    description = models.TextField(verbose_name='Descripción')
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courses_taught',
        verbose_name='Instructor'
    )
    collaborators = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='courses_collaborated',
        blank=True,
        verbose_name='Docentes Colaboradores'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')
    enrollment_limit = models.PositiveIntegerField(
        default=50,
        verbose_name='Límite de Inscripción'
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')
    is_paused = models.BooleanField(default=False, verbose_name='En Pausa')
    schedule = models.TextField(blank=True, null=True, verbose_name='Horario')
    # Inscripción: el docente abre/cierra. Si está abierta, se puede inscribir.
    enrollment_open = models.BooleanField(
        default=False,
        verbose_name='Inscripción abierta',
        help_text='Si está activo, el curso acepta nuevas inscripciones (sujeto a fechas si se definen).'
    )
    enrollment_opens_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Inscripción abre el',
        help_text='Opcional. Si se define, la inscripción solo estará abierta a partir de esta fecha y hora.'
    )
    enrollment_closes_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Inscripción cierra el',
        help_text='Opcional. Si se define, la inscripción se cierra en esta fecha y hora.'
    )

    class Meta:
        verbose_name = 'Curso'
        verbose_name_plural = 'Cursos'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        # Usar instructor_id para validar antes de guardar
        # Solo validar si instructor_id está asignado y el objeto está siendo guardado
        if self.instructor_id is not None:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                instructor = User.objects.get(pk=self.instructor_id)
                if not instructor.is_teacher():
                    raise ValidationError('El instructor debe ser un profesor.')
            except User.DoesNotExist:
                pass  # El instructor no existe aún, se asignará después

    def save(self, *args, **kwargs):
        # Validar solo si instructor_id está asignado
        # No llamar a clean() aquí para evitar problemas durante form.is_valid()
        if self.instructor_id is not None:
            self.clean()
        super().save(*args, **kwargs)

    @property
    def current_enrollments(self):
        return self.enrollments.filter(status='approved').count()

    @property
    def available_spots(self):
        return max(0, self.enrollment_limit - self.current_enrollments)
    
    def is_instructor_or_collaborator(self, user):
        """Check if user is the instructor or a collaborator of the course"""
        return self.instructor == user or user in self.collaborators.all()
    
    def is_visible_to_students(self):
        """Check if course is visible to students (active and not paused)"""
        return self.is_active and not self.is_paused

    def is_open_for_enrollment(self):
        """
        Inscripción efectivamente abierta: enrollment_open=True y, si existen,
        now >= enrollment_opens_at y now <= enrollment_closes_at.
        """
        if not self.enrollment_open:
            return False
        now = timezone.now()
        if self.enrollment_opens_at is not None and now < self.enrollment_opens_at:
            return False
        if self.enrollment_closes_at is not None and now > self.enrollment_closes_at:
            return False
        return True


class Enrollment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
    ]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='Estudiante'
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
        verbose_name='Curso'
    )
    enrolled_at = models.DateTimeField(auto_now_add=True, verbose_name='Inscrito en')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Estado'
    )

    class Meta:
        verbose_name = 'Inscripción'
        verbose_name_plural = 'Inscripciones'
        ordering = ['-enrolled_at']
        unique_together = ['student', 'course']

    def __str__(self):
        return f"{self.student.username} - {self.course.title} ({self.get_status_display()})"

    def clean(self):
        if self.student and not self.student.is_student():
            raise ValidationError('Solo los estudiantes pueden inscribirse en cursos.')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
