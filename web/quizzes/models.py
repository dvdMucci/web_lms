from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ThemeExam(models.Model):
    """Examen de opción múltiple asociado a un tema."""
    title = models.CharField(max_length=200, verbose_name='Título')
    description = models.TextField(blank=True, verbose_name='Descripción')
    tema = models.ForeignKey(
        'units.Tema',
        on_delete=models.CASCADE,
        related_name='theme_exams',
        verbose_name='Tema',
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name='theme_exams',
        verbose_name='Curso',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_theme_exams',
        verbose_name='Creado por',
    )
    is_published = models.BooleanField(
        default=False,
        verbose_name='Publicado',
        help_text='Si no está publicado, los alumnos no verán el examen.',
    )
    available_from = models.DateTimeField(verbose_name='Disponible desde')
    available_until = models.DateTimeField(verbose_name='Disponible hasta')
    attendance_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Fecha de asistencia requerida',
        help_text='Opcional. Si se indica, solo podrán rendir el examen los alumnos '
        'marcados como presentes en esa fecha (según la planilla de asistencia del curso).',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        verbose_name = 'Examen del tema'
        verbose_name_plural = 'Exámenes del tema'
        ordering = ['available_from', 'created_at']

    def __str__(self):
        return f'{self.title} — {self.tema.title}'

    def clean(self):
        if self.available_from and self.available_until:
            if self.available_until <= self.available_from:
                raise ValidationError('«Disponible hasta» debe ser posterior a «Disponible desde».')
        if self.tema_id and self.course_id:
            from units.models import Tema
            try:
                tema = Tema.objects.get(pk=self.tema_id)
            except Tema.DoesNotExist:
                return
            if tema.unit.course_id != self.course_id:
                raise ValidationError('El tema debe pertenecer al curso indicado.')

    def save(self, *args, **kwargs):
        if self.tema_id is not None and self.course_id is not None:
            self.clean()
        super().save(*args, **kwargs)

    def can_be_managed_by(self, user):
        return (
            self.course.instructor == user
            or user in self.course.collaborators.all()
            or getattr(user, 'user_type', '') == 'admin'
        )

    def is_available_now(self):
        now = timezone.now()
        return self.available_from <= now <= self.available_until

    def question_count(self):
        if self.pk is None:
            return 0
        return self.questions.count()

    def is_valid_for_publishing(self):
        """Al menos una pregunta; cada pregunta con exactamente 3 opciones y una correcta."""
        # Sin pk, el related manager de preguntas no es usable (lanza ValueError en Django).
        if self.pk is None:
            return (
                False,
                'No podés publicar un examen sin preguntas. '
                'Guardalo sin publicar, agregá preguntas y luego marcá «Publicado».',
            )
        questions = list(self.questions.prefetch_related('answer_options'))
        if not questions:
            return False, 'Debe haber al menos una pregunta.'
        for q in questions:
            opts = list(q.answer_options.all())
            if len(opts) != 3:
                return False, f'La pregunta «{q.text[:50]}…» debe tener exactamente 3 opciones.'
            correct = sum(1 for o in opts if o.is_correct)
            if correct != 1:
                return False, f'Cada pregunta debe tener exactamente una opción correcta (pregunta id {q.pk}).'
        return True, ''

    @staticmethod
    def score_from_counts(correct: int, total: int) -> Decimal:
        """
        Nota de 0,00 a 10,00 proporcional al porcentaje de aciertos:
        10 × (aciertos / total). Ej.: 50 % → 5,00; 100 % → 10,00.
        Dos decimales (ROUND_HALF_UP).
        """
        if total <= 0:
            raise ValueError('total debe ser positivo')
        raw = Decimal('10') * Decimal(correct) / Decimal(total)
        low, high = Decimal('0'), Decimal('10')
        clamped = max(low, min(high, raw))
        return clamped.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class ExamQuestion(models.Model):
    exam = models.ForeignKey(
        ThemeExam,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name='Examen',
    )
    text = models.TextField(verbose_name='Texto de la pregunta')
    order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    correct_explanation = models.TextField(
        blank=True,
        default='',
        verbose_name='Aclaración de la respuesta correcta (opcional)',
        help_text='Opcional. Se muestra al alumno al revisar el examen.',
    )

    class Meta:
        verbose_name = 'Pregunta'
        verbose_name_plural = 'Preguntas'
        ordering = ['order', 'id']

    def __str__(self):
        return self.text[:80]


class ExamAnswerOption(models.Model):
    question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name='answer_options',
        verbose_name='Pregunta',
    )
    text = models.TextField(verbose_name='Texto de la opción')
    is_correct = models.BooleanField(default=False, verbose_name='Es correcta')

    class Meta:
        verbose_name = 'Opción de respuesta'
        verbose_name_plural = 'Opciones de respuesta'

    def __str__(self):
        return self.text[:60]


class ExamAttempt(models.Model):
    exam = models.ForeignKey(
        ThemeExam,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name='Examen',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='exam_attempts',
        verbose_name='Estudiante',
    )
    started_at = models.DateTimeField(auto_now_add=True, verbose_name='Iniciado en')
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Enviado en',
    )
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Puntaje (1,00–10,00)',
    )
    correct_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Respuestas correctas',
    )
    total_questions = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Total de preguntas',
    )
    shuffle_state = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Orden aleatorio del intento',
        help_text='question_ids y option_order por pregunta.',
    )

    class Meta:
        verbose_name = 'Intento de examen'
        verbose_name_plural = 'Intentos de examen'
        unique_together = [['exam', 'student']]
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.student} — {self.exam.title}'

    def is_submitted(self):
        return self.submitted_at is not None


class ExamAttemptAnswer(models.Model):
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name='Intento',
    )
    question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name='attempt_answers',
        verbose_name='Pregunta',
    )
    selected_option = models.ForeignKey(
        ExamAnswerOption,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='attempt_selections',
        verbose_name='Opción elegida',
    )
    dont_know = models.BooleanField(
        default=False,
        verbose_name='«No lo sé»',
        help_text='Respuesta fija del sistema (no es una opción cargada por el docente).',
    )

    class Meta:
        verbose_name = 'Respuesta del intento'
        verbose_name_plural = 'Respuestas del intento'
        unique_together = [['attempt', 'question']]

    def clean(self):
        super().clean()
        if self.dont_know and self.selected_option_id is not None:
            raise ValidationError(
                'Si se marca «No lo sé», no debe elegirse una opción de la pregunta.'
            )
