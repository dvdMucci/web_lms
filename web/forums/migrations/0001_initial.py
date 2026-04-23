import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('courses', '0004_set_existing_courses_enrollment_open'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ForumPost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('content', models.TextField(verbose_name='Contenido')),
                ('is_private', models.BooleanField(
                    default=False,
                    help_text='Solo visible para el alumno participante y docentes del curso.',
                    verbose_name='Privado',
                )),
                ('is_pinned', models.BooleanField(default=False, verbose_name='Fijado')),
                ('is_locked', models.BooleanField(default=False, verbose_name='Bloqueado')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creado en')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Actualizado en')),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='forum_posts',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Autor',
                )),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='forum_posts',
                    to='courses.course',
                    verbose_name='Curso',
                )),
                ('student_participant', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='private_forum_posts',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Alumno participante',
                )),
            ],
            options={
                'verbose_name': 'Publicación del Foro',
                'verbose_name_plural': 'Publicaciones del Foro',
                'ordering': ['-is_pinned', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ForumReply',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(verbose_name='Contenido')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creado en')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Actualizado en')),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='forum_replies',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Autor',
                )),
                ('parent_reply', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='nested_replies',
                    to='forums.forumreply',
                    verbose_name='Respuesta padre',
                )),
                ('post', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='replies',
                    to='forums.forumpost',
                    verbose_name='Publicación',
                )),
            ],
            options={
                'verbose_name': 'Respuesta del Foro',
                'verbose_name_plural': 'Respuestas del Foro',
                'ordering': ['created_at'],
            },
        ),
    ]
