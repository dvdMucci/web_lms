from django.db import models
from django.conf import settings

class Notification(models.Model):
    TYPE_CHOICES = [
        ('comment', 'Comentario en entrega'),
        ('material', 'Material nuevo'),
        ('assignment', 'Tarea nueva'),
        ('exam', 'Examen disponible'),
        ('grade', 'Calificación recibida'),
        ('enrollment', 'Inscripción'),
        ('submission', 'Nueva entrega'),
    ]

    ICON_MAP = {
        'comment': 'fas fa-comment',
        'material': 'fas fa-file',
        'assignment': 'fas fa-tasks',
        'exam': 'fas fa-pen',
        'grade': 'fas fa-star',
        'enrollment': 'fas fa-user-plus',
        'submission': 'fas fa-upload',
    }

    COLOR_MAP = {
        'comment': 'text-primary',
        'material': 'text-success',
        'assignment': 'text-warning',
        'exam': 'text-danger',
        'grade': 'text-info',
        'enrollment': 'text-secondary',
        'submission': 'text-success',
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Usuario',
    )
    notification_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, verbose_name='Tipo',
    )
    title = models.CharField(max_length=200, verbose_name='Título')
    message = models.TextField(verbose_name='Mensaje')
    url = models.CharField(max_length=500, blank=True, verbose_name='URL')
    is_read = models.BooleanField(default=False, verbose_name='Leída')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creada en')

    class Meta:
        verbose_name = 'Notificación'
        verbose_name_plural = 'Notificaciones'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username} — {self.title}'

    @property
    def icon(self):
        return self.ICON_MAP.get(self.notification_type, 'fas fa-bell')

    @property
    def color(self):
        return self.COLOR_MAP.get(self.notification_type, 'text-primary')
