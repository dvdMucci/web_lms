from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from assignments.models import Assignment, AssignmentSubmission
from assignments.services import get_effective_submission
from courses.models import Course, Enrollment
from courses.utils import can_view_course_as_teacher
from quizzes.models import ExamAttempt, ThemeExam

from .forms import AcademicSituationForm
from .models import AcademicSituation

User = get_user_model()


def _user_can_edit(user, course):
    return (
        user.is_authenticated
        and (course.is_instructor_or_collaborator(user) or user.user_type == 'admin')
    )


def _user_can_view_all(user, course):
    return _user_can_edit(user, course) or can_view_course_as_teacher(user, course)


def _user_is_approved_student(user, course):
    return Enrollment.objects.filter(
        course=course,
        student=user,
        status='approved',
    ).exists()


def _parse_year(request):
    raw = request.GET.get('year', '').strip()
    current_year = timezone.localdate().year
    if not raw:
        return current_year
    try:
        year = int(raw)
    except ValueError:
        return current_year
    if year < 2000 or year > 2100:
        return current_year
    return year


def _get_approved_students(course):
    return (
        Enrollment.objects.filter(course=course, status='approved')
        .select_related('student')
        .order_by('student__last_name', 'student__first_name', 'student__username')
    )


def _empty_situation(student):
    return AcademicSituation(
        student=student,
        semester_1_valuation=None,
        semester_2_valuation=None,
        semester_1_grade=None,
        semester_2_grade=None,
        average_grade=None,
    )


def _build_evaluation_rows(course, student):
    """List published assignments and exams with current grade status for one student."""
    assignments = (
        Assignment.objects.filter(course=course, is_published=True)
        .annotate(target_count=Count('target_students'))
        .filter(Q(target_count=0) | Q(target_students=student))
        .distinct()
        .select_related('tema', 'tema__unit')
        .order_by(
            'tema__unit__order',
            'tema__unit_id',
            'tema__order',
            'tema_id',
            'due_date',
            'created_at',
        )
    )

    latest_by_assignment = {}
    for assignment in assignments:
        submission, is_collaborator = get_effective_submission(assignment, student)
        if submission is not None:
            latest_by_assignment[assignment.id] = {
                'submission': submission,
                'is_collaborator': is_collaborator,
            }

    rows = []
    pending_evaluations = 0

    for assignment in assignments:
        entry = latest_by_assignment.get(assignment.id)
        submission = entry['submission'] if entry else None
        is_collaborator = entry['is_collaborator'] if entry else False
        has_grade = bool(submission and submission.has_grade())
        if not has_grade:
            pending_evaluations += 1
        unit = assignment.tema.unit if assignment.tema_id else None
        rows.append({
            'kind': 'assignment',
            'kind_label': 'Tarea',
            'title': assignment.title,
            'unit': unit,
            'tema': assignment.tema,
            'grade_display': submission.get_grade_display() if has_grade else None,
            'has_grade': has_grade,
            'has_submission': submission is not None,
            'is_collaborator': is_collaborator,
            'object': assignment,
            'submission': submission,
        })

    exams = (
        ThemeExam.objects.filter(course=course, is_published=True)
        .select_related('tema', 'tema__unit')
        .order_by(
            'tema__unit__order',
            'tema__unit_id',
            'tema__order',
            'tema_id',
            'available_from',
            'created_at',
        )
    )
    attempts = {
        attempt.exam_id: attempt
        for attempt in ExamAttempt.objects.filter(
            exam__in=exams,
            student=student,
            submitted_at__isnull=False,
        )
    }

    for exam in exams:
        attempt = attempts.get(exam.id)
        has_grade = attempt is not None and attempt.score is not None
        if not has_grade:
            pending_evaluations += 1
        unit = exam.tema.unit if exam.tema_id else None
        rows.append({
            'kind': 'exam',
            'kind_label': 'Examen',
            'title': exam.title,
            'unit': unit,
            'tema': exam.tema,
            'grade_display': str(attempt.score) if has_grade else None,
            'has_grade': has_grade,
            'has_submission': attempt is not None,
            'object': exam,
            'submission': attempt,
        })

    return rows, pending_evaluations


