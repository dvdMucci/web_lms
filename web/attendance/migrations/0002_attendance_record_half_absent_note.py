from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='attendancerecord',
            name='status',
            field=models.CharField(choices=[('present', 'Presente'), ('absent', 'Ausente'), ('half_absent', 'Media falta')], max_length=12, verbose_name='Estado'),
        ),
        migrations.AddField(
            model_name='attendancerecord',
            name='note',
            field=models.TextField(blank=True, verbose_name='Nota'),
        ),
    ]
