from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0002_material_link_url_material_material_type_and_more'),
        ('units', '0002_tema'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='tema',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='materials', to='units.tema', verbose_name='Tema'),
        ),
    ]
