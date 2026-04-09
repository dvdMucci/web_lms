from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_customuser_email_verification_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='StudentRegistrationToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, max_length=64, unique=True)),
                ('starts_at', models.DateTimeField()),
                ('expires_at', models.DateTimeField()),
                ('is_active', models.BooleanField(default=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('max_uses', models.PositiveIntegerField(blank=True, null=True)),
                ('uses_count', models.PositiveIntegerField(default=0)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_registration_tokens', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Token de registro de alumnos',
                'verbose_name_plural': 'Tokens de registro de alumnos',
                'ordering': ['-created_at'],
            },
        ),
    ]
