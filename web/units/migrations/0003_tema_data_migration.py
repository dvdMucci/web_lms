from django.db import migrations


def create_default_temas(apps, schema_editor):
    Unit = apps.get_model('units', 'Unit')
    Tema = apps.get_model('units', 'Tema')
    Material = apps.get_model('materials', 'Material')
    Assignment = apps.get_model('assignments', 'Assignment')

    for unit in Unit.objects.all():
        tema = Tema.objects.create(
            unit=unit,
            title='Tema principal',
            description=getattr(unit, 'description', ''),
            created_by=unit.created_by,
            is_paused=unit.is_paused,
            order=0,
        )
        Material.objects.filter(unit=unit).update(tema=tema)
        Assignment.objects.filter(unit=unit).update(tema=tema)


class Migration(migrations.Migration):

    dependencies = [
        ('units', '0002_tema'),
        ('materials', '0003_material_tema'),
        ('assignments', '0002_assignment_tema'),
    ]

    operations = [
        migrations.RunPython(create_default_temas, migrations.RunPython.noop),
    ]
