from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

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

    class Meta:
        verbose_name = 'Curso'
        verbose_name_plural = 'Cursos'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def clean(self):
        if self.instructor and not self.instructor.is_teacher():
            raise ValidationError('El instructor debe ser un profesor.')

    def save(self, *args, **kwargs):
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
