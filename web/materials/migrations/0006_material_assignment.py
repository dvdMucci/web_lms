# Generated manually for assignment guide materials

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0001_initial'),
        ('materials', '0005_merge_20260127_1045'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='assignment',
            field=models.ForeignKey(
                blank=True,
                help_text='Si se indica, el material es guía de esa tarea y no aparece en la lista de materiales del tema.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='guide_materials',
                to='assignments.assignment',
                verbose_name='Tarea (material guía)',
            ),
        ),
        migrations.AddIndex(
            model_name='material',
            index=models.Index(fields=['assignment', 'is_published'], name='mat_assign_pub_idx'),
        ),
    ]
