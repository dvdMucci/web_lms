from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0008_teacher_marked_submission'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='evaluation_type',
            field=models.CharField(
                choices=[
                    ('letter', 'Letras (R, B, MB, E)'),
                    ('numeric', 'Puntaje (0 a 10)'),
                ],
                default='letter',
                help_text='Cómo se califica esta tarea: con letras o con puntaje de 0 a 10.',
                max_length=20,
                verbose_name='Forma de evaluación',
            ),
        ),
        migrations.AddField(
            model_name='assignmentsubmission',
            name='grade_letter',
            field=models.CharField(
                blank=True,
                choices=[
                    ('R', 'R — Regular'),
                    ('B', 'B — Bueno'),
                    ('MB', 'MB — Muy bueno'),
                    ('E', 'E — Excelente'),
                ],
                max_length=2,
                null=True,
                verbose_name='Nota (letras)',
            ),
        ),
        migrations.AddField(
            model_name='assignmentsubmission',
            name='grade_score',
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                verbose_name='Nota (0 a 10)',
            ),
        ),
    ]
