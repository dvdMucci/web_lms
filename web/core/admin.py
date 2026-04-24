import os
from django.contrib import admin
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.html import format_html
from django.core.cache import cache
from django.conf import settings
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
            path(
                'orphaned-files/',
                self.admin_site.admin_view(self.orphaned_files_view),
                name='core_storageconfig_orphaned_files',
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

    def _get_used_file_paths(self):
        """Devuelve el conjunto de rutas relativas a MEDIA_ROOT de todos los archivos en uso."""
        from materials.models import Material
        from assignments.models import AssignmentSubmission, AssignmentSubmissionFile

        used = set()
        for name in Material.objects.exclude(file='').exclude(file=None).values_list('file', flat=True):
            if name:
                used.add(name)
        for name in AssignmentSubmission.objects.exclude(file='').exclude(file=None).values_list('file', flat=True):
            if name:
                used.add(name)
        for name in AssignmentSubmissionFile.objects.exclude(file='').exclude(file=None).values_list('file', flat=True):
            if name:
                used.add(name)
        return used

    def _scan_media_files(self):
        """Escanea MEDIA_ROOT y devuelve lista de rutas relativas de todos los archivos."""
        media_root = settings.MEDIA_ROOT
        result = []
        if not os.path.isdir(media_root):
            return result
        for dirpath, _dirnames, filenames in os.walk(media_root):
            for filename in filenames:
                abs_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(abs_path, media_root)
                result.append(rel_path)
        return result

    def orphaned_files_view(self, request):
        """Vista para detectar y eliminar archivos huérfanos del storage."""
        from django.contrib import messages as dj_messages

        deleted_count = 0
        deleted_size = 0
        errors = []

        if request.method == 'POST':
            files_to_delete = request.POST.getlist('files_to_delete')
            # Doble validación: re-chequear que siguen siendo huérfanos
            used = self._get_used_file_paths()
            media_root = settings.MEDIA_ROOT
            for rel_path in files_to_delete:
                # Normalizar path para evitar traversal
                safe_path = os.path.normpath(rel_path)
                if safe_path.startswith('..') or os.path.isabs(safe_path):
                    errors.append(f'Ruta inválida ignorada: {rel_path}')
                    continue
                if safe_path in used:
                    errors.append(f'Archivo en uso (no se eliminó): {rel_path}')
                    continue
                abs_path = os.path.join(media_root, safe_path)
                if not os.path.isfile(abs_path):
                    continue
                try:
                    size = os.path.getsize(abs_path)
                    os.remove(abs_path)
                    deleted_count += 1
                    deleted_size += size
                except Exception as e:
                    errors.append(f'Error al eliminar {rel_path}: {e}')

            if deleted_count:
                mb = deleted_size / (1024 * 1024)
                dj_messages.success(request, f'Se eliminaron {deleted_count} archivos ({mb:.2f} MB liberados).')
            if errors:
                for err in errors:
                    dj_messages.warning(request, err)

            from django.shortcuts import redirect
            return redirect('admin:core_storageconfig_orphaned_files')

        # GET: escanear y calcular huérfanos
        used = self._get_used_file_paths()
        all_files = self._scan_media_files()
        media_root = settings.MEDIA_ROOT

        orphans = []
        for rel_path in all_files:
            if rel_path not in used:
                abs_path = os.path.join(media_root, rel_path)
                try:
                    size = os.path.getsize(abs_path)
                    mtime = os.path.getmtime(abs_path)
                    import datetime
                    orphans.append({
                        'path': rel_path,
                        'size_kb': round(size / 1024, 1),
                        'modified': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M'),
                    })
                except OSError:
                    pass

        total_orphan_size = sum(o['size_kb'] for o in orphans)

        context = {
            **self.admin_site.each_context(request),
            'title': 'Archivos Huérfanos del Storage',
            'orphans': orphans,
            'total_orphan_size_kb': round(total_orphan_size, 1),
            'total_orphan_size_mb': round(total_orphan_size / 1024, 2),
        }
        return TemplateResponse(request, 'admin/core/storageconfig/orphaned_files.html', context)


# Agregar un enlace en el admin para acceder a la vista de uso
admin.site.site_header = "Marina Ojeda LMS - Administración"
admin.site.index_title = "Panel de Control"
