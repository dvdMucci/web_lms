# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0002_course_collaborators_course_is_paused'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='enrollment_open',
            field=models.BooleanField(
                default=False,
                help_text='Si está activo, el curso acepta nuevas inscripciones (sujeto a fechas si se definen).',
                verbose_name='Inscripción abierta'
            ),
        ),
        migrations.AddField(
            model_name='course',
            name='enrollment_opens_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Opcional. Si se define, la inscripción solo estará abierta a partir de esta fecha y hora.',
                null=True,
                verbose_name='Inscripción abre el'
            ),
        ),
        migrations.AddField(
            model_name='course',
            name='enrollment_closes_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Opcional. Si se define, la inscripción se cierra en esta fecha y hora.',
                null=True,
                verbose_name='Inscripción cierra el'
            ),
        ),
    ]
