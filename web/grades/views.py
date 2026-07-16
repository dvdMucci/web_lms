from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from assignments.models import Assignment
from assignments.services import get_effective_submission, map_effective_submissions
from courses.models import Course, Enrollment
from courses.utils import can_view_course_as_teacher
from quizzes.models import ExamAttempt, ThemeExam

from .forms import AcademicSituationForm
from .models import AcademicSituation

User = get_user_model()

_EVAL_ORDER = (
    'tema__unit__order',
    'tema__unit_id',
    'tema__order',
    'tema_id',
)


def _short_title(title, max_len=22):
    text = (title or '').strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + '…'


def _cell_from_submission(submission):
    has_submission = submission is not None
    has_grade = bool(submission and submission.has_grade())
    return {
        'grade_display': submission.get_grade_display() if has_grade else None,
        'has_grade': has_grade,
        'has_submission': has_submission,
        'status': (
            'graded' if has_grade
            else 'submitted' if has_submission
            else 'missing'
        ),
    }


def _format_exam_score(score):
    if score is None:
        return None
    if score == score.to_integral_value():
        return str(int(score))
    return f'{score:.2f}'.rstrip('0').rstrip('.')


def _cell_from_attempt(attempt):
    has_submission = attempt is not None
    has_grade = attempt is not None and attempt.score is not None
    return {
        'grade_display': _format_exam_score(attempt.score) if has_grade else None,
        'has_grade': has_grade,
        'has_submission': has_submission,
        'status': (
            'graded' if has_grade
            else 'submitted' if has_submission
            else 'missing'
        ),
    }


def _empty_cell(status='missing'):
    return {
        'grade_display': None,
        'has_grade': False,
        'has_submission': False,
        'status': status,
    }


def _build_course_grade_matrix(course, students):
    """
    Build spreadsheet columns and per-student grade cells for published
    assignments and exams in the course.
    """
    student_list = list(students)
    student_ids = [s.id for s in student_list]

    assignments = list(
        Assignment.objects.filter(course=course, is_published=True)
        .select_related('tema', 'tema__unit')
        .prefetch_related('target_students')
        .order_by(*_EVAL_ORDER, 'due_date', 'created_at')
    )
    exams = list(
        ThemeExam.objects.filter(course=course, is_published=True)
        .select_related('tema', 'tema__unit')
        .order_by(*_EVAL_ORDER, 'available_from', 'created_at')
    )

    columns = []
    # Interleave by unit/tema order: build sortable tuples then merge
    column_items = []
    for assignment in assignments:
        unit = assignment.tema.unit if assignment.tema_id else None
        column_items.append((
            (
                unit.order if unit else 0,
                unit.id if unit else 0,
                assignment.tema.order if assignment.tema_id else 0,
                assignment.tema_id or 0,
                0,  # assignments before exams on same tema
                assignment.due_date.timestamp() if assignment.due_date else 0,
                assignment.id,
            ),
            {
                'key': f'a-{assignment.id}',
                'kind': 'assignment',
                'kind_label': 'Tarea',
                'title': assignment.title,
                'short_title': _short_title(assignment.title),
                'object': assignment,
            },
        ))
    for exam in exams:
        unit = exam.tema.unit if exam.tema_id else None
        column_items.append((
            (
                unit.order if unit else 0,
                unit.id if unit else 0,
                exam.tema.order if exam.tema_id else 0,
                exam.tema_id or 0,
                1,
                exam.available_from.timestamp() if exam.available_from else 0,
                exam.id,
            ),
            {
                'key': f'e-{exam.id}',
                'kind': 'exam',
                'kind_label': 'Examen',
                'title': exam.title,
                'short_title': _short_title(exam.title),
                'object': exam,
            },
        ))
    column_items.sort(key=lambda item: item[0])
    columns = [item[1] for item in column_items]

    # target_students: empty M2M => visible to all
    targeted_by_assignment = {}
    for assignment in assignments:
        targets = list(assignment.target_students.values_list('id', flat=True))
        targeted_by_assignment[assignment.id] = set(targets) if targets else None

    grades_by_student = {
        sid: {col['key']: _empty_cell() for col in columns}
        for sid in student_ids
    }

    for assignment in assignments:
        key = f'a-{assignment.id}'
        allowed = targeted_by_assignment[assignment.id]
        effective = map_effective_submissions(assignment, student_list)
        for student in student_list:
            sid = student.id
            if allowed is not None and sid not in allowed:
                grades_by_student[sid][key] = _empty_cell('na')
                continue
            entry = effective.get(sid) or {}
            grades_by_student[sid][key] = _cell_from_submission(entry.get('submission'))

    if exams and student_ids:
        attempts = ExamAttempt.objects.filter(
            exam__in=exams,
            student_id__in=student_ids,
            submitted_at__isnull=False,
        )
        attempt_map = {}
        for attempt in attempts:
            # keep one attempt per (exam, student); model is typically unique
            attempt_map[(attempt.exam_id, attempt.student_id)] = attempt
        for exam in exams:
            key = f'e-{exam.id}'
            for sid in student_ids:
                grades_by_student[sid][key] = _cell_from_attempt(
                    attempt_map.get((exam.id, sid))
                )

    return columns, grades_by_student


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
    students = [enrollment.student for enrollment in enrollments]
    situations = {
        s.student_id: s
        for s in AcademicSituation.objects.filter(course=course, year=year)
    }
    evaluation_columns, grades_by_student = _build_course_grade_matrix(course, students)

    rows = []
    for student in students:
        situation = situations.get(student.id) or _empty_situation(student)
        cells_map = grades_by_student.get(student.id, {})
        eval_cells = []
        for col in evaluation_columns:
            cell = dict(cells_map.get(col['key'], _empty_cell()))
            cell['title'] = f"{col['kind_label']}: {col['title']}"
            eval_cells.append(cell)
        rows.append({
            'student': student,
            'situation': situation,
            'missing_valuations': situation.missing_valuations_count(),
            'missing_grades': situation.missing_grades_count(),
            'is_complete': situation.is_complete() if situation.pk else False,
            'eval_cells': eval_cells,
        })

    return render(request, 'grades/academic_situation_list.html', {
        'course': course,
        'year': year,
        'rows': rows,
        'evaluation_columns': evaluation_columns,
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
