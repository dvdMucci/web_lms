from django import forms
from django.core.exceptions import ValidationError
from .models import Assignment, AssignmentSubmission, AssignmentCollaborator, AssignmentComment
from courses.models import Enrollment
import os


class AssignmentForm(forms.ModelForm):
    """Form for creating and editing assignments"""
    
    class Meta:
        model = Assignment
        fields = ['title', 'description', 'due_date', 'final_date', 'allow_group_work', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'due_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'final_date': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'allow_group_work': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Título de la Tarea',
            'description': 'Descripción e Instrucciones',
            'due_date': 'Fecha Límite de Entrega',
            'final_date': 'Fecha Final (Opcional - No se podrán subir más archivos después de esta fecha)',
            'allow_group_work': 'Permitir Trabajo en Grupo',
            'is_active': 'Tarea Activa',
        }
        help_texts = {
            'title': 'Ingrese el título de la tarea',
            'description': 'Describa la tarea y las instrucciones para los estudiantes',
            'due_date': 'Fecha y hora límite para entregar sin penalización',
            'final_date': 'Si se establece, después de esta fecha no se podrán subir más archivos',
            'allow_group_work': 'Si está habilitado, los estudiantes podrán agregar colaboradores',
            'is_active': 'Si está desactivada, los estudiantes no podrán verla',
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.course = kwargs.pop('course', None)
        self.unit = kwargs.pop('unit', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        due_date = cleaned_data.get('due_date')
        final_date = cleaned_data.get('final_date')
        
        if due_date and final_date:
            if final_date < due_date:
                raise forms.ValidationError({
                    'final_date': 'La fecha final no puede ser anterior a la fecha límite de entrega.'
                })
        
        return cleaned_data


class SubmissionForm(forms.ModelForm):
    """Form for students to submit assignments"""
    initial_comment = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Agregue un comentario o nota sobre su entrega (opcional)'
        }),
        label='Comentario o Nota',
        required=False,
        help_text='Puede agregar un comentario o nota sobre su entrega (opcional)'
    )
    
    class Meta:
        model = AssignmentSubmission
        fields = ['file']
        widgets = {
            'file': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'file': 'Archivo de Entrega',
        }
        help_texts = {
            'file': 'Sube tu archivo (PDF, Office, o Canva). Máximo 50MB',
        }
    
    def __init__(self, *args, **kwargs):
        self.assignment = kwargs.pop('assignment', None)
        self.student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if not file:
            raise forms.ValidationError('Debe seleccionar un archivo para entregar.')
        
        # Size validation (50MB max)
        max_size = 50 * 1024 * 1024  # 50MB
        if file.size > max_size:
            raise forms.ValidationError(f'El archivo no puede ser mayor a 50MB.')
        
        # Extension validation - Office, PDF, Canva
        allowed_extensions = [
            # Office documents
            'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'odt', 'ods', 'odp',
            # PDF
            'pdf',
            # Canva exports (common formats)
            'png', 'jpg', 'jpeg', 'pdf',  # Canva can export as PDF or images
        ]
        
        file_extension = os.path.splitext(file.name)[1].lstrip('.').lower()
        if file_extension not in allowed_extensions:
            raise forms.ValidationError(
                f'Tipo de archivo no permitido. Solo se permiten: documentos de Office (doc, docx, ppt, pptx, xls, xlsx), PDF, o archivos de Canva (PDF, PNG, JPG).'
            )
        
        # Security: block dangerous extensions
        dangerous_extensions = ['exe', 'bat', 'cmd', 'com', 'pif', 'scr', 'vbs', 'js', 'zip', 'rar', '7z']
        if file_extension in dangerous_extensions:
            raise forms.ValidationError('Tipo de archivo no permitido por razones de seguridad.')
        
        return file
    
    def clean(self):
        cleaned_data = super().clean()
        
        if self.assignment and self.student:
            # Check if assignment allows submissions
            if not self.assignment.is_submission_allowed():
                raise forms.ValidationError('Ya no se pueden subir archivos para esta tarea.')
            
            # Check if student is enrolled
            enrollment = Enrollment.objects.filter(
                student=self.student,
                course=self.assignment.course,
                status='approved'
            ).first()
            
            if not enrollment:
                raise forms.ValidationError('Debes estar inscrito y aprobado en el curso para entregar tareas.')
        
        return cleaned_data


class FeedbackForm(forms.Form):
    """Form for teachers to give feedback on submissions"""
    feedback = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        label='Devolución',
        required=False,
        help_text='Escriba sus comentarios sobre la entrega del estudiante'
    )
    needs_resubmission = forms.BooleanField(
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label='Requiere Reentrega',
        required=False,
        help_text='Marque esta opción si el estudiante debe hacer una reentrega'
    )


class CollaboratorForm(forms.Form):
    """Form to add collaborators to a submission (for group work)"""
    collaborator_username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de usuario del colaborador'}),
        label='Nombre de Usuario del Colaborador',
        max_length=150,
        help_text='Ingrese el nombre de usuario del estudiante que desea agregar como colaborador'
    )
    
    def __init__(self, *args, **kwargs):
        self.submission = kwargs.pop('submission', None)
        self.current_student = kwargs.pop('current_student', None)
        super().__init__(*args, **kwargs)
    
    def clean_collaborator_username(self):
        username = self.cleaned_data.get('collaborator_username')
        
        if not username:
            return username
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        try:
            collaborator = User.objects.get(username=username)
        except User.DoesNotExist:
            raise forms.ValidationError('El usuario no existe.')
        
        if not collaborator.is_student():
            raise forms.ValidationError('Solo se pueden agregar estudiantes como colaboradores.')
        
        if self.submission and self.current_student:
            # Check if collaborator is enrolled in the course
            from courses.models import Enrollment
            enrollment = Enrollment.objects.filter(
                student=collaborator,
                course=self.submission.assignment.course,
                status='approved'
            ).first()
            
            if not enrollment:
                raise forms.ValidationError('El colaborador debe estar inscrito y aprobado en el curso.')
            
            # Check if already a collaborator
            if AssignmentCollaborator.objects.filter(
                submission=self.submission,
                student=collaborator
            ).exists():
                raise forms.ValidationError('Este estudiante ya es colaborador de esta entrega.')
            
            # Check if trying to add themselves
            if collaborator == self.current_student:
                raise forms.ValidationError('No puedes agregarte a ti mismo como colaborador.')
            
            # Check if collaborator is already the main student
            if collaborator == self.submission.student:
                raise forms.ValidationError('El estudiante principal no puede ser colaborador.')
        
        return username


class CommentForm(forms.ModelForm):
    """Form for adding comments to assignment submissions"""
    
    class Meta:
        model = AssignmentComment
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Escriba su comentario aquí...'
            }),
        }
        labels = {
            'comment': 'Comentario',
        }
        help_texts = {
            'comment': 'Escriba su comentario o respuesta',
        }
    
    def __init__(self, *args, **kwargs):
        self.submission = kwargs.pop('submission', None)
        self.user = kwargs.pop('user', None)
        self.parent_comment = kwargs.pop('parent_comment', None)
        super().__init__(*args, **kwargs)
