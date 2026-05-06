from django import forms
from .models import Unit, Tema
from courses.models import Course
from materials.models import Material
import os

class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ['title', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'title': 'Título',
            'order': 'Orden',
        }
        help_texts = {
            'title': 'Ingrese el título de la unidad',
            'order': 'Orden de visualización (0 = primero)',
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.course = kwargs.pop('course', None)
        super().__init__(*args, **kwargs)
    
    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order is not None and order < 0:
            raise forms.ValidationError('El orden debe ser mayor o igual a 0.')
        return order


class TemaForm(forms.ModelForm):
    PUBLICATION_CHOICES = [
        ('no_publicar', 'No publicar'),
        ('publicar_ahora', 'Publicar ahora'),
        ('programar', 'Programar fecha de publicación'),
    ]

    publication_mode = forms.ChoiceField(
        choices=PUBLICATION_CHOICES,
        initial='no_publicar',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Publicación',
        required=True,
    )
    scheduled_publish_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        label='Fecha y hora de publicación',
    )

    class Meta:
        model = Tema
        fields = ['title', 'description', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'title': 'Título',
            'description': 'Descripción',
            'order': 'Orden',
        }
        help_texts = {
            'title': 'Ingrese el título del tema',
            'description': 'Describa el contenido del tema',
            'order': 'Orden de visualización (0 = primero)',
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.unit = kwargs.pop('unit', None)
        super().__init__(*args, **kwargs)
        datetime_local_format = '%Y-%m-%dT%H:%M'
        self.fields['scheduled_publish_at'].widget.format = datetime_local_format
        self.fields['scheduled_publish_at'].input_formats = [
            '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
        ]
        # Pre-fill publication_mode and scheduled_publish_at when editing
        if self.instance and self.instance.pk:
            if self.instance.scheduled_publish_at:
                self.fields['publication_mode'].initial = 'programar'
                from django.utils import timezone
                val = timezone.localtime(self.instance.scheduled_publish_at)
                self.fields['scheduled_publish_at'].initial = val.strftime(datetime_local_format)
            elif not self.instance.is_paused:
                self.fields['publication_mode'].initial = 'publicar_ahora'
            else:
                self.fields['publication_mode'].initial = 'no_publicar'

    def clean(self):
        cleaned_data = super().clean()
        publication_mode = cleaned_data.get('publication_mode')
        scheduled_publish_at = cleaned_data.get('scheduled_publish_at')

        if publication_mode == 'programar':
            if not scheduled_publish_at:
                raise forms.ValidationError({'scheduled_publish_at': 'Debe indicar la fecha y hora de publicación.'})
            from django.utils import timezone
            dt = scheduled_publish_at
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            if dt <= timezone.now():
                raise forms.ValidationError({'scheduled_publish_at': 'La fecha de publicación debe ser en el futuro.'})

        return cleaned_data

    def clean_order(self):
        order = self.cleaned_data.get('order')
        if order is not None and order < 0:
            raise forms.ValidationError('El orden debe ser mayor o igual a 0.')
        return order

    def save(self, commit=True):
        tema = super().save(commit=False)
        publication_mode = self.cleaned_data.get('publication_mode')
        scheduled_publish_at = self.cleaned_data.get('scheduled_publish_at')

        if publication_mode == 'publicar_ahora':
            tema.is_paused = False
            tema.scheduled_publish_at = None
        elif publication_mode == 'programar':
            tema.is_paused = True
            from django.utils import timezone
            dt = scheduled_publish_at
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            tema.scheduled_publish_at = dt
        else:  # no_publicar
            tema.is_paused = True
            tema.scheduled_publish_at = None

        if commit:
            tema.save()
        return tema


class MaterialUploadForm(forms.ModelForm):
    MATERIAL_TYPE_CHOICES = [
        ('file', 'Archivo'),
        ('link', 'Enlace'),
    ]
    
    material_type = forms.ChoiceField(
        choices=MATERIAL_TYPE_CHOICES,
        initial='file',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='Tipo de Material'
    )
    
    class Meta:
        model = Material
        fields = ['title', 'description', 'material_type', 'file', 'link_url', 'visibility', 
                  'is_published', 'scheduled_publish_at', 'send_notification_email']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'link_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'visibility': forms.Select(attrs={'class': 'form-control'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'scheduled_publish_at': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'send_notification_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Título',
            'description': 'Descripción',
            'file': 'Archivo',
            'link_url': 'URL del Enlace',
            'visibility': 'Visibilidad',
            'is_published': 'Publicar Ahora',
            'scheduled_publish_at': 'Publicar Más Tarde (Fecha/Hora)',
            'send_notification_email': 'Enviar Correo de Notificación',
        }
        help_texts = {
            'title': 'Nombre que verán los estudiantes',
            'description': 'Descripción opcional del material',
            'file': 'Seleccione el archivo a subir (máx. 50MB)',
            'link_url': 'URL completa del enlace (debe comenzar con http:// o https://)',
            'visibility': 'Quién puede ver este material',
            'is_published': 'Si está activado, el material estará disponible para los estudiantes inmediatamente',
            'scheduled_publish_at': 'Opcional: Programe la publicación para una fecha y hora específica. Si se establece, el material se publicará automáticamente en ese momento',
            'send_notification_email': 'Si está activado, se enviará un correo a todos los estudiantes inscritos cuando se publique el material',
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.course = kwargs.pop('course', None)
        self.tema = kwargs.pop('tema', None)
        self.assignment = kwargs.pop('assignment', None)
        super().__init__(*args, **kwargs)
        self.fields['file'].widget.attrs['accept'] = (
            '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.jpg,.jpeg,.png,.gif,'
            '.mp4,.avi,.mov,.zip,.rar,.7z,.pkt'
        )
        datetime_local_format = '%Y-%m-%dT%H:%M'
        self.fields['scheduled_publish_at'].widget.format = datetime_local_format
        # Aceptar el formato de <input type="datetime-local">: YYYY-MM-DDTHH:mm
        self.fields['scheduled_publish_at'].input_formats = [
            '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M',
        ]
        # Set initial material type
        if self.instance and self.instance.pk:
            self.fields['material_type'].initial = self.instance.material_type
            value = getattr(self.instance, 'scheduled_publish_at', None)
            if value:
                from django.utils import timezone
                value = timezone.localtime(value)
                self.initial['scheduled_publish_at'] = value.strftime(datetime_local_format)
        else:
            self.fields['material_type'].initial = 'file'
            # Material guía de tarea: por UX se publica para inscriptos por defecto.
            if self.assignment is not None:
                self.fields['visibility'].initial = 'enrolled'
                self.fields['is_published'].initial = True
    
    def clean(self):
        cleaned_data = super().clean()
        material_type = cleaned_data.get('material_type')
        file = cleaned_data.get('file')
        link_url = cleaned_data.get('link_url')
        is_published = cleaned_data.get('is_published', False)
        scheduled_publish_at = cleaned_data.get('scheduled_publish_at')
        
        if material_type == 'file':
            if not file:
                raise forms.ValidationError({'file': 'Debe proporcionar un archivo para materiales de tipo archivo.'})
            if link_url:
                raise forms.ValidationError('No puede tener una URL cuando el tipo es archivo.')
        elif material_type == 'link':
            if not link_url:
                raise forms.ValidationError({'link_url': 'Debe proporcionar una URL para materiales de tipo enlace.'})
            if file:
                raise forms.ValidationError('No puede tener un archivo cuando el tipo es enlace.')
        
        # Validar lógica de publicación
        if scheduled_publish_at and is_published:
            raise forms.ValidationError({
                'is_published': 'No puede publicar inmediatamente si tiene una fecha de publicación programada. Desactive "Publicar Ahora" o elimine la fecha programada.'
            })
        
        if scheduled_publish_at:
            from django.utils import timezone
            dt = scheduled_publish_at
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            if dt <= timezone.now():
                raise forms.ValidationError({
                    'scheduled_publish_at': 'La fecha de publicación programada debe ser en el futuro.'
                })

        if self.assignment is not None and self.tema is not None:
            if self.assignment.tema_id != self.tema.id:
                raise forms.ValidationError('El tema del formulario no coincide con la tarea.')
        
        return cleaned_data
    
    def save(self, commit=True):
        material = super().save(commit=False)
        # Si hay una fecha programada, no publicar ahora
        if material.scheduled_publish_at:
            material.is_published = False
        if self.assignment is not None:
            material.assignment = self.assignment
        
        if commit:
            material.save()
        return material
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if not file:
            return file
        
        # Size validation (50MB max)
        max_size = 50 * 1024 * 1024  # 50MB
        if file.size > max_size:
            raise forms.ValidationError(f'El archivo no puede ser mayor a {max_size / (1024*1024):.0f}MB.')
        
        # Extension validation
        allowed_extensions = [
            'pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx',
            'txt', 'jpg', 'jpeg', 'png', 'gif', 'mp4', 'avi', 'mov',
            'zip', 'rar', '7z', 'pkt'
        ]
        
        file_extension = os.path.splitext(file.name)[1].lstrip('.').lower()
        if file_extension not in allowed_extensions:
            raise forms.ValidationError(
                f'Tipo de archivo no permitido. Extensiones permitidas: {", ".join(allowed_extensions)}'
            )
        
        # MIME type validation (basic check)
        dangerous_extensions = ['exe', 'bat', 'cmd', 'com', 'pif', 'scr', 'vbs', 'js']
        if file_extension in dangerous_extensions:
            raise forms.ValidationError('Tipo de archivo no permitido por razones de seguridad.')
        
        return file
    
    def clean_link_url(self):
        link_url = self.cleaned_data.get('link_url')
        if link_url:
            # Basic URL validation
            if not (link_url.startswith('http://') or link_url.startswith('https://')):
                raise forms.ValidationError('La URL debe comenzar con http:// o https://')
        return link_url


class MaterialEditForm(MaterialUploadForm):
    def clean(self):
        cleaned_data = forms.ModelForm.clean(self)
        material_type = cleaned_data.get('material_type')
        file = cleaned_data.get('file')
        link_url = cleaned_data.get('link_url')

        if material_type == 'file':
            if not file and not (self.instance and self.instance.file):
                raise forms.ValidationError({'file': 'Debe proporcionar un archivo para materiales de tipo archivo.'})
            if link_url:
                raise forms.ValidationError('No puede tener una URL cuando el tipo es archivo.')
        elif material_type == 'link':
            if not link_url:
                raise forms.ValidationError({'link_url': 'Debe proporcionar una URL para materiales de tipo enlace.'})
            if file:
                raise forms.ValidationError('No puede tener un archivo cuando el tipo es enlace.')

        return cleaned_data

    def save(self, commit=True):
        material = super().save(commit=False)
        material.material_type = self.cleaned_data.get('material_type', material.material_type)

        if material.material_type == 'file':
            material.link_url = None
        elif material.material_type == 'link':
            material.file = None
            material.original_filename = ''
            material.file_size = None
            material.file_type = ''

        if commit:
            material.save()
        return material
