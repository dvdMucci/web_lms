from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('units', '0003_tema_data_migration'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='unit',
            name='description',
        ),
    ]
