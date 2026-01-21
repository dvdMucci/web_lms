from django.db import models
from django.core.exceptions import ValidationError


class StorageConfig(models.Model):
    """
    Configuración del almacenamiento del bucket OCI.
    Solo debe haber una instancia de esta configuración.
    """
    total_storage_gb = models.PositiveIntegerField(
        default=20,
        verbose_name="Espacio Total (GB)",
        help_text="Espacio total contratado en el bucket (en GB)"
    )
    alert_threshold_percent = models.PositiveIntegerField(
        default=80,
        verbose_name="Umbral de Alerta (%)",
        help_text="Porcentaje de uso que activa una alerta (0-100)"
    )
    alert_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name="Email para Alertas",
        help_text="Email donde se enviarán las alertas de almacenamiento. Si está vacío, se usará el email del superusuario."
    )
    alert_enabled = models.BooleanField(
        default=True,
        verbose_name="Alertas Habilitadas",
        help_text="Activar o desactivar las notificaciones de almacenamiento"
    )
    last_alert_sent = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Última Alerta Enviada",
        help_text="Fecha y hora de la última alerta enviada"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Creado en")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Actualizado en")

    class Meta:
        verbose_name = "Configuración de Almacenamiento"
        verbose_name_plural = "Configuración de Almacenamiento"
        ordering = ['-updated_at']

    def __str__(self):
        return f"Almacenamiento: {self.total_storage_gb}GB - Umbral: {self.alert_threshold_percent}%"

    def clean(self):
        if self.alert_threshold_percent > 100:
            raise ValidationError({'alert_threshold_percent': 'El umbral no puede ser mayor a 100%.'})

    def save(self, *args, **kwargs):
        # Asegurar que solo hay una instancia
        if not self.pk and StorageConfig.objects.exists():
            raise ValidationError("Solo puede haber una configuración de almacenamiento.")
        self.full_clean()
        super().save(*args, **kwargs)
