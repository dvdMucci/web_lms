from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models.signals import post_save
from django.dispatch import receiver
import os

class Material(models.Model):
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
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_materials",
        verbose_name="Subido por"
    )
    file = models.FileField(upload_to='materials/', verbose_name="Archivo")
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
        if self.uploaded_by and not (self.uploaded_by.is_teacher() or self.uploaded_by.user_type == 'admin'):
            raise ValidationError("Solo instructores o administradores pueden subir materiales.")
        if self.course and self.uploaded_by != self.course.instructor and self.uploaded_by.user_type != 'admin':
            raise ValidationError("Solo el instructor del curso o administradores pueden subir materiales a este curso.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

@receiver(post_save, sender=Material)
def update_file_info(sender, instance, created, **kwargs):
    if created and instance.file:
        instance.file_size = instance.file.size
        instance.file_type = os.path.splitext(instance.file.name)[1].lstrip('.')
        instance.save(update_fields=['file_size', 'file_type'])
