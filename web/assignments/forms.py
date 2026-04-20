from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Assignment, AssignmentSubmission, AssignmentCollaborator, AssignmentComment
from courses.models import Enrollment
import os


class AssignmentForm(forms.ModelForm):
    """Form for creating and editing assignments"""
    
    class Meta:
        model = Assignment
        fields = ['title', 'description', 'due_date', 'final_date', 'allow_group_work', 'is_active',
                  'is_published', 'scheduled_publish_at', 'send_notification_email']
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
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'scheduled_publish_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'send_notification_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Título de la Tarea',
            'description': 'Descripción e Instrucciones',
            'due_date': 'Fecha Límite de Entrega',
            'final_date': 'Fecha Final (Opcional - No se podrán subir más archivos después de esta fecha)',
            'allow_group_work': 'Permitir Trabajo en Grupo',
            'is_active': 'Tarea Activa',
            'is_published': 'Publicar Ahora',
            'scheduled_publish_at': 'Publicar Más Tarde (Fecha/Hora)',
            'send_notification_email': 'Enviar Correo de Notificación',
        }
        help_texts = {
            'title': 'Ingrese el título de la tarea',
            'description': 'Describa la tarea y las instrucciones para los estudiantes',
            'due_date': 'Fecha y hora límite para entregar sin penalización',
            'final_date': 'Si se establece, después de esta fecha no se podrán subir más archivos',
            'allow_group_work': 'Si está habilitado, los estudiantes podrán agregar colaboradores',
            'is_active': 'Si está desactivada, los estudiantes no podrán verla',
            'is_published': 'Si está activado, la tarea estará disponible para los estudiantes inmediatamente',
            'scheduled_publish_at': 'Opcional: Programe la publicación para una fecha y hora específica. Si se establece, la tarea se publicará automáticamente en ese momento',
            'send_notification_email': 'Si está activado, se enviará un correo a todos los estudiantes inscritos cuando se publique la tarea',
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.course = kwargs.pop('course', None)
        self.tema = kwargs.pop('tema', None)
        super().__init__(*args, **kwargs)
        datetime_local_format = '%Y-%m-%dT%H:%M'

        # Forzar formato de render para que datetime-local precargue correctamente
        for name in ('due_date', 'final_date', 'scheduled_publish_at'):
            self.fields[name].widget.format = datetime_local_format

        # Aceptar formato de <input type="datetime-local">: YYYY-MM-DDTHH:mm
        for name in ('due_date', 'final_date', 'scheduled_publish_at'):
            self.fields[name].input_formats = [
                '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
            ]

        # En edición, mostrar la fecha/hora ya guardada en formato esperado
        if self.instance and self.instance.pk:
            for name in ('due_date', 'final_date', 'scheduled_publish_at'):
                value = getattr(self.instance, name, None)
                if value:
                    value = timezone.localtime(value)
                    self.initial[name] = value.strftime(datetime_local_format)

    def clean(self):
        cleaned_data = super().clean()
        due_date = cleaned_data.get('due_date')
        final_date = cleaned_data.get('final_date')
        is_published = cleaned_data.get('is_published', False)
        scheduled_publish_at = cleaned_data.get('scheduled_publish_at')
        
        if due_date and final_date:
            if final_date < due_date:
                raise forms.ValidationError({
                    'final_date': 'La fecha final no puede ser anterior a la fecha límite de entrega.'
                })
        
        # Validar lógica de publicación
        if scheduled_publish_at and is_published:
            raise forms.ValidationError({
                'is_published': 'No puede publicar inmediatamente si tiene una fecha de publicación programada. Desactive "Publicar Ahora" o elimine la fecha programada.'
            })
        
        if scheduled_publish_at:
            dt = scheduled_publish_at
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            if dt <= timezone.now():
                raise forms.ValidationError({
                    'scheduled_publish_at': 'La fecha de publicación programada debe ser en el futuro.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        assignment = super().save(commit=False)
        # Si hay una fecha programada, no publicar ahora
        if assignment.scheduled_publish_at:
            assignment.is_published = False
        
        if commit:
            assignment.save()
        return assignment


# Office, PDF, Canva (imágenes / pdf) — máx. 50 MB por archivo
SUBMISSION_ALLOWED_EXTENSIONS = frozenset({
    'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
    'pdf', 'png', 'jpg', 'jpeg',
})
SUBMISSION_MAX_FILE_BYTES = 50 * 1024 * 1024


def _validate_submission_upload_file(upload):
    """Valida extensión y tamaño de un UploadedFile."""
    max_size = SUBMISSION_MAX_FILE_BYTES
    if upload.size > max_size:
        raise forms.ValidationError(
            f'«{upload.name}»: cada archivo no puede superar 50 MB.'
        )
    ext = os.path.splitext(upload.name)[1].lstrip('.').lower()
    if ext not in SUBMISSION_ALLOWED_EXTENSIONS:
        raise forms.ValidationError(
            f'«{upload.name}»: tipo no permitido. Use Office (.doc, .docx, .ppt, .pptx, .xls, .xlsx), '
            '.pdf o imágenes/PDF de Canva (.pdf, .png, .jpg, .jpeg).'
        )
    dangerous = {'exe', 'bat', 'cmd', 'com', 'pif', 'scr', 'vbs', 'js', 'zip', 'rar', '7z'}
    if ext in dangerous:
        raise forms.ValidationError(f'«{upload.name}»: tipo de archivo no permitido por seguridad.')
    return upload


class SubmissionForm(forms.Form):
    """Varios archivos por entrega."""
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

    def __init__(self, *args, **kwargs):
        self.assignment = kwargs.pop('assignment', None)
        self.student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        uploads = self.files.getlist('files')
        if not uploads:
            raise forms.ValidationError('Seleccioná al menos un archivo para entregar.')
        validated = []
        errors = []
        for upload in uploads:
            try:
                validated.append(_validate_submission_upload_file(upload))
            except forms.ValidationError as e:
                errors.extend(e.messages)
        if errors:
            raise forms.ValidationError(errors)
        cleaned_data['file_list'] = validated

        if self.assignment and self.student:
            if not self.assignment.is_submission_allowed():
                raise forms.ValidationError('Ya no se pueden subir archivos para esta tarea.')
            enrollment = Enrollment.objects.filter(
                student=self.student,
                course=self.assignment.course,
                status='approved'
            ).first()
            if not enrollment:
                raise forms.ValidationError(
                    'Debes estar inscrito y aprobado en el curso para entregar tareas.'
                )

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
