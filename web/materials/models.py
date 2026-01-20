from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
import os
import uuid
from datetime import datetime

def material_upload_path(instance, filename):
    """Generate serialized filename for materials"""
    # Get file extension
    ext = os.path.splitext(filename)[1]
    # Generate unique filename using UUID and timestamp
    unique_filename = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    # Store original filename in instance
    instance.original_filename = filename
    return f'materials/{unique_filename}'

class Material(models.Model):
    MATERIAL_TYPE_CHOICES = [
        ('file', 'Archivo'),
        ('link', 'Enlace'),
    ]

    VISIBILITY_CHOICES = [
        ('public', 'Público'),
        ('enrolled', 'Inscritos'),
        ('private', 'Privado'),
    ]

    title = models.CharField(max_length=200, verbose_name="Título")
    description = models.TextField(blank=True, verbose_name="Descripción")
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.CASCADE,
        related_name="materials",
        verbose_name="Curso"
    )
    unit = models.ForeignKey(
        'units.Unit',
        on_delete=models.CASCADE,
        related_name="materials",
        null=True,
        blank=True,
        verbose_name="Unidad"
    )
    material_type = models.CharField(
        max_length=10,
        choices=MATERIAL_TYPE_CHOICES,
        default='file',
        verbose_name="Tipo de Material"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_materials",
        verbose_name="Subido por"
    )
    file = models.FileField(upload_to=material_upload_path, blank=True, null=True, verbose_name="Archivo")
    link_url = models.URLField(blank=True, null=True, verbose_name="URL del Enlace")
    original_filename = models.CharField(max_length=255, blank=True, verbose_name="Nombre Original del Archivo")
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default='enrolled',
        verbose_name="Visibilidad"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Subido en")
    file_size = models.PositiveIntegerField(blank=True, null=True, verbose_name="Tamaño del archivo")
    file_type = models.CharField(max_length=100, blank=True, verbose_name="Tipo de archivo")

    class Meta:
        verbose_name = "Material"
        verbose_name_plural = "Materiales"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title

    def clean(self):
        # Only validate if uploaded_by is set and has a value
        if self.uploaded_by_id is not None and self.course_id is not None:
            from django.contrib.auth import get_user_model
            from courses.models import Course
            User = get_user_model()
            try:
                user = User.objects.get(pk=self.uploaded_by_id)
                course = Course.objects.get(pk=self.course_id)
            except (User.DoesNotExist, Course.DoesNotExist):
                return
            
            if not (user.is_teacher() or user.user_type == 'admin'):
                raise ValidationError("Solo instructores o administradores pueden subir materiales.")
            
            # Validate course permissions (instructor, collaborator, or admin)
            is_instructor = course.instructor_id == self.uploaded_by_id
            is_collaborator = self.uploaded_by_id in course.collaborators.values_list('id', flat=True)
            is_admin = user.user_type == 'admin'
            
            if not (is_instructor or is_collaborator or is_admin):
                raise ValidationError("Solo el instructor, colaboradores o administradores pueden subir materiales a este curso.")
            
            # Validate unit permissions if unit is specified
            if self.unit_id is not None:
                from units.models import Unit
                try:
                    unit = Unit.objects.get(pk=self.unit_id)
                    if unit.course_id != self.course_id:
                        raise ValidationError("La unidad debe pertenecer al curso especificado.")
                except Unit.DoesNotExist:
                    pass
        
        # Validate material type
        if self.material_type == 'file' and not self.file:
            raise ValidationError("Debe proporcionar un archivo para materiales de tipo archivo.")
        if self.material_type == 'link' and not self.link_url:
            raise ValidationError("Debe proporcionar una URL para materiales de tipo enlace.")
        if self.material_type == 'file' and self.link_url:
            raise ValidationError("No puede tener una URL cuando el tipo es archivo.")
        if self.material_type == 'link' and self.file:
            raise ValidationError("No puede tener un archivo cuando el tipo es enlace.")

    def save(self, *args, **kwargs):
        # Only run clean if uploaded_by_id is set (avoid accessing uploaded_by directly to prevent RelatedObjectDoesNotExist)
        if self.uploaded_by_id is not None:
            self.clean()
        super().save(*args, **kwargs)

@receiver(post_save, sender=Material)
def update_file_info(sender, instance, created, **kwargs):
    if instance.file:
        file_size = instance.file.size
        file_type = os.path.splitext(instance.file.name)[1].lstrip('.')
        original_filename = instance.original_filename or os.path.basename(instance.file.name)
        if created or instance.file_size != file_size or instance.file_type != file_type or instance.original_filename != original_filename:
            instance.file_size = file_size
            instance.file_type = file_type
            instance.original_filename = original_filename
            instance.save(update_fields=['file_size', 'file_type', 'original_filename'])
    else:
        if instance.file_size or instance.file_type or instance.original_filename:
            instance.file_size = None
            instance.file_type = ''
            instance.original_filename = ''
            instance.save(update_fields=['file_size', 'file_type', 'original_filename'])


@receiver(pre_save, sender=Material)
def delete_old_material_file(sender, instance, **kwargs):
    if not instance.pk:
        return
    old_instance = Material.objects.filter(pk=instance.pk).only('file').first()
    if not old_instance or not old_instance.file:
        return
    old_file = old_instance.file
    new_file = instance.file
    if not new_file or old_file.name != new_file.name:
        old_file.delete(save=False)


@receiver(post_delete, sender=Material)
def delete_material_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
