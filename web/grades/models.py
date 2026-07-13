from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class AcademicSituation(models.Model):
    """Formal academic record for a student in a course for one academic year."""

    VALUATION_TEP = 'TEP'
    VALUATION_TEA = 'TEA'
    VALUATION_CHOICES = [
        (VALUATION_TEP, 'TEP'),
        (VALUATION_TEA, 'TEA'),
    ]

    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='academic_situations',
        verbose_name='Curso',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='academic_situations',
        verbose_name='Estudiante',
    )
    year = models.PositiveIntegerField(verbose_name='Año lectivo')

    semester_1_valuation = models.CharField(
        max_length=3,
        choices=VALUATION_CHOICES,
        null=True,
        blank=True,
        verbose_name='Valoración 1er cuatrimestre',
    )
    semester_2_valuation = models.CharField(
        max_length=3,
        choices=VALUATION_CHOICES,
        null=True,
        blank=True,
        verbose_name='Valoración 2º cuatrimestre',
    )

    semester_1_grade = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('10'))],
        verbose_name='Nota 1er cuatrimestre',
    )
    semester_2_grade = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('10'))],
        verbose_name='Nota 2º cuatrimestre',
    )
    average_grade = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('10'))],
        verbose_name='Promedio',
        help_text='Definido por el docente según notas, evaluaciones, valoraciones y aportes en clase.',
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='academic_situations_updated',
        verbose_name='Actualizado por',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        verbose_name = 'Situación Académica'
        verbose_name_plural = 'Situaciones Académicas'
        ordering = ['-year', 'student__last_name', 'student__first_name']
        unique_together = ['course', 'student', 'year']

    def __str__(self):
        name = self.student.get_full_name() or self.student.username
        return f'{name} - {self.course.title} ({self.year})'

    def missing_valuations_count(self):
        return sum(
            1 for value in (self.semester_1_valuation, self.semester_2_valuation)
            if not value
        )

    def missing_grades_count(self):
        return sum(
            1 for value in (
                self.semester_1_grade,
                self.semester_2_grade,
                self.average_grade,
            )
            if value is None
        )

    def is_complete(self):
        return self.missing_valuations_count() == 0 and self.missing_grades_count() == 0
