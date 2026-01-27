from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError

class Unit(models.Model):
    title = models.CharField(max_length=200, verbose_name='Título')
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='units',
        verbose_name='Curso'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_units',
        verbose_name='Creado por'
    )
    is_paused = models.BooleanField(default=False, verbose_name='En Pausa')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')
    order = models.PositiveIntegerField(default=0, verbose_name='Orden')

    class Meta:
        verbose_name = 'Unidad'
        verbose_name_plural = 'Unidades'
        ordering = ['order', 'created_at']
        unique_together = ['course', 'order']

    def __str__(self):
        return f"{self.title} - {self.course.title}"

    def clean(self):
        # Only validate if created_by is set and has a value
        if self.created_by_id is not None and self.course_id is not None:
            from django.contrib.auth import get_user_model
            from courses.models import Course
            User = get_user_model()
            try:
                user = User.objects.get(pk=self.created_by_id)
                course = Course.objects.get(pk=self.course_id)
            except (User.DoesNotExist, Course.DoesNotExist):
                return
            
            if not (user.is_teacher() or user.user_type == 'admin'):
                raise ValidationError('Solo los profesores pueden crear unidades.')
            
            # Validate that creator is instructor or collaborator
            is_instructor = course.instructor_id == self.created_by_id
            is_collaborator = self.created_by_id in course.collaborators.values_list('id', flat=True)
            is_admin = user.user_type == 'admin'
            
            if not (is_instructor or is_collaborator or is_admin):
                raise ValidationError('Solo el instructor, colaboradores o administradores pueden crear unidades en este curso.')

    def save(self, *args, **kwargs):
        # Only run clean if created_by_id is set (avoid accessing created_by directly to prevent RelatedObjectDoesNotExist)
        if self.created_by_id is not None:
            self.clean()
        super().save(*args, **kwargs)

    def is_visible_to_students(self):
        """Check if unit is visible to students (not paused)"""
        return not self.is_paused

    def can_be_managed_by(self, user):
        """Check if user can manage this unit"""
        return (
            self.course.instructor == user or
            user in self.course.collaborators.all() or
            user.user_type == 'admin'
        )


class Tema(models.Model):
    title = models.CharField(max_length=200, verbose_name='Título')
    description = models.TextField(verbose_name='Descripción')
    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name='temas',
        verbose_name='Unidad'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_temas',
        verbose_name='Creado por'
    )
    is_paused = models.BooleanField(default=True, verbose_name='En Pausa')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')
    order = models.PositiveIntegerField(default=0, verbose_name='Orden')

    class Meta:
        verbose_name = 'Tema'
        verbose_name_plural = 'Temas'
        ordering = ['order', 'created_at']
        unique_together = ['unit', 'order']

    def __str__(self):
        return f"{self.title} - {self.unit.title}"

    def clean(self):
        if self.created_by_id is not None and self.unit_id is not None:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(pk=self.created_by_id)
                unit = Unit.objects.get(pk=self.unit_id)
            except (User.DoesNotExist, Unit.DoesNotExist):
                return

            if not (user.is_teacher() or user.user_type == 'admin'):
                raise ValidationError('Solo los profesores pueden crear temas.')

            is_instructor = unit.course.instructor_id == self.created_by_id
            is_collaborator = self.created_by_id in unit.course.collaborators.values_list('id', flat=True)
            is_admin = user.user_type == 'admin'

            if not (is_instructor or is_collaborator or is_admin):
                raise ValidationError('Solo el instructor, colaboradores o administradores pueden crear temas en este curso.')

    def save(self, *args, **kwargs):
        if self.created_by_id is not None:
            self.clean()
        super().save(*args, **kwargs)

    def is_visible_to_students(self):
        """Check if theme is visible to students (unit not paused and theme not paused)."""
        return not self.is_paused and self.unit.is_visible_to_students()

    def can_be_managed_by(self, user):
        """Check if user can manage this theme."""
        return self.unit.can_be_managed_by(user)
