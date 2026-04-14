from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0003_alter_examquestion_correct_explanation'),
    ]

    operations = [
        migrations.AddField(
            model_name='themeexam',
            name='attendance_date',
            field=models.DateField(
                blank=True,
                help_text='Opcional. Si se indica, solo podrán rendir el examen los alumnos '
                'marcados como presentes en esa fecha (según la planilla de asistencia del curso).',
                null=True,
                verbose_name='Fecha de asistencia requerida',
            ),
        ),
        migrations.AddField(
            model_name='examattemptanswer',
            name='dont_know',
            field=models.BooleanField(
                default=False,
                help_text='Respuesta fija del sistema (no es una opción cargada por el docente).',
                verbose_name='«No lo sé»',
            ),
        ),
    ]
