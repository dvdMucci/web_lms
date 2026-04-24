from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import Q, Count, Exists, OuterRef
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.http import HttpResponse, Http404
from datetime import datetime, time
import json
import mimetypes
import os

from django.utils.safestring import mark_safe
from .models import (
    Assignment,
    AssignmentSubmission,
    AssignmentSubmissionFile,
    AssignmentCollaborator,
    AssignmentComment,
)
from .forms import AssignmentForm, SubmissionForm, FeedbackForm, CollaboratorForm, CommentForm
from courses.models import Course, Enrollment
from units.models import Unit, Tema
from accounts.models import UserActivityLog
from accounts.activity import log_user_activity
from django.contrib.auth import get_user_model


User = get_user_model()


def _guide_materials_for_request_user(user, assignment):
    """Materiales guía de la tarea visibles para el usuario (docente: todos; alumno: publicados y no privados)."""
    from materials.models import Material

    qs = Material.objects.filter(assignment=assignment).order_by('-uploaded_at')
    if user.is_teacher() or user.user_type == 'admin':
        return qs
    return qs.filter(is_published=True).filter(
        Q(visibility='public') | Q(visibility='enrolled')
    )


def _resolve_submission_file_field(submission, attachment_id=None):
    """
    Devuelve (django FileField file, nombre para descarga) o (None, None).
    """
    if attachment_id is not None:
        att = get_object_or_404(
            AssignmentSubmissionFile,
            pk=attachment_id,
            submission_id=submission.pk,
        )
        ff = att.file
        name = att.original_filename or os.path.basename(ff.name)
        return ff, name
    att = submission.attachment_files.order_by('order', 'id').first()
    if att:
        ff = att.file
        name = att.original_filename or os.path.basename(ff.name)
        return ff, name
    if submission.file:
        ff = submission.file
        name = submission.original_filename or os.path.basename(ff.name)
        return ff, name
    return None, None


def _http_response_from_uploaded_file(field_file, filename, *, inline):
    """Lee desde almacenamiento (local o remoto) y arma HttpResponse."""
    with field_file.open('rb') as f:
        data = f.read()
    content_type, _ = mimetypes.guess_type(filename)
    if not content_type:
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
        }
        content_type = content_type_map.get(ext, 'application/octet-stream')
    response = HttpResponse(data, content_type=content_type)
    disp = 'inline' if inline else 'attachment'
    response['Content-Disposition'] = f'{disp}; filename="{filename}"'
    return response


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
                messages.info(
                    request,
                    'Podés agregar material guía opcional (archivo o enlace) desde esta pantalla; no es obligatorio.',
                )
                if request.POST.get('create_and_add_material') == '1':
                    return redirect(
                        'assignments:assignment_material_upload',
                        course_id=course_id,
                        unit_id=unit_id,
                        tema_id=tema_id,
                        assignment_id=assignment.id,
                    )
                return redirect(
                    'assignments:assignment_detail',
                    course_id=course_id,
                    unit_id=unit_id,
                    tema_id=tema_id,
                    assignment_id=assignment.id,
                )
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
    
    viewing_as_student = getattr(request, 'viewing_as_student', False)
    is_teacher = (request.user.is_teacher() or request.user.user_type == 'admin') and not viewing_as_student
    can_manage = assignment.can_be_managed_by(request.user) and not viewing_as_student

    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'is_teacher': is_teacher,
        'can_manage': can_manage,
        'guide_materials': _guide_materials_for_request_user(request.user, assignment),
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
            ).prefetch_related('attachment_files').order_by('-version').first()
            
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
        ).prefetch_related('attachment_files').order_by('-version')
        
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
            file_list = form.cleaned_data['file_list']
            proto = AssignmentSubmission(assignment=assignment, student=request.user)
            version = proto.get_next_version()
            first_name = os.path.basename(file_list[0].name)
            submission = AssignmentSubmission(
                assignment=assignment,
                student=request.user,
                version=version,
                status='submitted',
                original_filename=first_name,
            )
            if assignment.is_late_submission():
                submission.status = 'submitted'
            try:
                with transaction.atomic():
                    submission.save()
                    for i, uploaded in enumerate(file_list):
                        AssignmentSubmissionFile.objects.create(
                            submission=submission,
                            file=uploaded,
                            original_filename=os.path.basename(uploaded.name),
                            order=i,
                        )
                    initial_comment = form.cleaned_data.get('initial_comment')
                    if initial_comment:
                        AssignmentComment.objects.create(
                            submission=submission,
                            user=request.user,
                            comment=initial_comment,
                        )
                n = len(file_list)
                msg_extra = f' ({n} archivos)' if n > 1 else ''
                messages.success(
                    request,
                    f'Entrega subida exitosamente (Versión {submission.version}){msg_extra}.',
                )
                log_user_activity(
                    action=UserActivityLog.ACTION_SUBMISSION_UPLOADED,
                    actor=request.user,
                    details=f'Entrega subida en tarea "{assignment.title}" (v{submission.version}, {n} archivo(s))',
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
    submission = get_object_or_404(
        AssignmentSubmission.objects.prefetch_related('attachment_files'),
        id=submission_id,
        assignment=assignment,
    )

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
    ).prefetch_related('attachment_files').order_by('-version')
    
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
    submission = get_object_or_404(
        AssignmentSubmission.objects.prefetch_related('attachment_files'),
        id=submission_id,
        assignment=assignment,
    )

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


