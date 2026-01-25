"""
Management command para publicar automáticamente materiales y tareas programados.
Este comando debe ejecutarse periódicamente (por ejemplo, cada minuto) usando cron o un scheduler.
Usa la zona horaria de Django (TIME_ZONE, p. ej. America/Argentina/Buenos_Aires).
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from materials.models import Material
from assignments.models import Assignment
from core.notifications import notify_material_published, notify_assignment_published
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Publica automáticamente materiales y tareas que tienen una fecha de publicación programada y ya han llegado'

    def handle(self, *args, **options):
        # now en UTC (Django USE_TZ). La BD guarda fechas en UTC; la comparación es correcta.
        now = timezone.now()
        # Hora local para el log (Argentina u la TIME_ZONE de settings)
        local_now = timezone.localtime(now)

        tz_name = getattr(settings, 'TIME_ZONE', 'UTC')
        self.stdout.write(
            self.style.NOTICE(f'[{local_now.strftime("%Y-%m-%d %H:%M:%S")} {tz_name}] Revisando publicaciones programadas...')
        )

        published_materials = 0
        published_assignments = 0
        emails_sent = 0

        # Publicar materiales programados
        materials_to_publish = Material.objects.filter(
            scheduled_publish_at__lte=now,
            is_published=False
        ).select_related('course', 'unit', 'uploaded_by')
        
        for material in materials_to_publish:
            try:
                material.is_published = True
                material.save(update_fields=['is_published'])
                published_materials += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Material "{material.title}" publicado exitosamente.'
                    )
                )
                
                # Enviar notificaciones si está configurado
                if material.send_notification_email:
                    try:
                        sent = notify_material_published(material)
                        emails_sent += sent
                        if sent > 0:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  → Enviados {sent} correos de notificación para el material "{material.title}"'
                                )
                            )
                    except Exception as e:
                        logger.error(f'Error al enviar notificaciones para material {material.id}: {e}')
                        self.stdout.write(
                            self.style.WARNING(
                                f'  → Error al enviar notificaciones para el material "{material.title}": {e}'
                            )
                        )
                
            except Exception as e:
                logger.error(f'Error al publicar material {material.id}: {e}')
                self.stdout.write(
                    self.style.ERROR(
                        f'Error al publicar material "{material.title}": {e}'
                    )
                )
        
        # Publicar tareas programadas
        assignments_to_publish = Assignment.objects.filter(
            scheduled_publish_at__lte=now,
            is_published=False
        ).select_related('course', 'unit', 'created_by')
        
        for assignment in assignments_to_publish:
            try:
                assignment.is_published = True
                assignment.save(update_fields=['is_published'])
                published_assignments += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Tarea "{assignment.title}" publicada exitosamente.'
                    )
                )
                
                # Enviar notificaciones si está configurado
                if assignment.send_notification_email:
                    try:
                        sent = notify_assignment_published(assignment)
                        emails_sent += sent
                        if sent > 0:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  → Enviados {sent} correos de notificación para la tarea "{assignment.title}"'
                                )
                            )
                    except Exception as e:
                        logger.error(f'Error al enviar notificaciones para tarea {assignment.id}: {e}')
                        self.stdout.write(
                            self.style.WARNING(
                                f'  → Error al enviar notificaciones para la tarea "{assignment.title}": {e}'
                            )
                        )
                
            except Exception as e:
                logger.error(f'Error al publicar tarea {assignment.id}: {e}')
                self.stdout.write(
                    self.style.ERROR(
                        f'Error al publicar tarea "{assignment.title}": {e}'
                    )
                )
        
        # Resumen
        total_published = published_materials + published_assignments
        if total_published > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Publicados {published_materials} materiales y {published_assignments} tareas.'
                )
            )
            if emails_sent > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Enviados {emails_sent} correos de notificación.'
                    )
                )
        else:
            self.stdout.write(
                self.style.SUCCESS('No hay contenido programado para publicar en este momento.')
            )
