import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from courses.models import Course, Enrollment
from units.models import Unit, Tema

from .forms import ExamImportForm, ExamQuestionWithOptionsForm, ThemeExamForm
from .models import ExamAttempt, ExamAttemptAnswer, ExamQuestion, ThemeExam
from .services.excel_quiz import (
    build_template_workbook,
    export_exam_to_workbook,
    import_questions_for_exam,
    parse_excel_rows,
    workbook_to_response,
)
from .utils import (
    DONT_KNOW_POST_VALUE,
    DONT_KNOW_SHUFFLE_TOKEN,
    build_exam_attempt_review_rows,
    ensure_attempt_shuffle_and_answers,
    exam_has_submitted_attempts,
    resolve_student_exam_access,
)

logger = logging.getLogger(__name__)


def _course_unit_tema(course_id, unit_id, tema_id):
    course = get_object_or_404(Course, pk=course_id)
    unit = get_object_or_404(Unit, pk=unit_id, course=course)
    tema = get_object_or_404(Tema, pk=tema_id, unit=unit)
    return course, unit, tema


def _user_manages_course(user, course):
    return (
        course.instructor_id == user.id
        or course.collaborators.filter(pk=user.pk).exists()
        or getattr(user, 'user_type', '') == 'admin'
    )


def _student_enrolled_approved(user, course):
    return Enrollment.objects.filter(
        student=user,
        course=course,
        status='approved',
    ).exists()


def _get_exam(course_id, unit_id, tema_id, exam_id):
    course, unit, tema = _course_unit_tema(course_id, unit_id, tema_id)
    exam = get_object_or_404(ThemeExam, pk=exam_id, tema=tema, course=course)
    return course, unit, tema, exam


# --- Docente ---


