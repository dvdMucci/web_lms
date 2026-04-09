from django.contrib import admin
from django.contrib.auth.admin import UserAdmin # El UserAdmin base de Django
from .models import CustomUser, StudentRegistrationToken, UserActivityLog
from .forms import CustomUserCreationForm, CustomUserChangeForm

@admin.register(CustomUser) # Registra tu modelo CustomUser en el admin
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm # Formulario para crear usuarios desde el admin
    form = CustomUserChangeForm # Formulario para editar usuarios desde el admin
    model = CustomUser # El modelo asociado
    list_display = ['username', 'email', 'user_type', 'is_2fa_enabled', 'telegram_chat_id', 'is_active'] # Campos a mostrar en la lista
    list_filter = ['user_type', 'is_2fa_enabled', 'is_active', 'date_joined'] # Campos para filtrar
    fieldsets = UserAdmin.fieldsets + ( # Campos adicionales en el formulario de edición
        ('Información Adicional', {
            'fields': ('user_type', 'telegram_chat_id', 'is_2fa_enabled')
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + ( # Campos adicionales en el formulario de creación
        ('Información Adicional', {
            'fields': ('user_type', 'email')
        }),
    )


@admin.register(StudentRegistrationToken)
class StudentRegistrationTokenAdmin(admin.ModelAdmin):
    list_display = (
        'token',
        'created_by',
        'starts_at',
        'expires_at',
        'is_active',
        'uses_count',
        'max_uses',
    )
    list_filter = ('is_active', 'starts_at', 'expires_at')
    search_fields = ('token', 'description', 'created_by__username')
    readonly_fields = ('uses_count', 'cancelled_at', 'created_at', 'updated_at')


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'actor', 'target_username', 'target_user')
    list_filter = ('action', 'created_at')
    search_fields = ('target_username', 'details', 'actor__username', 'target_user__username')
    readonly_fields = ('created_at',)