def _submission_serve_file(request, course_id, unit_id, tema_id, assignment_id, submission_id, attachment_id, *, inline):
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)

    if request.user.is_student():
        if submission.student != request.user:
            messages.error(request, 'No tienes permiso para ver esta entrega.')
            return redirect(
                'assignments:assignment_detail',
                course_id=course_id,
                unit_id=unit_id,
                tema_id=tema_id,
                assignment_id=assignment_id,
            )
    elif not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para ver esta entrega.')
        return redirect(
            'assignments:assignment_detail',
            course_id=course_id,
            unit_id=unit_id,
            tema_id=tema_id,
            assignment_id=assignment_id,
        )

    ff, filename = _resolve_submission_file_field(submission, attachment_id)
    if not ff:
        raise Http404('Archivo no encontrado.')
    try:
        response = _http_response_from_uploaded_file(ff, filename, inline=inline)
        if inline:
            log_user_activity(
                action=UserActivityLog.ACTION_SUBMISSION_VIEWED,
                actor=request.user,
                details=f'Entrega visualizada de tarea "{assignment.title}"',
            )
        else:
            log_user_activity(
                action=UserActivityLog.ACTION_SUBMISSION_DOWNLOADED,
                actor=request.user,
                details=f'Entrega descargada de tarea "{assignment.title}"',
            )
        return response
    except FileNotFoundError:
        raise Http404('Archivo no encontrado.') from None


@login_required
def submission_view(request, course_id, unit_id, tema_id, assignment_id, submission_id):
    """Ver en el navegador el primer archivo o el indicado por URL de adjunto."""
    return _submission_serve_file(
        request, course_id, unit_id, tema_id, assignment_id, submission_id, None, inline=True
    )


@login_required
def submission_attachment_view(request, course_id, unit_id, tema_id, assignment_id, submission_id, attachment_id):
    return _submission_serve_file(
        request,
        course_id,
        unit_id,
        tema_id,
        assignment_id,
        submission_id,
        attachment_id,
        inline=True,
    )


@login_required
def submission_download(request, course_id, unit_id, tema_id, assignment_id, submission_id):
    return _submission_serve_file(
        request, course_id, unit_id, tema_id, assignment_id, submission_id, None, inline=False
    )


@login_required
def submission_attachment_download(request, course_id, unit_id, tema_id, assignment_id, submission_id, attachment_id):
    return _submission_serve_file(
        request,
        course_id,
        unit_id,
        tema_id,
        assignment_id,
        submission_id,
        attachment_id,
        inline=False,
    )


def _assignment_material_redirect_kwargs(course_id, unit_id, tema_id, assignment_id):
    return {
        'course_id': course_id,
        'unit_id': unit_id,
        'tema_id': tema_id,
        'assignment_id': assignment_id,
    }


