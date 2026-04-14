# Generated manually for ThemeExam app

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('courses', '0004_set_existing_courses_enrollment_open'),
        ('units', '0005_tema_remove_unique_order_constraint'),
    ]

    operations = [
        migrations.CreateModel(
            name='ThemeExam',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Título')),
                ('description', models.TextField(blank=True, verbose_name='Descripción')),
                ('is_published', models.BooleanField(default=False, help_text='Si no está publicado, los alumnos no verán el examen.', verbose_name='Publicado')),
                ('available_from', models.DateTimeField(verbose_name='Disponible desde')),
                ('available_until', models.DateTimeField(verbose_name='Disponible hasta')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Creado en')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Actualizado en')),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='theme_exams', to='courses.course', verbose_name='Curso')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_theme_exams', to=settings.AUTH_USER_MODEL, verbose_name='Creado por')),
                ('tema', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='theme_exams', to='units.tema', verbose_name='Tema')),
            ],
            options={
                'verbose_name': 'Examen del tema',
                'verbose_name_plural': 'Exámenes del tema',
                'ordering': ['available_from', 'created_at'],
            },
        ),
        migrations.CreateModel(
            name='ExamQuestion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='Texto de la pregunta')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Orden')),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='quizzes.themeexam', verbose_name='Examen')),
            ],
            options={
                'verbose_name': 'Pregunta',
                'verbose_name_plural': 'Preguntas',
                'ordering': ['order', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ExamAnswerOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='Texto de la opción')),
                ('is_correct', models.BooleanField(default=False, verbose_name='Es correcta')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answer_options', to='quizzes.examquestion', verbose_name='Pregunta')),
            ],
            options={
                'verbose_name': 'Opción de respuesta',
                'verbose_name_plural': 'Opciones de respuesta',
            },
        ),
        migrations.CreateModel(
            name='ExamAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(auto_now_add=True, verbose_name='Iniciado en')),
                ('submitted_at', models.DateTimeField(blank=True, null=True, verbose_name='Enviado en')),
                ('score', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Puntaje (1–10)')),
                ('correct_count', models.PositiveIntegerField(blank=True, null=True, verbose_name='Respuestas correctas')),
                ('total_questions', models.PositiveIntegerField(blank=True, null=True, verbose_name='Total de preguntas')),
                ('shuffle_state', models.JSONField(blank=True, default=dict, help_text='question_ids y option_order por pregunta.', verbose_name='Orden aleatorio del intento')),
                ('exam', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='quizzes.themeexam', verbose_name='Examen')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exam_attempts', to=settings.AUTH_USER_MODEL, verbose_name='Estudiante')),
            ],
            options={
                'verbose_name': 'Intento de examen',
                'verbose_name_plural': 'Intentos de examen',
                'ordering': ['-started_at'],
                'unique_together': {('exam', 'student')},
            },
        ),
        migrations.CreateModel(
            name='ExamAttemptAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attempt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='quizzes.examattempt', verbose_name='Intento')),
                ('question', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempt_answers', to='quizzes.examquestion', verbose_name='Pregunta')),
                ('selected_option', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='attempt_selections', to='quizzes.examansweroption', verbose_name='Opción elegida')),
            ],
            options={
                'verbose_name': 'Respuesta del intento',
                'verbose_name_plural': 'Respuestas del intento',
                'unique_together': {('attempt', 'question')},
            },
        ),
    ]
