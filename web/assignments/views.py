from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Exists, OuterRef
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.http import HttpResponse, Http404
from django.core.files.storage import default_storage
from datetime import datetime, time
import json

from django.utils.safestring import mark_safe
from .models import Assignment, AssignmentSubmission, AssignmentCollaborator, AssignmentComment
from .forms import AssignmentForm, SubmissionForm, FeedbackForm, CollaboratorForm, CommentForm
from courses.models import Course, Enrollment
from units.models import Unit, Tema
from accounts.models import UserActivityLog
from accounts.activity import log_user_activity
from django.contrib.auth import get_user_model


User = get_user_model()


@login_required
def teacher_submission_report(request):
    """Reporte docente de entregas por alumno con filtros por curso, unidad, alumno y fechas."""
    if not request.user.is_teacher():
        messages.error(request, 'Esta vista es solo para docentes.')
        return redirect('dashboard')

    managed_courses = Course.objects.filter(
        Q(instructor=request.user) | Q(collaborators=request.user)
    ).distinct().order_by('title')

    course_id_raw = request.GET.get('course', '').strip()
    unit_id_raw = request.GET.get('unit', '').strip()
    student_id_raw = request.GET.get('student', '').strip()
    selected_course_id = None
    selected_unit_id = None
    selected_student_id = None

    courses_for_report = managed_courses
    if course_id_raw:
        try:
            cid = int(course_id_raw)
        except ValueError:
            cid = None
        if cid is not None:
            if managed_courses.filter(pk=cid).exists():
                selected_course_id = cid
                courses_for_report = managed_courses.filter(pk=cid)
            else:
                messages.warning(request, 'El curso seleccionado no está disponible o no lo gestionás.')

    assignments_qs = Assignment.objects.filter(course__in=courses_for_report)

    # Unidades por curso (JSON para rellenar el select sin recargar al elegir curso)
    units_by_course = {}
    for row in Unit.objects.filter(course__in=managed_courses).order_by(
        'course_id', 'order', 'pk'
    ).values('id', 'title', 'course_id'):
        key = str(row['course_id'])
        units_by_course.setdefault(key, []).append(
            {'id': row['id'], 'title': row['title']}
        )
    units_by_course_json = mark_safe(json.dumps(units_by_course, ensure_ascii=False))

    if unit_id_raw:
        try:
            uid = int(unit_id_raw)
        except ValueError:
            uid = None
        if uid is not None:
            unit_obj = Unit.objects.filter(pk=uid, course__in=managed_courses).select_related('course').first()
            if not unit_obj:
                messages.warning(request, 'La unidad seleccionada no existe o no pertenece a tus cursos.')
            elif not selected_course_id:
                messages.warning(request, 'Seleccioná un curso para poder filtrar por unidad.')
            elif unit_obj.course_id != selected_course_id:
                messages.warning(request, 'La unidad no pertenece al curso seleccionado.')
            else:
                selected_unit_id = uid
                assignments_qs = assignments_qs.filter(tema__unit_id=uid)

    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

    if start_date:
        try:
            start_parsed = datetime.strptime(start_date, '%Y-%m-%d')
            start_dt = timezone.make_aware(
                datetime.combine(start_parsed.date(), time.min),
                timezone.get_current_timezone(),
            )
            assignments_qs = assignments_qs.filter(due_date__gte=start_dt)
        except ValueError:
            messages.warning(request, 'La fecha desde no tiene un formato válido.')

    if end_date:
        try:
            end_parsed = datetime.strptime(end_date, '%Y-%m-%d')
            end_dt = timezone.make_aware(
                datetime.combine(end_parsed.date(), time.max),
                timezone.get_current_timezone(),
            )
            assignments_qs = assignments_qs.filter(due_date__lte=end_dt)
        except ValueError:
            messages.warning(request, 'La fecha hasta no tiene un formato válido.')

    assignments_qs = assignments_qs.select_related('course', 'tema', 'tema__unit')
    assignment_ids = list(assignments_qs.values_list('id', flat=True))

    totals_by_course = {
        row['course_id']: row['total']
        for row in assignments_qs.values('course_id').annotate(total=Count('id'))
    }

    enrollments_base = Enrollment.objects.filter(
        course__in=courses_for_report,
        status='approved',
    )

    # Alumnos inscriptos en los cursos del filtro (para el desplegable "Alumno")
    student_ids_in_scope = enrollments_base.values_list('student_id', flat=True).distinct()
    students_for_select = User.objects.filter(
        pk__in=student_ids_in_scope,
        user_type='student',
    ).order_by('last_name', 'first_name', 'username')

    if student_id_raw:
        try:
            sid = int(student_id_raw)
        except ValueError:
            sid = None
        if sid is not None:
            if enrollments_base.filter(student_id=sid).exists():
                selected_student_id = sid
            else:
                messages.warning(request, 'El alumno seleccionado no pertenece al curso o no está inscripto.')

    enrollments = enrollments_base.select_related('student', 'course').order_by(
        'course__title', 'student__last_name', 'student__first_name'
    )
    if selected_student_id is not None:
        enrollments = enrollments.filter(student_id=selected_student_id)

    submitted_by_pair = {
        (row['assignment__course_id'], row['student_id']): row['submitted']
        for row in AssignmentSubmission.objects.filter(
            assignment_id__in=assignment_ids
        ).values('assignment__course_id', 'student_id').annotate(
            submitted=Count('assignment_id', distinct=True)
        )
    } if assignment_ids else {}

    rows = []
    for enrollment in enrollments:
        total_assignments = totals_by_course.get(enrollment.course_id, 0)
        submitted_count = submitted_by_pair.get((enrollment.course_id, enrollment.student_id), 0)
        percentage = round((submitted_count / total_assignments) * 100, 2) if total_assignments else 0
        rows.append({
            'course': enrollment.course,
            'student': enrollment.student,
            'total_assignments': total_assignments,
            'submitted_count': submitted_count,
            'percentage': percentage,
        })

    context = {
        'rows': rows,
        'start_date': start_date,
        'end_date': end_date,
        'managed_courses': managed_courses,
        'units_by_course_json': units_by_course_json,
        'students_for_select': students_for_select,
        'selected_course_id': selected_course_id,
        'selected_unit_id': selected_unit_id,
        'selected_student_id': selected_student_id,
    }
    return render(request, 'assignments/teacher_submission_report.html', context)