@login_required
@require_http_methods(['GET', 'POST'])
def assignment_material_upload(request, course_id, unit_id, tema_id, assignment_id):
    from django.urls import reverse
    from units.forms import MaterialUploadForm

    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    kw = _assignment_material_redirect_kwargs(course_id, unit_id, tema_id, assignment_id)

    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso para subir material guía en esta tarea.')
        return redirect('assignments:assignment_detail', **kw)

    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['title'] = assignment.title
        post_data['description'] = assignment.description
        form = MaterialUploadForm(
            post_data,
            request.FILES,
            user=request.user,
            course=course,
            tema=tema,
            assignment=assignment,
        )
        if form.is_valid():
            material = form.save(commit=False)
            material.course = course
            material.tema = tema
            material.uploaded_by = request.user
            material.material_type = form.cleaned_data['material_type']

            if material.material_type == 'file' and material.file:
                if not material.original_filename:
                    material.original_filename = os.path.basename(material.file.name)

            material.save()

            if material.is_published and not material.scheduled_publish_at and material.send_notification_email:
                try:
                    from core.notifications import notify_material_published
                    sent = notify_material_published(material)
                    if sent > 0:
                        messages.success(
                            request,
                            f'Material guía "{material.title}" subido y publicado. Se enviaron {sent} notificaciones por correo.',
                        )
                    else:
                        messages.success(
                            request,
                            f'Material guía "{material.title}" subido y publicado exitosamente.',
                        )
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error('Error al enviar notificaciones para material %s: %s', material.id, e)
                    messages.success(
                        request,
                        f'Material guía "{material.title}" subido. (Error al enviar notificaciones)',
                    )
            else:
                if material.scheduled_publish_at:
                    messages.success(
                        request,
                        f'Material guía "{material.title}" guardado. Se publicará el '
                        f'{material.scheduled_publish_at.strftime("%d/%m/%Y a las %H:%M")}.',
                    )
                else:
                    messages.success(request, f'Material guía "{material.title}" subido exitosamente.')
            log_user_activity(
                action=UserActivityLog.ACTION_MATERIAL_UPLOADED,
                actor=request.user,
                details=f'Material guía "{material.title}" en tarea "{assignment.title}" / {course.title}',
            )
            return redirect('assignments:assignment_detail', **kw)
    else:
        form = MaterialUploadForm(
            user=request.user,
            course=course,
            tema=tema,
            assignment=assignment,
        )

    material_cancel_url = reverse('assignments:assignment_detail', kwargs=kw)
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'title': 'Subir material guía',
        'material_cancel_url': material_cancel_url,
    }
    return render(request, 'units/material_upload.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def assignment_material_edit(request, course_id, unit_id, tema_id, assignment_id, material_id):
    from django.urls import reverse
    from materials.models import Material
    from units.forms import MaterialEditForm

    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    material = get_object_or_404(
        Material,
        id=material_id,
        assignment=assignment,
        tema=tema,
        course=course,
    )
    kw = _assignment_material_redirect_kwargs(course_id, unit_id, tema_id, assignment_id)

    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso para editar este material guía.')
        return redirect('assignments:assignment_detail', **kw)

    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['title'] = assignment.title
        post_data['description'] = assignment.description
        form = MaterialEditForm(
            post_data,
            request.FILES,
            instance=material,
            user=request.user,
            course=course,
            tema=tema,
            assignment=assignment,
        )
        if form.is_valid():
            old_is_published = material.is_published
            material = form.save()
            if not old_is_published and material.is_published and not material.scheduled_publish_at and material.send_notification_email:
                try:
                    from core.notifications import notify_material_published
                    sent = notify_material_published(material)
                    if sent > 0:
                        messages.success(
                            request,
                            f'Material guía "{material.title}" actualizado y publicado. Se enviaron {sent} notificaciones por correo.',
                        )
                    else:
                        messages.success(
                            request,
                            f'Material guía "{material.title}" actualizado y publicado exitosamente.',
                        )
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error('Error al enviar notificaciones para material %s: %s', material.id, e)
                    messages.success(
                        request,
                        f'Material guía "{material.title}" actualizado. (Error al enviar notificaciones)',
                    )
            else:
                messages.success(request, f'Material guía "{material.title}" actualizado exitosamente.')
            log_user_activity(
                action=UserActivityLog.ACTION_MATERIAL_UPDATED,
                actor=request.user,
                details=f'Material guía "{material.title}" en tarea "{assignment.title}"',
            )
            return redirect('assignments:assignment_detail', **kw)
    else:
        form = MaterialEditForm(
            instance=material,
            user=request.user,
            course=course,
            tema=tema,
            assignment=assignment,
        )

    material_cancel_url = reverse('assignments:assignment_detail', kwargs=kw)
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'material': material,
        'title': 'Editar material guía',
        'material_cancel_url': material_cancel_url,
    }
    return render(request, 'units/material_edit.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def assignment_material_delete(request, course_id, unit_id, tema_id, assignment_id, material_id):
    from django.urls import reverse
    from materials.models import Material

    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    tema = get_object_or_404(Tema, id=tema_id, unit=unit)
    assignment = get_object_or_404(Assignment, id=assignment_id, tema=tema, course=course)
    material = get_object_or_404(
        Material,
        id=material_id,
        assignment=assignment,
        tema=tema,
        course=course,
    )
    kw = _assignment_material_redirect_kwargs(course_id, unit_id, tema_id, assignment_id)

    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tenés permiso para eliminar este material guía.')
        return redirect('assignments:assignment_detail', **kw)

    if request.method == 'POST':
        material_title = material.title
        log_user_activity(
            action=UserActivityLog.ACTION_MATERIAL_DELETED,
            actor=request.user,
            details=f'Material guía "{material_title}" eliminado de tarea "{assignment.title}"',
        )
        material.delete()
        messages.success(request, f'Material guía "{material_title}" eliminado exitosamente.')
        return redirect('assignments:assignment_detail', **kw)

    material_cancel_url = reverse('assignments:assignment_detail', kwargs=kw)
    context = {
        'course': course,
        'unit': unit,
        'tema': tema,
        'assignment': assignment,
        'material': material,
        'has_file': bool(material.file),
        'material_cancel_url': material_cancel_url,
    }
    return render(request, 'units/material_delete_confirm.html', context)
