from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='examquestion',
            name='correct_explanation',
            field=models.TextField(
                blank=True,
                default='',
                verbose_name='Aclaración de la respuesta correcta (opcional)',
                help_text='Texto opcional para mostrar al alumno junto con la respuesta correcta.',
            ),
        ),
        migrations.AlterField(
            model_name='examattempt',
            name='score',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name='Puntaje (1,00–10,00)',
            ),
        ),
    ]
