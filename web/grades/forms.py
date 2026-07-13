from django import forms

from .models import AcademicSituation


class AcademicSituationForm(forms.ModelForm):
    class Meta:
        model = AcademicSituation
        fields = [
            'semester_1_valuation',
            'semester_2_valuation',
            'semester_1_grade',
            'semester_2_grade',
            'average_grade',
        ]
        widgets = {
            'semester_1_valuation': forms.Select(attrs={'class': 'form-select'}),
            'semester_2_valuation': forms.Select(attrs={'class': 'form-select'}),
            'semester_1_grade': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '10',
                'step': '0.01',
            }),
            'semester_2_grade': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '10',
                'step': '0.01',
            }),
            'average_grade': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '10',
                'step': '0.01',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        empty_choice = [('', '— Sin cargar —')]
        self.fields['semester_1_valuation'].required = False
        self.fields['semester_2_valuation'].required = False
        self.fields['semester_1_valuation'].choices = empty_choice + list(
            AcademicSituation.VALUATION_CHOICES
        )
        self.fields['semester_2_valuation'].choices = empty_choice + list(
            AcademicSituation.VALUATION_CHOICES
        )
        self.fields['semester_1_grade'].required = False
        self.fields['semester_2_grade'].required = False
        self.fields['average_grade'].required = False
        self.fields['semester_1_valuation'].label = 'Valoración 1er cuatrimestre'
        self.fields['semester_2_valuation'].label = 'Valoración 2º cuatrimestre'
        self.fields['semester_1_grade'].label = 'Nota 1er cuatrimestre'
        self.fields['semester_2_grade'].label = 'Nota 2º cuatrimestre'
        self.fields['average_grade'].label = 'Promedio'
        self.fields['average_grade'].help_text = (
            'Lo define el docente según notas, evaluaciones, valoraciones y aportes en clase.'
        )
