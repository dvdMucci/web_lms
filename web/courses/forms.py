from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Course

User = get_user_model()


MODE_NOW = 'now'
MODE_PERIOD = 'period'
MODE_SCHEDULED = 'scheduled'


class EnrollmentOpenForm(forms.Form):
    """Formulario para abrir la inscripción: ahora, por un periodo o programado."""
    mode = forms.ChoiceField(
        choices=[
            (MODE_NOW, 'Abrir ahora (sin fecha de cierre)'),
            (MODE_PERIOD, 'Abrir desde ahora por un periodo'),
            (MODE_SCHEDULED, 'Programar apertura a futuro por un periodo'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Cómo abrir la inscripción',
    )
    enrollment_opens_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        label='Abrir el (fecha y hora)',
        help_text='Para "Programar apertura": fecha y hora en que se abrirá.',
    )
    enrollment_closes_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        label='Cerrar el (fecha y hora)',
        help_text='Para "por un periodo": fecha y hora en que se cerrará. Opcional si se programa solo la apertura.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['enrollment_opens_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
        self.fields['enrollment_closes_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']

    def clean(self):
        data = super().clean()
        mode = data.get('mode')
        opens = data.get('enrollment_opens_at')
        closes = data.get('enrollment_closes_at')

        if mode == MODE_PERIOD:
            if not closes:
                self.add_error('enrollment_closes_at', 'Indique la fecha y hora de cierre del periodo.')
            if closes and timezone.is_naive(closes):
                closes = timezone.make_aware(closes, timezone.get_current_timezone())
            if closes and timezone.now() >= closes:
                self.add_error('enrollment_closes_at', 'La fecha de cierre debe ser futura.')
        elif mode == MODE_SCHEDULED:
            if not opens:
                self.add_error('enrollment_opens_at', 'Indique la fecha y hora de apertura.')
            if opens:
                if timezone.is_naive(opens):
                    opens = timezone.make_aware(opens, timezone.get_current_timezone())
                if opens <= timezone.now():
                    self.add_error('enrollment_opens_at', 'La fecha de apertura debe ser futura.')
            if closes and opens:
                if timezone.is_naive(closes):
                    closes = timezone.make_aware(closes, timezone.get_current_timezone())
                if closes <= opens:
                    self.add_error('enrollment_closes_at', 'La fecha de cierre debe ser posterior a la de apertura.')
        return data

class CourseForm(forms.ModelForm):
    collaborators = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(user_type='teacher'),
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'form-control'}),
        help_text='Seleccione los docentes colaboradores del curso'
    )
    
    class Meta:
        model = Course
        fields = ['title', 'description', 'enrollment_limit', 'schedule', 'collaborators']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'enrollment_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'schedule': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
        labels = {
            'title': 'Título',
            'description': 'Descripción',
            'enrollment_limit': 'Límite de Inscripción',
            'schedule': 'Horario',
            'collaborators': 'Docentes Colaboradores',
        }
        help_texts = {
            'title': 'Ingrese el título del curso',
            'description': 'Describa el contenido y objetivos del curso',
            'enrollment_limit': 'Número máximo de estudiantes permitidos',
            'schedule': 'Horarios y fechas del curso',
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Filter collaborators queryset to exclude the instructor
        # Usar instructor_id para evitar acceder al objeto antes de que esté asignado
        if self.instance and self.instance.pk and self.instance.instructor_id:
            self.fields['collaborators'].queryset = User.objects.filter(
                user_type='teacher'
            ).exclude(id=self.instance.instructor_id)
        else:
            self.fields['collaborators'].queryset = User.objects.filter(
                user_type='teacher'
            )
    
    def clean_enrollment_limit(self):
        enrollment_limit = self.cleaned_data.get('enrollment_limit')
        if enrollment_limit and enrollment_limit < 1:
            raise forms.ValidationError('El límite de inscripción debe ser mayor a 0.')
        return enrollment_limit
    
    def clean_collaborators(self):
        collaborators = self.cleaned_data.get('collaborators')
        if collaborators:
            for collaborator in collaborators:
                if not collaborator.is_teacher():
                    raise forms.ValidationError(
                        'Solo se pueden agregar profesores como colaboradores.'
                    )
        return collaborators
