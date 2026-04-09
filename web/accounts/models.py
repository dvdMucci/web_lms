import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

class CustomUser(AbstractUser):
    USER_TYPES = [
        ('student', 'Estudiante'),
        ('teacher', 'Profesor'),
        ('admin', 'Administrador'),
    ]
    
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPES,
        default='student',
        verbose_name='Tipo de Usuario'
    )
    
    telegram_chat_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Chat ID de Telegram'
    )
    
    is_2fa_enabled = models.BooleanField(
        default=False,
        verbose_name='2FA Habilitado'
    )

    email_verified_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Email verificado el'
    )
    email_verification_sent_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Ultimo envio de verificacion'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- ADD THESE RELATED_NAME ARGUMENTS ---
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='customuser_set', # Unique related_name for CustomUser groups
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='customuser_permissions_set', # Unique related_name for CustomUser permissions
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )
    # ----------------------------------------
    
    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
    
    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"
    
    def can_manage_users(self):
        return self.user_type == 'admin'

    def is_teacher(self):
        return self.user_type == 'teacher'

    def is_student(self):
        return self.user_type == 'student'

    def is_email_verified(self):
        return bool(self.email_verified_at)


class StudentRegistrationToken(models.Model):
    token = models.CharField(max_length=64, unique=True, db_index=True)
    created_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_registration_tokens',
    )
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses_count = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Token de registro de alumnos'
        verbose_name_plural = 'Tokens de registro de alumnos'
        ordering = ['-created_at']

    def __str__(self):
        return f"Token {self.token[:8]}... ({self.uses_count} usos)"

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(24)

    def is_valid_now(self):
        now = timezone.now()
        return (
            self.is_active
            and self.cancelled_at is None
            and self.starts_at <= now <= self.expires_at
        )

    def can_consume(self):
        if not self.is_valid_now():
            return False
        if self.max_uses is None:
            return True
        return self.uses_count < self.max_uses

    def consume(self):
        if not self.can_consume():
            return False
        self.uses_count = self.uses_count + 1
        self.save(update_fields=['uses_count', 'updated_at'])
        return True

    def cancel(self):
        if not self.is_active and self.cancelled_at:
            return
        self.is_active = False
        self.cancelled_at = timezone.now()
        self.save(update_fields=['is_active', 'cancelled_at', 'updated_at'])


class UserActivityLog(models.Model):
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_USER_CREATED = 'user_created'
    ACTION_USER_UPDATED = 'user_updated'
    ACTION_USER_DELETED = 'user_deleted'
    ACTION_COURSE_CREATED = 'course_created'
    ACTION_COURSE_UPDATED = 'course_updated'
    ACTION_COURSE_DELETED = 'course_deleted'
    ACTION_ENROLLMENT_APPROVED = 'enrollment_approved'
    ACTION_ENROLLMENT_REJECTED = 'enrollment_rejected'
    ACTION_ENROLLMENT_CANCELLED = 'enrollment_cancelled'
    ACTION_ASSIGNMENT_CREATED = 'assignment_created'
    ACTION_ASSIGNMENT_UPDATED = 'assignment_updated'
    ACTION_ASSIGNMENT_DELETED = 'assignment_deleted'
    ACTION_SUBMISSION_UPLOADED = 'submission_uploaded'
    ACTION_SUBMISSION_VIEWED = 'submission_viewed'
    ACTION_SUBMISSION_DOWNLOADED = 'submission_downloaded'
    ACTION_MATERIAL_UPLOADED = 'material_uploaded'
    ACTION_MATERIAL_UPDATED = 'material_updated'
    ACTION_MATERIAL_DELETED = 'material_deleted'
    ACTION_MATERIAL_DOWNLOADED = 'material_downloaded'

    ACTION_CHOICES = [
        (ACTION_LOGIN, 'Inicio de sesión'),
        (ACTION_LOGOUT, 'Cierre de sesión'),
        (ACTION_USER_CREATED, 'Usuario creado'),
        (ACTION_USER_UPDATED, 'Usuario actualizado'),
        (ACTION_USER_DELETED, 'Usuario eliminado'),
        (ACTION_COURSE_CREATED, 'Curso creado'),
        (ACTION_COURSE_UPDATED, 'Curso actualizado'),
        (ACTION_COURSE_DELETED, 'Curso eliminado'),
        (ACTION_ENROLLMENT_APPROVED, 'Inscripción aprobada'),
        (ACTION_ENROLLMENT_REJECTED, 'Inscripción rechazada'),
        (ACTION_ENROLLMENT_CANCELLED, 'Inscripción cancelada'),
        (ACTION_ASSIGNMENT_CREATED, 'Tarea creada'),
        (ACTION_ASSIGNMENT_UPDATED, 'Tarea actualizada'),
        (ACTION_ASSIGNMENT_DELETED, 'Tarea eliminada'),
        (ACTION_SUBMISSION_UPLOADED, 'Entrega subida'),
        (ACTION_SUBMISSION_VIEWED, 'Entrega visualizada'),
        (ACTION_SUBMISSION_DOWNLOADED, 'Entrega descargada'),
        (ACTION_MATERIAL_UPLOADED, 'Material subido'),
        (ACTION_MATERIAL_UPDATED, 'Material actualizado'),
        (ACTION_MATERIAL_DELETED, 'Material eliminado'),
        (ACTION_MATERIAL_DOWNLOADED, 'Material descargado'),
    ]

    actor = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs_made',
    )
    target_user = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs_received',
    )
    target_username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    details = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Registro de actividad de usuario'
        verbose_name_plural = 'Registros de actividad de usuario'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_display()} - {self.target_username or '-'}"