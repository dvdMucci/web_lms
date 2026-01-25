# Migración de datos: marcar como publicados todos los materiales existentes
# para que los alumnos inscritos sigan pudiendo verlos (comportamiento anterior).

from django.db import migrations


def set_existing_materials_published(apps, schema_editor):
    Material = apps.get_model('materials', 'Material')
    Material.objects.all().update(is_published=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0003_material_publish_fields'),
    ]

    operations = [
        migrations.RunPython(set_existing_materials_published, noop),
    ]
