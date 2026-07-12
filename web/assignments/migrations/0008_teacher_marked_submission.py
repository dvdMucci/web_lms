from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('assignments', '0007_assignment_target_students'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='allow_student_upload',
            field=models.BooleanField(
                default=True,
                help_text=(
                    'Si está desactivado, el alumno no puede subir material: '
                    'el docente registra la entrega y si fue a tiempo o no.'
                ),
                verbose_name='Permitir subida de archivos por el alumno',
            ),
        ),
        migrations.AddField(
            model_name='assignmentsubmission',
            name='is_teacher_marked',
            field=models.BooleanField(
                default=False,
                help_text='True cuando el docente registró la entrega sin subida del alumno.',
                verbose_name='Registrada por el docente',
            ),
        ),
        migrations.AddField(
            model_name='assignmentsubmission',
            name='teacher_marked_on_time',
            field=models.BooleanField(
                blank=True,
                help_text='Si no es nulo, prevalece sobre el cálculo automático por fecha.',
                null=True,
                verbose_name='Entrega a tiempo (marca docente)',
            ),
        ),
        migrations.AddField(
            model_name='assignmentsubmission',
            name='teacher_marked_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Marcada por el docente en',
            ),
        ),
        migrations.AddField(
            model_name='assignmentsubmission',
            name='teacher_marked_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='teacher_marked_submissions',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Marcada por',
            ),
        ),
    ]
