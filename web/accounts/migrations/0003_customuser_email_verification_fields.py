from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_customuser_user_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='customuser',
            name='email_verification_sent_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Ultimo envio de verificacion'),
        ),
        migrations.AddField(
            model_name='customuser',
            name='email_verified_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Email verificado el'),
        ),
    ]