@login_required
@require_http_methods(['GET'])
def academic_situation_list(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if not _user_can_view_all(request.user, course):
        messages.error(request, 'No tenés permiso para ver la situación académica de este curso.')
        return redirect('course_detail', course_id=course.id)

    year = _parse_year(request)
    enrollments = _get_approved_students(course)
    situations = {
        s.student_id: s
        for s in AcademicSituation.objects.filter(course=course, year=year)
    }

    rows = []
    for enrollment in enrollments:
        student = enrollment.student
        situation = situations.get(student.id) or _empty_situation(student)
        rows.append({
            'student': student,
            'situation': situation,
            'missing_valuations': situation.missing_valuations_count(),
            'missing_grades': situation.missing_grades_count(),
            'is_complete': situation.is_complete() if situation.pk else False,
        })

    return render(request, 'grades/academic_situation_list.html', {
        'course': course,
        'year': year,
        'rows': rows,
        'can_edit': _user_can_edit(request.user, course),
        'current_year': timezone.localdate().year,
    })


@login_required
@require_http_methods(['GET', 'POST'])
def academic_situation_student(request, course_id, student_id):
    course = get_object_or_404(Course, id=course_id)
    student = get_object_or_404(User, id=student_id, user_type='student')
    can_edit = _user_can_edit(request.user, course)
    can_view_all = _user_can_view_all(request.user, course)
    is_own = request.user.id == student.id and _user_is_approved_student(request.user, course)

    if not (can_view_all or is_own):
        messages.error(request, 'No tenés permiso para ver esta situación académica.')
        return redirect('course_detail', course_id=course.id)

    enrollment = Enrollment.objects.filter(
        course=course,
        student=student,
        status='approved',
    ).first()
    if not enrollment:
        messages.error(request, 'El alumno no está inscripto en este curso.')
        return redirect('course_detail', course_id=course.id)

    year = _parse_year(request)
    situation = AcademicSituation.objects.filter(
        course=course,
        student=student,
        year=year,
    ).first()
    if situation is None:
        situation = AcademicSituation(course=course, student=student, year=year)

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'No tenés permiso para editar la situación académica.')
            return redirect(
                'grades:academic_situation_student',
                course_id=course.id,
                student_id=student.id,
            )
        form = AcademicSituationForm(request.POST, instance=situation)
        if form.is_valid():
            record = form.save(commit=False)
            record.course = course
            record.student = student
            record.year = year
            record.updated_by = request.user
            record.save()
            messages.success(request, 'Situación académica guardada correctamente.')
            redirect_url = reverse(
                'grades:academic_situation_student',
                kwargs={'course_id': course.id, 'student_id': student.id},
            )
            return redirect(f'{redirect_url}?year={year}')
    else:
        form = AcademicSituationForm(instance=situation)

    evaluation_rows, pending_evaluations = _build_evaluation_rows(course, student)
    classmates = []
    if can_view_all:
        classmates = [
            e.student for e in _get_approved_students(course)
        ]

    return render(request, 'grades/academic_situation_student.html', {
        'course': course,
        'student': student,
        'year': year,
        'situation': situation,
        'form': form,
        'can_edit': can_edit,
        'evaluation_rows': evaluation_rows,
        'pending_evaluations': pending_evaluations,
        'missing_valuations': situation.missing_valuations_count(),
        'missing_grades': situation.missing_grades_count(),
        'classmates': classmates,
        'current_year': timezone.localdate().year,
    })


@login_required
@require_http_methods(['GET'])
def academic_situation_my(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    if not _user_is_approved_student(request.user, course):
        messages.error(request, 'Solo los alumnos inscriptos pueden ver su situación académica.')
        return redirect('course_detail', course_id=course.id)
    year = _parse_year(request)
    redirect_url = reverse(
        'grades:academic_situation_student',
        kwargs={'course_id': course.id, 'student_id': request.user.id},
    )
    return redirect(f'{redirect_url}?year={year}')
