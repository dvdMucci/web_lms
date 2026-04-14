from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Max
from django.utils import timezone

from .models import ThemeExam, ExamQuestion, ExamAnswerOption


class ThemeExamForm(forms.ModelForm):
    class Meta:
        model = ThemeExam
        fields = [
            'title',
            'description',
            'is_published',
            'available_from',
            'available_until',
            'attendance_date',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'available_from': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'available_until': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local',
            }),
            'attendance_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
        }
        labels = {
            'title': 'Título del examen',
            'description': 'Descripción (opcional)',
            'is_published': 'Publicado',
            'available_from': 'Disponible desde',
            'available_until': 'Disponible hasta',
            'attendance_date': 'Fecha de asistencia requerida',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        fmt = '%Y-%m-%dT%H:%M'
        for name in ('available_from', 'available_until'):
            self.fields[name].widget.format = fmt
            self.fields[name].input_formats = [
                '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
            ]
        if self.instance and self.instance.pk:
            for name in ('available_from', 'available_until'):
                value = getattr(self.instance, name, None)
                if value is not None:
                    if timezone.is_aware(value):
                        value = timezone.localtime(value)
                    self.initial[name] = value.strftime(fmt)

    def clean(self):
        cleaned = super().clean()
        af, au = cleaned.get('available_from'), cleaned.get('available_until')
        if af and au and au <= af:
            raise ValidationError('«Disponible hasta» debe ser posterior a «Disponible desde».')

        if cleaned.get('is_published'):
            exam = self.instance
            for f in self.Meta.fields:
                if f in cleaned:
                    setattr(exam, f, cleaned[f])
            valid, err = exam.is_valid_for_publishing()
            if not valid:
                raise ValidationError(err)
        return cleaned


class ExamQuestionWithOptionsForm(forms.Form):
    text = forms.CharField(
        label='Pregunta',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    option_a = forms.CharField(
        label='Opción A',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
    option_b = forms.CharField(
        label='Opción B',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
    option_c = forms.CharField(
        label='Opción C',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
    correct = forms.ChoiceField(
        label='Respuesta correcta',
        choices=[('a', 'A'), ('b', 'B'), ('c', 'C')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
    )
    correct_explanation = forms.CharField(
        label='Aclaración de la respuesta correcta (opcional)',
        required=False,
        widget=forms.Textarea(
            attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Ej.: por qué la opción correcta es la adecuada'}
        ),
    )

    def save_for_exam(self, exam, order=None, existing_question=None):
        """Crea o actualiza una ExamQuestion y sus tres ExamAnswerOption."""
        if order is None:
            mx = ExamQuestion.objects.filter(exam=exam).aggregate(m=Max('order'))['m']
            order = (mx if mx is not None else -1) + 1

        texts = [
            self.cleaned_data['option_a'],
            self.cleaned_data['option_b'],
            self.cleaned_data['option_c'],
        ]
        correct_idx = {'a': 0, 'b': 1, 'c': 2}[self.cleaned_data['correct']]

        expl = (self.cleaned_data.get('correct_explanation') or '').strip()

        if existing_question:
            q = existing_question
            q.text = self.cleaned_data['text']
            q.order = order
            q.correct_explanation = expl
            q.save()
            opts = list(q.answer_options.order_by('id'))
            if len(opts) != 3:
                q.answer_options.all().delete()
                opts = []
        else:
            q = ExamQuestion.objects.create(
                exam=exam,
                text=self.cleaned_data['text'],
                order=order,
                correct_explanation=expl,
            )
            opts = []

        if len(opts) == 3:
            for i, opt in enumerate(opts):
                opt.text = texts[i]
                opt.is_correct = i == correct_idx
                opt.save()
        else:
            for i, t in enumerate(texts):
                ExamAnswerOption.objects.create(
                    question=q,
                    text=t,
                    is_correct=(i == correct_idx),
                )
        return q


class ExamImportForm(forms.Form):
    file = forms.FileField(
        label='Archivo Excel (.xlsx)',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xlsm'}),
    )
    replace_existing = forms.BooleanField(
        required=False,
        initial=False,
        label='Reemplazar todas las preguntas existentes',
        help_text='Si se marca, se eliminan las preguntas actuales y se cargan solo las del archivo.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
