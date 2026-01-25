# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0002_assignmentcomment'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='is_published',
            field=models.BooleanField(
                default=False,
                help_text='Si está desactivado, los estudiantes no podrán ver esta tarea',
                verbose_name='Publicado'
            ),
        ),
        migrations.AddField(
            model_name='assignment',
            name='scheduled_publish_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Si se establece, la tarea se publicará automáticamente en esta fecha y hora',
                null=True,
                verbose_name='Fecha/Hora de Publicación Programada'
            ),
        ),
        migrations.AddField(
            model_name='assignment',
            name='send_notification_email',
            field=models.BooleanField(
                default=False,
                help_text='Si está activado, se enviará un correo a los estudiantes cuando se publique la tarea',
                verbose_name='Enviar Notificación por Correo'
            ),
        ),
    ]
