from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0001_initial'),
        ('units', '0002_tema'),
    ]

    operations = [
        migrations.AddField(
            model_name='assignment',
            name='tema',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='units.tema', verbose_name='Tema'),
        ),
    ]
