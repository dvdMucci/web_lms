# Migración de datos: marcar como publicados todas las tareas existentes
# para que los alumnos inscritos sigan pudiendo verlas (comportamiento anterior).

from django.db import migrations


def set_existing_assignments_published(apps, schema_editor):
    Assignment = apps.get_model('assignments', 'Assignment')
    Assignment.objects.all().update(is_published=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('assignments', '0003_assignment_publish_fields'),
    ]

    operations = [
        migrations.RunPython(set_existing_assignments_published, noop),
    ]
