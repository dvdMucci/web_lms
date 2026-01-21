from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.core.cache import cache
from .models import StorageConfig
from .services.storage import get_storage_usage, check_storage_threshold


@admin.register(StorageConfig)
class StorageConfigAdmin(admin.ModelAdmin):
    list_display = ['total_storage_gb', 'alert_threshold_percent', 'alert_email', 'alert_enabled', 'last_alert_sent']
    fieldsets = (
        ('Configuración de Almacenamiento', {
            'fields': ('total_storage_gb',)
        }),
        ('Configuración de Alertas', {
            'fields': ('alert_enabled', 'alert_threshold_percent', 'alert_email', 'last_alert_sent')
        }),
        ('Información', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    readonly_fields = ['last_alert_sent', 'created_at', 'updated_at']
    
    def has_add_permission(self, request):
        # Solo permitir agregar si no existe una configuración
        return not StorageConfig.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # No permitir eliminar la configuración
        return False
    
    def changelist_view(self, request, extra_context=None):
        # Mostrar la vista de uso en la lista
        extra_context = extra_context or {}
        usage = get_storage_usage()
        extra_context['storage_usage'] = usage
        return super().changelist_view(request, extra_context)
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'storage-usage/',
                self.admin_site.admin_view(self.storage_usage_view),
                name='core_storageconfig_storage_usage',
            ),
            path(
                'check-threshold/',
                self.admin_site.admin_view(self.check_threshold_view),
                name='core_storageconfig_check_threshold',
            ),
        ]
        return custom_urls + urls
    
    def storage_usage_view(self, request):
        """
        Vista personalizada que muestra el uso detallado del almacenamiento.
        """
        # Invalidar caché para obtener datos frescos
        cache.delete('storage_usage_stats')
        usage = get_storage_usage()
        config = StorageConfig.objects.first()
        
        context = {
            **self.admin_site.each_context(request),
            'title': 'Uso de Almacenamiento',
            'usage': usage,
            'config': config,
            'has_view_permission': request.user.has_perm('core.view_storageconfig'),
        }
        
        return TemplateResponse(request, 'admin/core/storageconfig/storage_usage.html', context)
    
    def check_threshold_view(self, request):
        """
        Vista para verificar manualmente el umbral y enviar alerta si es necesario.
        """
        if request.method == 'POST':
            # Invalidar caché
            cache.delete('storage_usage_stats')
            usage = get_storage_usage()
            config = StorageConfig.objects.first()
            
            if config and config.alert_enabled:
                alert_sent = check_storage_threshold()
                
                if alert_sent:
                    self.message_user(request, 'Alerta de almacenamiento enviada exitosamente.', level='success')
                else:
                    if usage['used_percent'] < config.alert_threshold_percent:
                        self.message_user(
                            request,
                            f'El uso actual ({usage["used_percent"]:.1f}%) está por debajo del umbral ({config.alert_threshold_percent}%).',
                            level='info'
                        )
                    else:
                        self.message_user(request, 'No se pudo enviar la alerta o ya se envió recientemente (espera 24 horas).', level='warning')
            else:
                self.message_user(request, 'Las alertas están deshabilitadas o no hay configuración.', level='warning')
            
            from django.shortcuts import redirect
            return redirect('admin:core_storageconfig_changelist')
        
        from django.shortcuts import redirect
        return redirect('admin:core_storageconfig_changelist')


# Agregar un enlace en el admin para acceder a la vista de uso
admin.site.site_header = "Marina Ojeda LMS - Administración"
admin.site.index_title = "Panel de Control"
