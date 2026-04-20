"""
Archivos en assignments/submissions/ que ya no están referenciados en la BD.

Uso:
  python manage.py find_orphan_submission_files
  python manage.py find_orphan_submission_files --delete
  python manage.py find_orphan_submission_files --delete --noinput
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from assignments.models import AssignmentSubmission, AssignmentSubmissionFile


SUBDIR = Path('assignments') / 'submissions'


class Command(BaseCommand):
    help = (
        'Lista archivos bajo MEDIA_ROOT/assignments/submissions/ que no tienen '
        'fila en AssignmentSubmissionFile ni en AssignmentSubmission.file (huérfanos).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help='Eliminar del disco los archivos huérfanos listados.',
        )
        parser.add_argument(
            '--noinput',
            action='store_true',
            help='Con --delete, no pedir confirmación.',
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        target = media_root / SUBDIR

        referenced = self._referenced_paths()

        if not target.is_dir():
            self.stdout.write(
                self.style.WARNING(
                    f'No existe el directorio {target}. MEDIA_ROOT={media_root}'
                )
            )
            return

        on_disk = set()
        for path in target.rglob('*'):
            if path.is_file():
                rel = path.relative_to(media_root).as_posix()
                on_disk.add(rel)

        orphans = sorted(on_disk - referenced)

        self.stdout.write(
            f'Referenciados en BD: {len(referenced)} | Archivos en disco: {len(on_disk)}'
        )
        if not orphans:
            self.stdout.write(self.style.SUCCESS('No hay archivos huérfanos.'))
            return

        self.stdout.write(self.style.WARNING(f'Huérfanos encontrados: {len(orphans)}'))
        for rel in orphans:
            self.stdout.write(f'  {rel}')

        if not options['delete']:
            self.stdout.write(
                '\nPara borrarlos, ejecutá de nuevo con --delete (y --noinput en scripts).'
            )
            return

        if not options['noinput']:
            confirm = input(f'\n¿Eliminar {len(orphans)} archivo(s)? [s/N]: ')
            if confirm.lower() not in ('s', 'si', 'sí', 'y', 'yes'):
                self.stdout.write('Cancelado.')
                return

        deleted = 0
        errors = 0
        for rel in orphans:
            abs_path = media_root / rel
            try:
                abs_path.unlink()
                deleted += 1
            except OSError as e:
                self.stdout.write(self.style.ERROR(f'Error borrando {rel}: {e}'))
                errors += 1

        self.stdout.write(self.style.SUCCESS(f'Eliminados: {deleted} | Errores: {errors}'))

    def _referenced_paths(self):
        """Rutas relativas a MEDIA_ROOT tal como las guarda Django FileField."""
        s = set()
        for name in AssignmentSubmissionFile.objects.exclude(file='').values_list(
            'file', flat=True
        ):
            if name:
                s.add(str(name).replace('\\', '/'))
        for name in AssignmentSubmission.objects.exclude(file='').exclude(
            file__isnull=True
        ).values_list('file', flat=True):
            if name:
                s.add(str(name).replace('\\', '/'))
        return s
