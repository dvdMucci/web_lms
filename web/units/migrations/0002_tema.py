from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('units', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Tema',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('description', models.TextField(verbose_name='Descripción')),
                ('is_paused', models.BooleanField(default=True, verbose_name='En Pausa')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creado en')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Actualizado en')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_temas', to=settings.AUTH_USER_MODEL, verbose_name='Creado por')),
                ('unit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='temas', to='units.unit', verbose_name='Unidad')),
            ],
            options={
                'verbose_name': 'Tema',
                'verbose_name_plural': 'Temas',
                'ordering': ['order', 'created_at'],
                'unique_together': {('unit', 'order')},
            },
        ),
    ]
