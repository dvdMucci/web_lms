# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0002_material_link_url_material_material_type_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='material',
            name='is_published',
            field=models.BooleanField(
                default=False,
                help_text='Si está desactivado, los estudiantes no podrán ver este material',
                verbose_name='Publicado'
            ),
        ),
        migrations.AddField(
            model_name='material',
            name='scheduled_publish_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Si se establece, el material se publicará automáticamente en esta fecha y hora',
                null=True,
                verbose_name='Fecha/Hora de Publicación Programada'
            ),
        ),
        migrations.AddField(
            model_name='material',
            name='send_notification_email',
            field=models.BooleanField(
                default=False,
                help_text='Si está activado, se enviará un correo a los estudiantes cuando se publique el material',
                verbose_name='Enviar Notificación por Correo'
            ),
        ),
    ]
