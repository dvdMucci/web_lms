from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from assignments.models import Assignment
from core.notifications import notify_assignment_published
from courses.models import Course, Enrollment
from units.models import Unit, Tema


User = get_user_model()


class AssignmentNotificationPolicyTests(TestCase):
    def test_assignment_notification_skips_students_without_verified_email(self):
        teacher = User.objects.create_user(
            username='teacher_ntf',
            password='Pass1234!',
            user_type='teacher',
            email='teacher@example.com',
        )
        student = User.objects.create_user(
            username='student_ntf',
            password='Pass1234!',
            user_type='student',
            email='student@example.com',
            email_verified_at=None,
        )
        course = Course.objects.create(
            title='Curso Notif',
            description='Desc',
            instructor=teacher,
            is_active=True,
            is_paused=False,
        )
        Enrollment.objects.create(student=student, course=course, status='approved')
        unit = Unit.objects.create(
            title='Unidad',
            course=course,
            created_by=teacher,
            is_paused=False,
            order=1,
        )
        tema = Tema.objects.create(
            title='Tema',
            description='Desc',
            unit=unit,
            created_by=teacher,
            is_paused=False,
            order=1,
        )
        assignment = Assignment.objects.create(
            title='Tarea 1',
            description='Desc',
            tema=tema,
            course=course,
            created_by=teacher,
            due_date=timezone.now() + timedelta(days=1),
            is_active=True,
            is_published=True,
        )
        sent_count = notify_assignment_published(assignment)
        self.assertEqual(sent_count, 0)
