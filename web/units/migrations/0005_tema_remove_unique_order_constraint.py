from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('units', '0004_unit_remove_description'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='tema',
            unique_together=set(),
        ),
    ]

