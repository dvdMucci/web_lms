from django.db import models
from django.conf import settings
from courses.models import Course, Enrollment


class ForumPost(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='forum_posts',
        verbose_name='Curso',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='forum_posts',
        verbose_name='Autor',
    )
    title = models.CharField(max_length=200, verbose_name='Título')
    content = models.TextField(verbose_name='Contenido')
    is_private = models.BooleanField(
        default=False,
        verbose_name='Privado',
        help_text='Solo visible para el alumno participante y docentes del curso.',
    )
    # For private posts: the student involved (set automatically for student authors,
    # or selected by teacher when they initiate a private thread).
    student_participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='private_forum_posts',
        verbose_name='Alumno participante',
    )
    is_pinned = models.BooleanField(default=False, verbose_name='Fijado')
    is_locked = models.BooleanField(default=False, verbose_name='Bloqueado')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')
    # Tracks when new activity (post creation or new reply) last happened.
    last_activity_at = models.DateTimeField(auto_now_add=True, verbose_name='Última actividad')

    class Meta:
        verbose_name = 'Publicación del Foro'
        verbose_name_plural = 'Publicaciones del Foro'
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.course.title} — {self.title}"

    def can_view(self, user):
        if user.user_type == 'admin':
            return True
        if self.course.is_instructor_or_collaborator(user):
            return True
        is_enrolled = Enrollment.objects.filter(
            student=user, course=self.course, status='approved'
        ).exists()
        if not is_enrolled:
            return False
        if not self.is_private:
            return True
        return self.student_participant_id == user.pk

    def can_reply(self, user):
        return self.can_view(user) and not self.is_locked

    def can_edit(self, user):
        return (
            self.author_id == user.pk
            or self.course.is_instructor_or_collaborator(user)
            or user.user_type == 'admin'
        )

    def can_pin(self, user):
        return self.course.is_instructor_or_collaborator(user) or user.user_type == 'admin'

    @property
    def replies_count(self):
        return self.replies.count()

    @property
    def last_reply(self):
        return self.replies.order_by('-created_at').first()


class ForumPostRead(models.Model):
    """Tracks when a user last read a forum post (for unread indicators)."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='forum_reads',
        verbose_name='Usuario',
    )
    post = models.ForeignKey(
        ForumPost,
        on_delete=models.CASCADE,
        related_name='reads',
        verbose_name='Publicación',
    )
    last_read_at = models.DateTimeField(auto_now=True, verbose_name='Última lectura')

    class Meta:
        verbose_name = 'Lectura de Publicación'
        verbose_name_plural = 'Lecturas de Publicaciones'
        unique_together = ['user', 'post']

    def __str__(self):
        return f"{self.user.username} leyó '{self.post.title}'"


class ForumReply(models.Model):
    post = models.ForeignKey(
        ForumPost,
        on_delete=models.CASCADE,
        related_name='replies',
        verbose_name='Publicación',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='forum_replies',
        verbose_name='Autor',
    )
    content = models.TextField(verbose_name='Contenido')
    parent_reply = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='nested_replies',
        verbose_name='Respuesta padre',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Creado en')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Actualizado en')

    class Meta:
        verbose_name = 'Respuesta del Foro'
        verbose_name_plural = 'Respuestas del Foro'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author.username} en '{self.post.title}'"

    def can_delete(self, user):
        return (
            self.author_id == user.pk
            or self.post.course.is_instructor_or_collaborator(user)
            or user.user_type == 'admin'
        )
