from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from courses.models import Course, Enrollment
from quizzes.models import ExamAnswerOption, ExamAttempt, ExamQuestion, ThemeExam
from quizzes.utils import copy_exam_questions, resolve_student_exam_access, student_needs_recuperatorio
from units.models import Tema, Unit

User = get_user_model()


class RecuperatorioAccessTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='teacher_rec',
            password='Pass1234!',
            user_type='teacher',
            email='teacher-rec@example.com',
        )
        self.course = Course.objects.create(
            title='Curso rec',
            description='Desc',
            instructor=self.teacher,
            is_active=True,
            is_paused=False,
        )
        self.unit = Unit.objects.create(
            title='Unidad',
            course=self.course,
            created_by=self.teacher,
            is_paused=False,
            order=1,
        )
        self.tema = Tema.objects.create(
            title='Tema',
            description='Desc',
            unit=self.unit,
            created_by=self.teacher,
            is_paused=False,
            order=1,
        )
        now = timezone.now()
        self.exam = ThemeExam.objects.create(
            title='Parcial',
            description='',
            tema=self.tema,
            course=self.course,
            created_by=self.teacher,
            is_published=True,
            available_from=now - timedelta(days=2),
            available_until=now + timedelta(days=2),
        )
        question = ExamQuestion.objects.create(exam=self.exam, text='¿Pregunta?', order=0)
        ExamAnswerOption.objects.create(question=question, text='A', is_correct=True)
        ExamAnswerOption.objects.create(question=question, text='B', is_correct=False)
        ExamAnswerOption.objects.create(question=question, text='C', is_correct=False)
        self.recuperatorio = ThemeExam.objects.create(
            title='Recuperatorio: Parcial',
            description='',
            tema=self.tema,
            course=self.course,
            created_by=self.teacher,
            is_published=True,
            available_from=now - timedelta(hours=1),
            available_until=now + timedelta(days=7),
            recuperatorio_of=self.exam,
        )
        copy_exam_questions(self.exam, self.recuperatorio)

    def _student(self, username):
        student = User.objects.create_user(
            username=username,
            password='Pass1234!',
            user_type='student',
            email=f'{username}@example.com',
        )
        Enrollment.objects.create(student=student, course=self.course, status='approved')
        return student

    def _submit(self, student, score):
        ExamAttempt.objects.create(
            exam=self.exam,
            student=student,
            submitted_at=timezone.now(),
            score=score,
            correct_count=1,
            total_questions=1,
        )

    def test_sin_entrega_puede_rendir(self):
        student = self._student('sin_entrega')
        self.assertTrue(student_needs_recuperatorio(student, self.exam))
        ok, message = resolve_student_exam_access(
            student, self.course, self.tema, self.recuperatorio
        )
        self.assertTrue(ok, message)

    def test_nota_menor_a_7_puede_rendir(self):
        student = self._student('nota_baja')
        self._submit(student, Decimal('6.99'))
        ok, message = resolve_student_exam_access(
            student, self.course, self.tema, self.recuperatorio
        )
        self.assertTrue(ok, message)

    def test_aprobado_no_puede_rendir(self):
        student = self._student('aprobado')
        self._submit(student, Decimal('7.00'))
        self.assertFalse(student_needs_recuperatorio(student, self.exam))
        ok, message = resolve_student_exam_access(
            student, self.course, self.tema, self.recuperatorio
        )
        self.assertFalse(ok)
        self.assertIn('menor a 7', message)

    def test_copia_preguntas(self):
        self.assertEqual(self.recuperatorio.questions.count(), 1)
        copied = self.recuperatorio.questions.get()
        self.assertEqual(copied.answer_options.count(), 3)
        self.assertEqual(copied.answer_options.filter(is_correct=True).count(), 1)
