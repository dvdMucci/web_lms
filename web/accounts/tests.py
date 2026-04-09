from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import StudentRegistrationToken
from assignments.models import Assignment, AssignmentSubmission
from core import notifications
from courses.models import Course, Enrollment
from units.models import Unit, Tema


User = get_user_model()


class RegistrationTokenFlowTests(TestCase):
    def test_register_with_valid_token_creates_student_without_email(self):
        token = StudentRegistrationToken.objects.create(
            token=StudentRegistrationToken.generate_token(),
            starts_at=timezone.now() - timedelta(minutes=5),
            expires_at=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        response = self.client.post(
            reverse('register_with_token', kwargs={'token': token.token}),
            data={
                'username': 'alumno_token',
                'first_name': 'Alu',
                'last_name': 'Token',
                'password1': 'S3guraPass!123',
                'password2': 'S3guraPass!123',
            },
        )
        self.assertRedirects(response, reverse('login'))
        student = User.objects.get(username='alumno_token')
        token.refresh_from_db()
        self.assertEqual(student.user_type, 'student')
        self.assertEqual(student.email, '')
        self.assertEqual(token.uses_count, 1)

    def test_register_with_expired_token_is_rejected(self):
        token = StudentRegistrationToken.objects.create(
            token=StudentRegistrationToken.generate_token(),
            starts_at=timezone.now() - timedelta(days=2),
            expires_at=timezone.now() - timedelta(days=1),
            is_active=True,
        )
        response = self.client.get(reverse('register_with_token', kwargs={'token': token.token}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registro no disponible')


class NotificationsPolicyTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='docente',
            password='Pass1234!',
            user_type='teacher',
            email='docente@example.com',
        )
        self.student = User.objects.create_user(
            username='alumno',
            password='Pass1234!',
            user_type='student',
            email='alumno@example.com',
            email_verified_at=None,
        )
        self.course = Course.objects.create(
            title='Curso 1',
            description='Desc',
            instructor=self.teacher,
            enrollment_open=True,
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            status='pending',
        )

    def test_no_email_sent_when_student_email_not_verified(self):
        sent = notifications.notify_enrollment_created(self.enrollment)
        self.assertFalse(sent)


class StudentDashboardPendingAssignmentsTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='doc_dash',
            password='Pass1234!',
            user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='alu_dash',
            password='Pass1234!',
            user_type='student',
        )
        self.course = Course.objects.create(
            title='Curso Dashboard',
            description='Desc',
            instructor=self.teacher,
            enrollment_open=True,
            is_active=True,
            is_paused=False,
        )
        Enrollment.objects.create(student=self.student, course=self.course, status='approved')
        self.unit = Unit.objects.create(
            title='Unidad 1',
            course=self.course,
            created_by=self.teacher,
            is_paused=False,
            order=1,
        )
        self.tema = Tema.objects.create(
            title='Tema 1',
            description='Desc',
            unit=self.unit,
            created_by=self.teacher,
            is_paused=False,
            order=1,
        )
        self.pending_assignment = Assignment.objects.create(
            title='Tarea pendiente',
            description='Pendiente',
            tema=self.tema,
            course=self.course,
            created_by=self.teacher,
            due_date=timezone.now() + timedelta(days=2),
            is_active=True,
            is_published=True,
        )
        self.done_assignment = Assignment.objects.create(
            title='Tarea entregada',
            description='Entregada',
            tema=self.tema,
            course=self.course,
            created_by=self.teacher,
            due_date=timezone.now() + timedelta(days=3),
            is_active=True,
            is_published=True,
        )
        AssignmentSubmission.objects.create(
            assignment=self.done_assignment,
            student=self.student,
            version=1,
            file='assignments/submissions/dummy.txt',
            status='submitted',
        )

    def test_dashboard_shows_only_pending_assignments(self):
        self.client.login(username='alu_dash', password='Pass1234!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        pending_assignments = list(response.context['pending_assignments'])
        self.assertEqual(len(pending_assignments), 1)
        self.assertEqual(pending_assignments[0].id, self.pending_assignment.id)