@login_required
def assignment_list(request, course_id, unit_id, tema_id):
    """List all assignments for a theme"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    
    # Check if user can view the theme
    can_view = False
    if request.user.is_teacher() or request.user.user_type == 'admin':
        can_view = True
    elif request.user.is_student():
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).first()
        can_view = enrollment is not None and tema.is_visible_to_students()
    
    if not can_view:
        messages.error(request, 'No tienes permiso para ver las tareas de este tema.')
        return redirect('units:tema_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    
    # Get assignments - teachers see all, students only active and published
    if request.user.is_teacher() or request.user.user_type == 'admin':
        assignments = Assignment.objects.filter(tema=tema).order_by('due_date', 'created_at')
    else:
        assignments = Assignment.objects.filter(
            tema=tema,
            is_active=True,
            is_published=True
        ).order_by('due_date', 'created_at')
    
    # For each assignment, check if student has submitted
    if request.user.is_student():
        for assignment in assignments:
            assignment.has_submission = AssignmentSubmission.objects.filter(
                assignment=assignment,
                student=request.user
            ).exists()
            assignment.latest_submission = AssignmentSubmission.objects.filter(
                assignment=assignment,
                student=request.user
            ).order_by('-version').first()
    
    # Check if user can manage assignments
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignments': assignments,
        'can_manage': can_manage,
    }
    return render(request, 'assignments/assignment_list.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def assignment_create(request, course_id, unit_id, tema_id):
    """Create a new assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    
    # Check permissions
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    if not can_manage:
        messages.error(request, 'Solo el instructor, colaboradores o administradores pueden crear tareas.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    
    if request.method == 'POST':
        form = AssignmentForm(request.POST, user=request.user, course=course, tema=tema)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.course = course
            assignment.tema = tema
            assignment.created_by = request.user
            try:
                assignment.save()
                
                # Si se publicó inmediatamente y se solicitó notificación, enviar correos
                if assignment.is_published and not assignment.scheduled_publish_at and assignment.send_notification_email:
                    try:
                        from core.notifications import notify_assignment_published
                        sent = notify_assignment_published(assignment)
                        if sent > 0:
                            messages.success(request, f'Tarea "{assignment.title}" creada y publicada exitosamente. Se enviaron {sent} notificaciones por correo.')
                        else:
                            messages.success(request, f'Tarea "{assignment.title}" creada y publicada exitosamente.')
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f'Error al enviar notificaciones para tarea {assignment.id}: {e}')
                        messages.success(request, f'Tarea "{assignment.title}" creada exitosamente. (Error al enviar notificaciones)')
                else:
                    if assignment.scheduled_publish_at:
                        messages.success(request, f'Tarea "{assignment.title}" creada exitosamente. Se publicará el {assignment.scheduled_publish_at.strftime("%d/%m/%Y a las %H:%M")}.')
                    else:
                        messages.success(request, f'Tarea "{assignment.title}" creada exitosamente.')
                log_user_activity(
                    action=UserActivityLog.ACTION_ASSIGNMENT_CREATED,
                    actor=request.user,
                    details=f'Tarea "{assignment.title}" creada en "{course.title}"',
                )
                
                return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = AssignmentForm(user=request.user, course=course, tema=tema)
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'title': 'Crear Tarea',
    }
    return render(request, 'assignments/assignment_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def assignment_edit(request, course_id, unit_id, tema_id, assignment_id):
    """Edit an assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    
    # Check permissions
    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para editar esta tarea.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    
    if request.method == 'POST':
        form = AssignmentForm(request.POST, instance=assignment, user=request.user, course=course, tema=tema)
        if form.is_valid():
            old_is_published = assignment.is_published
            try:
                assignment = form.save()
                
                # Si se publicó por primera vez y se solicitó notificación, enviar correos
                if not old_is_published and assignment.is_published and not assignment.scheduled_publish_at and assignment.send_notification_email:
                    try:
                        from core.notifications import notify_assignment_published
                        sent = notify_assignment_published(assignment)
                        if sent > 0:
                            messages.success(request, f'Tarea "{assignment.title}" actualizada y publicada exitosamente. Se enviaron {sent} notificaciones por correo.')
                        else:
                            messages.success(request, f'Tarea "{assignment.title}" actualizada y publicada exitosamente.')
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f'Error al enviar notificaciones para tarea {assignment.id}: {e}')
                        messages.success(request, f'Tarea "{assignment.title}" actualizada exitosamente. (Error al enviar notificaciones)')
                else:
                    messages.success(request, f'Tarea "{assignment.title}" actualizada exitosamente.')
                log_user_activity(
                    action=UserActivityLog.ACTION_ASSIGNMENT_UPDATED,
                    actor=request.user,
                    details=f'Tarea "{assignment.title}" actualizada en "{course.title}"',
                )
                
                return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = AssignmentForm(instance=assignment, user=request.user, course=course, tema=tema)
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'title': 'Editar Tarea',
    }
    return render(request, 'assignments/assignment_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def assignment_delete(request, course_id, unit_id, tema_id, assignment_id):
    """Delete an assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    
    # Check permissions
    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para eliminar esta tarea.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    
    submission_count = AssignmentSubmission.objects.filter(assignment=assignment).count()

    if request.method == 'POST':
        assignment_title = assignment.title
        log_user_activity(
            action=UserActivityLog.ACTION_ASSIGNMENT_DELETED,
            actor=request.user,
            details=f'Tarea "{assignment_title}" eliminada de "{course.title}"',
        )
        assignment.delete()
        messages.success(request, f'Tarea "{assignment_title}" eliminada exitosamente.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    
    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'submission_count': submission_count,
    }
    return render(request, 'assignments/assignment_delete_confirm.html', context)


@login_required
def assignment_detail(request, course_id, unit_id, tema_id, assignment_id):
    """View assignment details - different for teachers and students"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    
    # Check if user can view
    can_view = False
    if request.user.is_teacher() or request.user.user_type == 'admin':
        can_view = True
    elif request.user.is_student():
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).first()
        can_view = enrollment is not None and assignment.is_active and assignment.is_published and tema.is_visible_to_students()
    
    if not can_view:
        messages.error(request, 'No tienes permiso para ver esta tarea.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id, tema_id=tema_id)
    
    is_teacher = request.user.is_teacher() or request.user.user_type == 'admin'
    can_manage = assignment.can_be_managed_by(request.user)
    
    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'is_teacher': is_teacher,
        'can_manage': can_manage,
    }
    
    if is_teacher:
        # Teacher view: show all submissions
        # Get all enrolled students
        enrolled_students = Enrollment.objects.filter(
            course=course,
            status='approved'
        ).select_related('student')
        
        # For each student, get their latest submission
        students_with_submissions = []
        submitted_count = 0
        pending_count = 0
        
        for enrollment in enrolled_students:
            student = enrollment.student
            latest_submission = AssignmentSubmission.objects.filter(
                assignment=assignment,
                student=student
            ).order_by('-version').first()
            
            has_submitted = latest_submission is not None
            if has_submitted:
                submitted_count += 1
            else:
                pending_count += 1
            
            students_with_submissions.append({
                'student': student,
                'has_submitted': has_submitted,
                'latest_submission': latest_submission,
                'submission_count': AssignmentSubmission.objects.filter(
                    assignment=assignment,
                    student=student
                ).count(),
            })
        
        context['students_with_submissions'] = students_with_submissions
        context['submitted_count'] = submitted_count
        context['pending_count'] = pending_count
        context['total_students'] = len(students_with_submissions)
        return render(request, 'assignments/assignment_detail_teacher.html', context)
    else:
        # Student view: show only their submissions
        submissions = AssignmentSubmission.objects.filter(
            assignment=assignment,
            student=request.user
        ).order_by('-version')
        
        # Check if can submit
        can_submit = assignment.is_submission_allowed()
        is_late = assignment.is_late_submission()
        
        # Check if assignment allows group work
        if assignment.allow_group_work:
            # Get latest submission to check collaborators
            latest_submission = submissions.first()
            if latest_submission:
                collaborators = AssignmentCollaborator.objects.filter(
                    submission=latest_submission
                ).select_related('student')
                context['collaborators'] = collaborators
        
        context['submissions'] = submissions
        context['can_submit'] = can_submit
        context['is_late'] = is_late
        return render(request, 'assignments/assignment_detail_student.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def submission_upload(request, course_id, unit_id, tema_id, assignment_id):
    """Upload a submission for an assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    
    # Check if user is student
    if not request.user.is_student():
        messages.error(request, 'Solo los estudiantes pueden entregar tareas.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    
    # Check if enrolled
    enrollment = Enrollment.objects.filter(
        student=request.user,
        course=course,
        status='approved'
    ).first()
    
    if not enrollment:
        messages.error(request, 'Debes estar inscrito y aprobado en el curso para entregar tareas.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    
    # Check if assignment allows submissions
    if not assignment.is_submission_allowed():
        messages.error(request, 'Ya no se pueden subir archivos para esta tarea.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    
    if request.method == 'POST':
        form = SubmissionForm(request.POST, request.FILES, assignment=assignment, student=request.user)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.assignment = assignment
            submission.student = request.user
            
            # Get next version number
            submission.version = submission.get_next_version()
            
            # Set status - check if assignment is past due date (submission will be late)
            if assignment.is_late_submission():
                submission.status = 'submitted'  # Still submitted, but will show as late
            else:
                submission.status = 'submitted'
            
            try:
                submission.save()
                
                # Save initial comment if provided
                initial_comment = form.cleaned_data.get('initial_comment')
                if initial_comment:
                    from .models import AssignmentComment
                    AssignmentComment.objects.create(
                        submission=submission,
                        user=request.user,
                        comment=initial_comment
                    )
                
                messages.success(request, f'Entrega subida exitosamente (Versión {submission.version}).')
                log_user_activity(
                    action=UserActivityLog.ACTION_SUBMISSION_UPLOADED,
                    actor=request.user,
                    details=f'Entrega subida en tarea "{assignment.title}" (v{submission.version})',
                )
                return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = SubmissionForm(assignment=assignment, student=request.user)
    
    # Check if late
    is_late = assignment.is_late_submission()
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'is_late': is_late,
    }
    return render(request, 'assignments/submission_upload.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def submission_detail(request, course_id, unit_id, tema_id, assignment_id, submission_id):
    """View submission details with all versions and comments"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions: student can only see their own, teacher can see all
    if request.user.is_student():
        if submission.student != request.user:
            messages.error(request, 'No tienes permiso para ver esta entrega.')
            return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    elif not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para ver esta entrega.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    
    # Get all versions of this submission
    all_versions = AssignmentSubmission.objects.filter(
        assignment=assignment,
        student=submission.student
    ).order_by('-version')
    
    # Get collaborators if group work
    collaborators = None
    collaborator_students = []
    if assignment.allow_group_work:
        collaborators = AssignmentCollaborator.objects.filter(
            submission=submission
        ).select_related('student')
        collaborator_students = [c.student for c in collaborators]
    
    can_manage = assignment.can_be_managed_by(request.user)
    
    # Get all comments for this submission (top-level only, replies loaded via prefetch)
    comments = AssignmentComment.objects.filter(
        submission=submission,
        parent_comment__isnull=True
    ).select_related('user').prefetch_related('replies__user').order_by('created_at')
    
    # Check if user can comment (student owner, collaborator, or teacher/admin)
    can_comment = False
    if request.user.is_student():
        can_comment = (
            submission.student == request.user or
            request.user in collaborator_students
        )
    elif request.user.is_teacher() or request.user.user_type == 'admin':
        can_comment = can_manage
    
    # Handle comment form submission
    comment_form = None
    if can_comment and request.method == 'POST' and 'add_comment' in request.POST:
        comment_form = CommentForm(request.POST, submission=submission, user=request.user)
        if comment_form.is_valid():
            comment = comment_form.save(commit=False)
            comment.submission = submission
            comment.user = request.user
            comment.save()
            messages.success(request, 'Comentario agregado exitosamente.')
            return redirect('assignments:submission_detail', 
                          course_id=course_id, unit_id=unit_id, tema_id=tema_id,
                          assignment_id=assignment_id, submission_id=submission_id)
    else:
        comment_form = CommentForm(submission=submission, user=request.user) if can_comment else None
    
    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'submission': submission,
        'all_versions': all_versions,
        'collaborators': collaborators,
        'can_manage': can_manage,
        'comments': comments,
        'can_comment': can_comment,
        'comment_form': comment_form,
    }
    return render(request, 'assignments/submission_detail.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def submission_feedback(request, course_id, unit_id, tema_id, assignment_id, submission_id):
    """Give feedback on a submission"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions
    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para dar feedback en esta entrega.')
        return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id, submission_id=submission_id)
    
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            submission.feedback = form.cleaned_data.get('feedback', '')
            submission.needs_resubmission = form.cleaned_data.get('needs_resubmission', False)
            submission.feedback_given_at = timezone.now()
            submission.feedback_given_by = request.user
            
            if submission.needs_resubmission:
                submission.status = 'returned'
            else:
                submission.status = 'submitted'
            
            submission.save()
            messages.success(request, 'Feedback guardado exitosamente.')
            return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id, submission_id=submission_id)
    else:
        form = FeedbackForm(initial={
            'feedback': submission.feedback,
            'needs_resubmission': submission.needs_resubmission,
        })
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'submission': submission,
    }
    return render(request, 'assignments/submission_feedback.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def collaborator_add(request, course_id, unit_id, tema_id, assignment_id, submission_id):
    """Add a collaborator to a submission (for group work)"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check if assignment allows group work
    if not assignment.allow_group_work:
        messages.error(request, 'Esta tarea no permite trabajo en grupo.')
        return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id, submission_id=submission_id)
    
    # Check if user is the student who submitted
    if request.user != submission.student:
        messages.error(request, 'Solo el estudiante que entregó puede agregar colaboradores.')
        return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id, submission_id=submission_id)
    
    if request.method == 'POST':
        form = CollaboratorForm(request.POST, submission=submission, current_student=request.user)
        if form.is_valid():
            username = form.cleaned_data['collaborator_username']
            from django.contrib.auth import get_user_model
            User = get_user_model()
            collaborator = User.objects.get(username=username)
            
            AssignmentCollaborator.objects.create(
                submission=submission,
                student=collaborator
            )
            messages.success(request, f'Colaborador "{username}" agregado exitosamente.')
            return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id, submission_id=submission_id)
    else:
        form = CollaboratorForm(submission=submission, current_student=request.user)
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'submission': submission,
    }
    return render(request, 'assignments/collaborator_add.html', context)


@login_required
def submission_view(request, course_id, unit_id, tema_id, assignment_id, submission_id):
    """View/preview a submission file in the browser"""
    import mimetypes
    import os
    
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions: student can only view their own, teacher can view all
    if request.user.is_student():
        if submission.student != request.user:
            messages.error(request, 'No tienes permiso para ver esta entrega.')
            return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    elif not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para ver esta entrega.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    
    if submission.file:
        try:
            file_path = submission.file.path
            filename = submission.original_filename if submission.original_filename else submission.file.name.split("/")[-1]
            
            # Determine content type
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                # Default content types for common file extensions
                ext = os.path.splitext(filename)[1].lower()
                content_type_map = {
                    '.pdf': 'application/pdf',
                    '.doc': 'application/msword',
                    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    '.ppt': 'application/vnd.ms-powerpoint',
                    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    '.xls': 'application/vnd.ms-excel',
                    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                }
                content_type = content_type_map.get(ext, 'application/octet-stream')
            
            with default_storage.open(file_path, 'rb') as f:
                response = HttpResponse(
                    f.read(),
                    content_type=content_type
                )
                # Use 'inline' to display in browser, 'attachment' to force download
                # For PDFs and images, use 'inline', for Office docs use 'attachment'
                if content_type in ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg', 'image/gif']:
                    response['Content-Disposition'] = f'inline; filename="{filename}"'
                else:
                    # For Office documents, still show inline but browser may download
                    response['Content-Disposition'] = f'inline; filename="{filename}"'
                log_user_activity(
                    action=UserActivityLog.ACTION_SUBMISSION_VIEWED,
                    actor=request.user,
                    details=f'Entrega visualizada de tarea "{assignment.title}"',
                )
                return response
        except FileNotFoundError:
            raise Http404("Archivo no encontrado.")
    
    raise Http404("Archivo no encontrado.")


@login_required
def submission_download(request, course_id, unit_id, tema_id, assignment_id, submission_id):
    """Download a submission file"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions: student can only download their own, teacher can download all
    if request.user.is_student():
        if submission.student != request.user:
            messages.error(request, 'No tienes permiso para descargar esta entrega.')
            return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    elif not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para descargar esta entrega.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, tema_id=tema_id, assignment_id=assignment_id)
    
    if submission.file:
        try:
            file_path = submission.file.path
            with default_storage.open(file_path, 'rb') as f:
                response = HttpResponse(
                    f.read(),
                    content_type='application/octet-stream'
                )
                filename = submission.original_filename if submission.original_filename else submission.file.name.split("/")[-1]
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                log_user_activity(
                    action=UserActivityLog.ACTION_SUBMISSION_DOWNLOADED,
                    actor=request.user,
                    details=f'Entrega descargada de tarea "{assignment.title}"',
                )
                return response
        except FileNotFoundError:
            raise Http404("Archivo no encontrado.")
    
    raise Http404("Archivo no encontrado.")
