# Migración de datos: marcar inscripción abierta en cursos existentes
# para no ocultar cursos actuales a los alumnos.

from django.db import migrations


def set_existing_courses_enrollment_open(apps, schema_editor):
    Course = apps.get_model('courses', 'Course')
    Course.objects.all().update(enrollment_open=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0003_course_enrollment_open_dates'),
    ]

    operations = [
        migrations.RunPython(set_existing_courses_enrollment_open, noop),
    ]
