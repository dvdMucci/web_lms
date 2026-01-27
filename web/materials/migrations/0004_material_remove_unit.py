from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0003_material_tema'),
        ('units', '0003_tema_data_migration'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='material',
            name='unit',
        ),
        migrations.AlterField(
            model_name='material',
            name='tema',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='materials', to='units.tema', verbose_name='Tema'),
        ),
    ]
