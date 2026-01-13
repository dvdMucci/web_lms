from django import forms
from django.contrib.auth import get_user_model
from .models import Course

User = get_user_model()

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
        if self.instance and self.instance.pk and self.instance.instructor:
            self.fields['collaborators'].queryset = User.objects.filter(
                user_type='teacher'
            ).exclude(id=self.instance.instructor.id)
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
