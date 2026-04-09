from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_studentregistrationtoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_username', models.CharField(blank=True, max_length=150)),
                ('action', models.CharField(choices=[('login', 'Inicio de sesión'), ('logout', 'Cierre de sesión'), ('user_created', 'Usuario creado'), ('user_updated', 'Usuario actualizado'), ('user_deleted', 'Usuario eliminado')], max_length=32)),
                ('details', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs_made', to=settings.AUTH_USER_MODEL)),
                ('target_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs_received', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Registro de actividad de usuario',
                'verbose_name_plural': 'Registros de actividad de usuario',
                'ordering': ['-created_at'],
            },
        ),
    ]
