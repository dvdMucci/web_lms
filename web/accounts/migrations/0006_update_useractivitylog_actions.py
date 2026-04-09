from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_useractivitylog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='useractivitylog',
            name='action',
            field=models.CharField(
                choices=[
                    ('login', 'Inicio de sesión'),
                    ('logout', 'Cierre de sesión'),
                    ('user_created', 'Usuario creado'),
                    ('user_updated', 'Usuario actualizado'),
                    ('user_deleted', 'Usuario eliminado'),
                    ('course_created', 'Curso creado'),
                    ('course_updated', 'Curso actualizado'),
                    ('course_deleted', 'Curso eliminado'),
                    ('enrollment_approved', 'Inscripción aprobada'),
                    ('enrollment_rejected', 'Inscripción rechazada'),
                    ('enrollment_cancelled', 'Inscripción cancelada'),
                    ('assignment_created', 'Tarea creada'),
                    ('assignment_updated', 'Tarea actualizada'),
                    ('assignment_deleted', 'Tarea eliminada'),
                    ('submission_uploaded', 'Entrega subida'),
                    ('submission_viewed', 'Entrega visualizada'),
                    ('submission_downloaded', 'Entrega descargada'),
                    ('material_uploaded', 'Material subido'),
                    ('material_updated', 'Material actualizado'),
                    ('material_deleted', 'Material eliminado'),
                    ('material_downloaded', 'Material descargado'),
                ],
                max_length=32,
            ),
        ),
    ]
