from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0006_submission_multiple_files'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='target_students',
            field=models.ManyToManyField(
                blank=True,
                help_text='Si se deja vacío, la tarea es visible para todos los alumnos inscriptos. Si se seleccionan alumnos específicos, solo ellos verán la tarea.',
                related_name='targeted_assignments',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Alumnos destinatarios',
            ),
        ),
    ]
