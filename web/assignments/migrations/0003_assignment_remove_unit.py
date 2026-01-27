from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0002_assignment_tema'),
        ('units', '0003_tema_data_migration'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='assignment',
            name='unit',
        ),
        migrations.AlterField(
            model_name='assignment',
            name='tema',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='units.tema', verbose_name='Tema'),
        ),
    ]
