"""Lógica auxiliar para intentos y orden aleatorio."""
import secrets

from django.db import transaction

from .models import ExamAttempt, ExamAttemptAnswer

# Token en shuffle_state JSON (mezclado con ids de opción como strings).
DONT_KNOW_SHUFFLE_TOKEN = 'dk'
# Valor POST del radio «No lo sé».
DONT_KNOW_POST_VALUE = '__dk__'


def exam_has_submitted_attempts(exam):
    return exam.attempts.filter(submitted_at__isnull=False).exists()


def _options_map_needs_rebuild(options_map, questions) -> bool:
    """Incluye la cuarta opción sintética «No lo sé» en el orden mezclado."""
    for q in questions:
        toks = options_map.get(str(q.id))
        if not toks or len(toks) != 4:
            return True
        if not any(
            t == DONT_KNOW_SHUFFLE_TOKEN or t == 'dk' for t in toks
        ):
            return True
        oids = list(q.answer_options.values_list('id', flat=True))
        if len(oids) != 3:
            return True
        int_ids = set()
        for t in toks:
            if t == DONT_KNOW_SHUFFLE_TOKEN or t == 'dk':
                continue
            try:
                int_ids.add(int(t))
            except (TypeError, ValueError):
                return True
        if int_ids != set(oids):
            return True
    return False


def resolve_student_exam_access(user, course, tema, exam):
    """
    Para alumnos: (True, None) si puede rendir el examen; si no, (False, mensaje).
    """
    from courses.models import Enrollment

    if not user.is_student():
        return False, 'Solo los alumnos pueden realizar el examen.'
    if not Enrollment.objects.filter(
        student=user,
        course=course,
        status='approved',
    ).exists():
        return False, 'No estás inscripto en este curso o tu inscripción no está aprobada.'
    if not tema.is_visible_to_students():
        return False, 'Este tema no está disponible para estudiantes.'
    if not exam.is_published:
        return False, 'El examen no está publicado.'
    if not exam.is_available_now():
        return False, 'El examen no está disponible en este momento.'
    if exam.attendance_date and not student_is_present_on_date(
        user, course, exam.attendance_date
    ):
        return False, (
            'Este examen solo puede realizarse si estuviste presente el día '
            f'{exam.attendance_date.strftime("%d/%m/%Y")} según la asistencia del curso.'
        )
    return True, None


def student_is_present_on_date(user, course, attendance_date) -> bool:
    """True si el alumno tiene registro «presente» en la sesión de asistencia de ese día."""
    from attendance.models import AttendanceRecord, AttendanceSession

    session = AttendanceSession.objects.filter(
        course=course,
        date=attendance_date,
    ).first()
    if not session:
        return False
    rec = AttendanceRecord.objects.filter(session=session, student=user).first()
    if not rec:
        return False
    return rec.status == 'present'


def ensure_attempt_shuffle_and_answers(attempt: ExamAttempt) -> None:
    """
    Genera shuffle_state y filas de ExamAttemptAnswer si el intento no está enviado.
    """
    if attempt.is_submitted():
        return

    exam = attempt.exam
    questions = list(exam.questions.prefetch_related('answer_options'))
    if not questions:
        return

    rng = secrets.SystemRandom()
    state = attempt.shuffle_state or {}
    q_ids_state = state.get('question_ids') or []
    current_ids = [q.id for q in questions]
    options_map = state.get('options') or {}

    need_rebuild = (
        not q_ids_state
        or len(q_ids_state) != len(current_ids)
        or set(q_ids_state) != set(current_ids)
        or _options_map_needs_rebuild(options_map, questions)
    )

    if need_rebuild:
        q_ids = current_ids[:]
        rng.shuffle(q_ids)
        options_map = {}
        for q in questions:
            oids = list(q.answer_options.values_list('id', flat=True))
            if len(oids) == 3:
                pack = [str(x) for x in oids] + [DONT_KNOW_SHUFFLE_TOKEN]
                rng.shuffle(pack)
                options_map[str(q.id)] = pack
        attempt.shuffle_state = {'question_ids': q_ids, 'options': options_map}
        attempt.save(update_fields=['shuffle_state'])
        ExamAttemptAnswer.objects.filter(attempt=attempt).exclude(
            question_id__in=current_ids
        ).delete()

    with transaction.atomic():
        for q in questions:
            ExamAttemptAnswer.objects.get_or_create(
                attempt=attempt,
                question=q,
            )


def build_exam_attempt_review_rows(attempt: ExamAttempt, exam):
    """
    Filas para vista de resultado: orden del intento (shuffle), texto de pregunta,
    opción elegida, opción correcta, si acertó, aclaración opcional.
    """
    state = attempt.shuffle_state or {}
    q_order = state.get('question_ids') or []
    if not q_order:
        q_order = list(
            exam.questions.order_by('order', 'id').values_list('pk', flat=True)
        )
    questions = {
        q.pk: q
        for q in exam.questions.prefetch_related('answer_options')
    }
    answers = {
        a.question_id: a
        for a in attempt.answers.select_related('selected_option', 'question')
    }
    rows = []
    for num, qid in enumerate(q_order, start=1):
        q = questions.get(qid)
        if not q:
            continue
        aa = answers.get(qid)
        selected = aa.selected_option if aa and not aa.dont_know else None
        selected_dont_know = bool(aa and aa.dont_know)
        correct_opt = next(
            (o for o in q.answer_options.all() if o.is_correct),
            None,
        )
        rows.append(
            {
                'num': num,
                'question': q,
                'selected': selected,
                'selected_dont_know': selected_dont_know,
                'correct_option': correct_opt,
                'is_correct': bool(selected and selected.is_correct),
                'explanation': (q.correct_explanation or '').strip(),
            }
        )
    return rows