@login_required
def exam_list(request, course_id, unit_id, tema_id):
    course, unit, tema = _course_unit_tema(course_id, unit_id, tema_id)
    if not _user_manages_course(request.user, course):
        messages.error(request, 'No tenés permiso para gestionar exámenes en este curso.')
        return redirect('course_detail', course_id=course_id)

    exams = ThemeExam.objects.filter(tema=tema).order_by('available_from', 'pk')
    return render(
        request,
        'quizzes/exam_list.html',
        {
            'course': course,
            'unit': unit,
            'tema': tema,
            'exams': exams,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def exam_create(request, course_id, unit_id, tema_id):
    course, unit, tema = _course_unit_tema(course_id, unit_id, tema_id)
    if not _user_manages_course(request.user, course):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)

    if request.method == 'POST':
        form = ThemeExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.tema = tema
            exam.course = course
            exam.created_by = request.user
            try:
                exam.save()
            except ValidationError as e:
                if getattr(e, 'error_dict', None):
                    for field, errors in e.error_dict.items():
                        for err in errors:
                            form.add_error(field if field != '__all__' else None, err)
                else:
                    for msg in e.messages:
                        form.add_error(None, msg)
            except DatabaseError as e:
                logger.exception('Error de base al crear ThemeExam')
                form.add_error(
                    None,
                    'No se pudo guardar el examen en la base de datos. '
                    'Si acabás de actualizar el sistema, ejecutá `python manage.py migrate` '
                    'en el entorno donde corre Django (p. ej. dentro del contenedor `web`). '
                    f'Detalle técnico: {e.__class__.__name__}',
                )
            else:
                messages.success(
                    request,
                    f'Examen «{exam.title}» creado. Agregá preguntas antes de publicar.',
                )
                return redirect(
                    'quizzes:exam_manage',
                    course_id=course_id,
                    unit_id=unit_id,
                    tema_id=tema_id,
                    exam_id=exam.pk,
                )
    else:
        form = ThemeExamForm()
    return render(
        request,
        'quizzes/exam_form.html',
        {
            'form': form,
            'course': course,
            'unit': unit,
            'tema': tema,
            'title': 'Nuevo examen',
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def exam_edit(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)

    if request.method == 'POST':
        form = ThemeExamForm(request.POST, instance=exam)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as e:
                if getattr(e, 'error_dict', None):
                    for field, errors in e.error_dict.items():
                        for err in errors:
                            form.add_error(field if field != '__all__' else None, err)
                else:
                    for msg in e.messages:
                        form.add_error(None, msg)
            except DatabaseError as e:
                logger.exception('Error de base al actualizar ThemeExam')
                form.add_error(
                    None,
                    'No se pudo guardar en la base de datos. Verificá que se ejecutó '
                    '`python manage.py migrate` en el contenedor/servidor. '
                    f'Detalle: {e.__class__.__name__}',
                )
            else:
                messages.success(request, 'Examen actualizado.')
                return redirect(
                    'quizzes:exam_manage',
                    course_id=course_id,
                    unit_id=unit_id,
                    tema_id=tema_id,
                    exam_id=exam.pk,
                )
    else:
        form = ThemeExamForm(instance=exam)
    return render(
        request,
        'quizzes/exam_form.html',
        {
            'form': form,
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'title': 'Editar examen',
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def exam_delete(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)

    if request.method == 'POST':
        title = exam.title
        exam.delete()
        messages.success(request, f'Examen «{title}» eliminado.')
        return redirect(
            'quizzes:exam_list',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
        )
    return render(
        request,
        'quizzes/exam_delete_confirm.html',
        {'course': course, 'unit': unit, 'tema': tema, 'exam': exam},
    )


@login_required
def exam_manage(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)

    locked = exam_has_submitted_attempts(exam)
    questions = exam.questions.prefetch_related('answer_options').order_by('order', 'id')
    attempts = (
        exam.attempts.filter(submitted_at__isnull=False)
        .select_related('student')
        .order_by('-submitted_at')
    )
    User = get_user_model()
    submitted_student_ids = exam.attempts.filter(
        submitted_at__isnull=False,
    ).values_list('student_id', flat=True)
    pending_students = (
        User.objects.filter(
            enrollments__course=course,
            enrollments__status='approved',
        )
        .exclude(pk__in=submitted_student_ids)
        .order_by('last_name', 'first_name', 'username')
        .distinct()
    )
    return render(
        request,
        'quizzes/exam_manage.html',
        {
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'questions': questions,
            'locked': locked,
            'attempts': attempts,
            'pending_students': pending_students,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def question_create(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)
    if exam_has_submitted_attempts(exam):
        messages.error(request, 'No se pueden agregar preguntas: ya hay entregas de alumnos.')
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    if request.method == 'POST':
        form = ExamQuestionWithOptionsForm(request.POST)
        if form.is_valid():
            form.save_for_exam(exam)
            messages.success(request, 'Pregunta agregada.')
            return redirect(
                'quizzes:exam_manage',
                course_id=course_id,
                unit_id=unit_id,
                tema_id=tema_id,
                exam_id=exam_id,
            )
    else:
        form = ExamQuestionWithOptionsForm()
    return render(
        request,
        'quizzes/question_form.html',
        {
            'form': form,
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'title': 'Nueva pregunta',
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def question_edit(request, course_id, unit_id, tema_id, exam_id, question_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)
    if exam_has_submitted_attempts(exam):
        messages.error(request, 'No se pueden editar preguntas: ya hay entregas de alumnos.')
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    question = get_object_or_404(ExamQuestion, pk=question_id, exam=exam)
    opts = list(question.answer_options.order_by('id'))
    if request.method == 'POST':
        form = ExamQuestionWithOptionsForm(request.POST)
        if form.is_valid():
            form.save_for_exam(exam, order=question.order, existing_question=question)
            messages.success(request, 'Pregunta actualizada.')
            return redirect(
                'quizzes:exam_manage',
                course_id=course_id,
                unit_id=unit_id,
                tema_id=tema_id,
                exam_id=exam_id,
            )
    else:
        initial = {
            'text': question.text,
            'correct_explanation': question.correct_explanation or '',
        }
        if len(opts) == 3:
            initial['option_a'] = opts[0].text
            initial['option_b'] = opts[1].text
            initial['option_c'] = opts[2].text
            for i, o in enumerate(opts):
                if o.is_correct:
                    initial['correct'] = ('a', 'b', 'c')[i]
                    break
        form = ExamQuestionWithOptionsForm(initial=initial)
    return render(
        request,
        'quizzes/question_form.html',
        {
            'form': form,
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'question': question,
            'title': 'Editar pregunta',
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def question_delete(request, course_id, unit_id, tema_id, exam_id, question_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)
    if exam_has_submitted_attempts(exam):
        messages.error(request, 'No se pueden eliminar preguntas: ya hay entregas.')
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    question = get_object_or_404(ExamQuestion, pk=question_id, exam=exam)
    if request.method == 'POST':
        question.delete()
        messages.success(request, 'Pregunta eliminada.')
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )
    return render(
        request,
        'quizzes/question_delete_confirm.html',
        {
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'question': question,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def exam_import(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)
    if exam_has_submitted_attempts(exam):
        messages.error(request, 'No se puede importar: ya hay entregas de alumnos.')
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    if request.method == 'POST':
        form = ExamImportForm(request.POST, request.FILES)
        if form.is_valid():
            replace = form.cleaned_data['replace_existing']
            rows, errs = parse_excel_rows(form.cleaned_data['file'])
            if errs:
                for e in errs[:20]:
                    messages.warning(request, e)
                if len(errs) > 20:
                    messages.warning(request, f'…y {len(errs) - 20} errores más.')
            if not rows and not errs:
                messages.error(request, 'No se encontraron filas de datos.')
            elif rows:
                try:
                    with transaction.atomic():
                        import_questions_for_exam(exam, rows, replace_existing=replace)
                except Exception as e:
                    messages.error(request, f'Error al importar: {e}')
                else:
                    messages.success(request, f'Se importaron {len(rows)} pregunta(s).')
                    return redirect(
                        'quizzes:exam_manage',
                        course_id=course_id,
                        unit_id=unit_id,
                        tema_id=tema_id,
                        exam_id=exam_id,
                    )
    else:
        form = ExamImportForm()
    return render(
        request,
        'quizzes/exam_import.html',
        {
            'form': form,
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
        },
    )


@login_required
def exam_export(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        raise Http404()
    wb = export_exam_to_workbook(exam)
    safe = ''.join(c if c.isalnum() else '_' for c in exam.title[:40])
    return workbook_to_response(wb, f'examen_{safe}_{exam.pk}.xlsx')


@login_required
def exam_template_download(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        raise Http404()
    wb = build_template_workbook()
    return workbook_to_response(wb, 'plantilla_examen.xlsx')


# --- Alumno ---


@login_required
@require_http_methods(['GET', 'POST'])
def exam_take(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)

    if request.user.is_teacher() or getattr(request.user, 'user_type', '') == 'admin':
        messages.info(request, 'Los docentes gestionan el examen desde la vista de administración.')
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    ok, err_msg = resolve_student_exam_access(request.user, course, tema, exam)
    if not ok:
        messages.error(request, err_msg or 'Este examen no está disponible o no tenés acceso.')
        return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)

    attempt, created = ExamAttempt.objects.get_or_create(
        exam=exam,
        student=request.user,
    )

    if attempt.is_submitted():
        return redirect(
            'quizzes:exam_result',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    ensure_attempt_shuffle_and_answers(attempt)
    attempt.refresh_from_db()

    questions_by_id = {
        q.pk: q
        for q in exam.questions.prefetch_related('answer_options')
    }
    options_by_id = {}
    for q in questions_by_id.values():
        for o in q.answer_options.all():
            options_by_id[o.pk] = o

    state = attempt.shuffle_state or {}
    q_order = state.get('question_ids') or []
    opt_orders = state.get('options') or {}

    display_questions = []
    for qid in q_order:
        q = questions_by_id.get(qid)
        if not q:
            continue
        raw_order = opt_orders.get(str(qid)) or []
        options_display = []
        for token in raw_order:
            if token == DONT_KNOW_SHUFFLE_TOKEN or token == 'dk':
                options_display.append({'kind': 'dont_know'})
            else:
                try:
                    oid = int(token)
                except (TypeError, ValueError):
                    continue
                opt = options_by_id.get(oid)
                if opt and opt.question_id == q.pk:
                    options_display.append({'kind': 'option', 'option': opt})
        dk_count = sum(1 for x in options_display if x.get('kind') == 'dont_know')
        opt_count = sum(1 for x in options_display if x.get('kind') == 'option')
        if dk_count != 1 or opt_count != 3:
            continue
        aa = ExamAttemptAnswer.objects.filter(attempt=attempt, question=q).first()
        selected_dk = bool(aa and aa.dont_know)
        selected_id = aa.selected_option_id if aa and not aa.dont_know else None
        display_questions.append(
            {
                'question': q,
                'options_display': options_display,
                'selected_id': selected_id,
                'selected_dk': selected_dk,
            }
        )

    n = len(display_questions)
    try:
        step = int(request.GET.get('step', 0))
    except (TypeError, ValueError):
        step = 0
    if n > 0:
        step = max(0, min(n - 1, step))

    def _redirect_take(s):
        url = reverse(
            'quizzes:exam_take',
            kwargs={
                'course_id': course_id,
                'unit_id': unit_id,
                'tema_id': tema_id,
                'exam_id': exam_id,
            },
        )
        return redirect(f'{url}?step={s}')

    def _save_answer_for_step(step_idx):
        if not n or step_idx < 0 or step_idx >= n:
            return
        dq = display_questions[step_idx]
        key = f'q_{dq["question"].pk}'
        raw = request.POST.get(key)
        if not raw:
            return
        if raw == DONT_KNOW_POST_VALUE:
            ExamAttemptAnswer.objects.update_or_create(
                attempt=attempt,
                question=dq['question'],
                defaults={
                    'selected_option_id': None,
                    'dont_know': True,
                },
            )
            return
        try:
            oid = int(raw)
        except ValueError:
            return
        opt = options_by_id.get(oid)
        if not opt or opt.question_id != dq['question'].pk:
            return
        ExamAttemptAnswer.objects.update_or_create(
            attempt=attempt,
            question=dq['question'],
            defaults={
                'selected_option_id': oid,
                'dont_know': False,
            },
        )

    if request.method == 'POST':
        # Guardar la opción al marcar un radio (última pregunta no tiene «Siguiente»).
        if request.POST.get('save_answer'):
            try:
                current_step = int(request.POST.get('current_step', 0))
            except (TypeError, ValueError):
                current_step = 0
            if n:
                current_step = max(0, min(n - 1, current_step))
            _save_answer_for_step(current_step)
            return _redirect_take(current_step)

        nav = request.POST.get('nav')
        if nav in ('prev', 'next'):
            try:
                current_step = int(request.POST.get('current_step', 0))
            except (TypeError, ValueError):
                current_step = 0
            if n:
                current_step = max(0, min(n - 1, current_step))
            _save_answer_for_step(current_step)
            if nav == 'prev':
                new_step = max(0, current_step - 1)
            else:
                new_step = min(n - 1, current_step + 1) if n else 0
            return _redirect_take(new_step)

        if 'submit_exam' in request.POST:
            try:
                current_step = int(request.POST.get('current_step', 0))
            except (TypeError, ValueError):
                current_step = 0
            if n:
                current_step = max(0, min(n - 1, current_step))
            _save_answer_for_step(current_step)

            first_missing_idx = None
            for idx, dq in enumerate(display_questions):
                aa = ExamAttemptAnswer.objects.filter(
                    attempt=attempt,
                    question_id=dq['question'].pk,
                ).first()
                if not aa or (not aa.selected_option_id and not aa.dont_know):
                    first_missing_idx = idx
                    break

            if first_missing_idx is not None:
                messages.error(
                    request,
                    'Debés responder todas las preguntas antes de enviar.',
                )
                return _redirect_take(first_missing_idx)

            with transaction.atomic():
                answers = list(
                    attempt.answers.select_related('selected_option', 'question')
                )
                total = len(answers)
                correct = sum(
                    1
                    for a in answers
                    if a.selected_option_id and a.selected_option.is_correct
                )
                score = ThemeExam.score_from_counts(correct, total)
                attempt.correct_count = correct
                attempt.total_questions = total
                attempt.score = score
                attempt.submitted_at = timezone.now()
                attempt.save(
                    update_fields=[
                        'correct_count',
                        'total_questions',
                        'score',
                        'submitted_at',
                    ]
                )
            messages.success(
                request,
                f'Examen enviado. Tu nota: {score:.2f} / 10,00.',
            )
            return redirect(
                'quizzes:exam_result',
                course_id=course_id,
                unit_id=unit_id,
                tema_id=tema_id,
                exam_id=exam_id,
            )

    current_dq = display_questions[step] if n else None
    answered_count = 0
    progress_percent = 0
    if n:
        answered_count = ExamAttemptAnswer.objects.filter(
            attempt=attempt,
            question_id__in=[dq['question'].pk for dq in display_questions],
        ).filter(
            Q(selected_option_id__isnull=False) | Q(dont_know=True),
        ).count()
        progress_percent = min(100, int(100 * (step + 1) / n))

    can_submit_exam = bool(n and answered_count == n)

    return render(
        request,
        'quizzes/exam_take.html',
        {
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'attempt': attempt,
            'display_questions': display_questions,
            'step': step,
            'total_questions': n,
            'current_dq': current_dq,
            'has_prev': n > 0 and step > 0,
            'has_next': n > 0 and step < n - 1,
            'answered_count': answered_count,
            'progress_percent': progress_percent,
            'can_submit_exam': can_submit_exam,
        },
    )


@login_required
def exam_result(request, course_id, unit_id, tema_id, exam_id):
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)

    if request.user.is_teacher() or getattr(request.user, 'user_type', '') == 'admin':
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    if not _student_enrolled_approved(request.user, course):
        messages.error(request, 'No tenés acceso.')
        return redirect('course_list_student')

    attempt = ExamAttempt.objects.filter(exam=exam, student=request.user).first()
    if not attempt or not attempt.is_submitted():
        messages.info(request, 'Aún no enviaste este examen.')
        return redirect(
            'quizzes:exam_take',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    review_rows = build_exam_attempt_review_rows(attempt, exam)
    return render(
        request,
        'quizzes/exam_result.html',
        {
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'attempt': attempt,
            'review_rows': review_rows,
            'is_teacher_view': False,
        },
    )


@login_required
def exam_attempt_detail(request, course_id, unit_id, tema_id, exam_id, attempt_id):
    """Detalle de entrega para el docente: respuestas y correcciones."""
    course, unit, tema, exam = _get_exam(course_id, unit_id, tema_id, exam_id)
    if not exam.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso.')
        return redirect('course_detail', course_id=course_id)

    attempt = get_object_or_404(ExamAttempt, pk=attempt_id, exam=exam)
    if not attempt.is_submitted():
        messages.error(request, 'Este intento aún no fue enviado por el alumno.')
        return redirect(
            'quizzes:exam_manage',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            exam_id=exam_id,
        )

    review_rows = build_exam_attempt_review_rows(attempt, exam)
    return render(
        request,
        'quizzes/exam_attempt_detail.html',
        {
            'course': course,
            'unit': unit,
            'tema': tema,
            'exam': exam,
            'attempt': attempt,
            'review_rows': review_rows,
            'is_teacher_view': True,
        },
    )
