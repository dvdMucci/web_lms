from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Q, Count, Exists, OuterRef
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.http import HttpResponse, Http404
from django.core.files.storage import default_storage
from .models import Assignment, AssignmentSubmission, AssignmentCollaborator, AssignmentComment
from .forms import AssignmentForm, SubmissionForm, FeedbackForm, CollaboratorForm, CommentForm
from courses.models import Course, Enrollment
from units.models import Unit


@login_required
def assignment_list(request, course_id, unit_id):
    """List all assignments for a unit"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    
    # Check if user can view the unit
    can_view = False
    if request.user.is_teacher() or request.user.user_type == 'admin':
        can_view = True
    elif request.user.is_student():
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).first()
        can_view = enrollment is not None and not unit.is_paused
    
    if not can_view:
        messages.error(request, 'No tienes permiso para ver las tareas de esta unidad.')
        return redirect('units:unit_detail', course_id=course_id, unit_id=unit_id)
    
    # Get assignments - teachers see all, students only active
    if request.user.is_teacher() or request.user.user_type == 'admin':
        assignments = Assignment.objects.filter(unit=unit).order_by('due_date', 'created_at')
    else:
        assignments = Assignment.objects.filter(unit=unit, is_active=True).order_by('due_date', 'created_at')
    
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
        'assignments': assignments,
        'can_manage': can_manage,
    }
    return render(request, 'assignments/assignment_list.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def assignment_create(request, course_id, unit_id):
    """Create a new assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    
    # Check permissions
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    if not can_manage:
        messages.error(request, 'Solo el instructor, colaboradores o administradores pueden crear tareas.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id)
    
    if request.method == 'POST':
        form = AssignmentForm(request.POST, user=request.user, course=course, unit=unit)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.course = course
            assignment.unit = unit
            assignment.created_by = request.user
            try:
                assignment.save()
                messages.success(request, f'Tarea "{assignment.title}" creada exitosamente.')
                return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = AssignmentForm(user=request.user, course=course, unit=unit)
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'title': 'Crear Tarea',
    }
    return render(request, 'assignments/assignment_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def assignment_edit(request, course_id, unit_id, assignment_id):
    """Edit an assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    
    # Check permissions
    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para editar esta tarea.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id)
    
    if request.method == 'POST':
        form = AssignmentForm(request.POST, instance=assignment, user=request.user, course=course, unit=unit)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'Tarea "{assignment.title}" actualizada exitosamente.')
                return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = AssignmentForm(instance=assignment, user=request.user, course=course, unit=unit)
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'assignment': assignment,
        'title': 'Editar Tarea',
    }
    return render(request, 'assignments/assignment_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def assignment_delete(request, course_id, unit_id, assignment_id):
    """Delete an assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    
    # Check permissions
    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para eliminar esta tarea.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id)
    
    if request.method == 'POST':
        assignment_title = assignment.title
        assignment.delete()
        messages.success(request, f'Tarea "{assignment_title}" eliminada exitosamente.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id)
    
    context = {
        'course': course,
        'unit': unit,
        'assignment': assignment,
    }
    return render(request, 'assignments/assignment_delete_confirm.html', context)


@login_required
def assignment_detail(request, course_id, unit_id, assignment_id):
    """View assignment details - different for teachers and students"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    
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
        can_view = enrollment is not None and assignment.is_active
    
    if not can_view:
        messages.error(request, 'No tienes permiso para ver esta tarea.')
        return redirect('assignments:assignment_list', course_id=course_id, unit_id=unit_id)
    
    is_teacher = request.user.is_teacher() or request.user.user_type == 'admin'
    can_manage = assignment.can_be_managed_by(request.user)
    
    context = {
        'course': course,
        'unit': unit,
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
def submission_upload(request, course_id, unit_id, assignment_id):
    """Upload a submission for an assignment"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    
    # Check if user is student
    if not request.user.is_student():
        messages.error(request, 'Solo los estudiantes pueden entregar tareas.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    
    # Check if enrolled
    enrollment = Enrollment.objects.filter(
        student=request.user,
        course=course,
        status='approved'
    ).first()
    
    if not enrollment:
        messages.error(request, 'Debes estar inscrito y aprobado en el curso para entregar tareas.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    
    # Check if assignment allows submissions
    if not assignment.is_submission_allowed():
        messages.error(request, 'Ya no se pueden subir archivos para esta tarea.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    
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
                return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
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
        'assignment': assignment,
        'is_late': is_late,
    }
    return render(request, 'assignments/submission_upload.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def submission_detail(request, course_id, unit_id, assignment_id, submission_id):
    """View submission details with all versions and comments"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions: student can only see their own, teacher can see all
    if request.user.is_student():
        if submission.student != request.user:
            messages.error(request, 'No tienes permiso para ver esta entrega.')
            return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    elif not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para ver esta entrega.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    
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
                          course_id=course_id, unit_id=unit_id, 
                          assignment_id=assignment_id, submission_id=submission_id)
    else:
        comment_form = CommentForm(submission=submission, user=request.user) if can_comment else None
    
    context = {
        'course': course,
        'unit': unit,
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
def submission_feedback(request, course_id, unit_id, assignment_id, submission_id):
    """Give feedback on a submission"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions
    if not assignment.can_be_managed_by(request.user):
        messages.error(request, 'No tienes permiso para dar feedback en esta entrega.')
        return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id, submission_id=submission_id)
    
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
            return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id, submission_id=submission_id)
    else:
        form = FeedbackForm(initial={
            'feedback': submission.feedback,
            'needs_resubmission': submission.needs_resubmission,
        })
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'assignment': assignment,
        'submission': submission,
    }
    return render(request, 'assignments/submission_feedback.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def collaborator_add(request, course_id, unit_id, assignment_id, submission_id):
    """Add a collaborator to a submission (for group work)"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check if assignment allows group work
    if not assignment.allow_group_work:
        messages.error(request, 'Esta tarea no permite trabajo en grupo.')
        return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id, submission_id=submission_id)
    
    # Check if user is the student who submitted
    if request.user != submission.student:
        messages.error(request, 'Solo el estudiante que entregó puede agregar colaboradores.')
        return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id, submission_id=submission_id)
    
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
            return redirect('assignments:submission_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id, submission_id=submission_id)
    else:
        form = CollaboratorForm(submission=submission, current_student=request.user)
    
    context = {
        'form': form,
        'course': course,
        'unit': unit,
        'assignment': assignment,
        'submission': submission,
    }
    return render(request, 'assignments/collaborator_add.html', context)


@login_required
def submission_view(request, course_id, unit_id, assignment_id, submission_id):
    """View/preview a submission file in the browser"""
    import mimetypes
    import os
    
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions: student can only view their own, teacher can view all
    if request.user.is_student():
        if submission.student != request.user:
            messages.error(request, 'No tienes permiso para ver esta entrega.')
            return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    elif not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para ver esta entrega.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    
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
                return response
        except FileNotFoundError:
            raise Http404("Archivo no encontrado.")
    
    raise Http404("Archivo no encontrado.")


@login_required
def submission_download(request, course_id, unit_id, assignment_id, submission_id):
    """Download a submission file"""
    course = get_object_or_404(Course, id=course_id)
    unit = get_object_or_404(Unit, id=unit_id, course=course)
    assignment = get_object_or_404(Assignment, id=assignment_id, unit=unit, course=course)
    submission = get_object_or_404(AssignmentSubmission, id=submission_id, assignment=assignment)
    
    # Check permissions: student can only download their own, teacher can download all
    if request.user.is_student():
        if submission.student != request.user:
            messages.error(request, 'No tienes permiso para descargar esta entrega.')
            return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    elif not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para descargar esta entrega.')
        return redirect('assignments:assignment_detail', course_id=course_id, unit_id=unit_id, assignment_id=assignment_id)
    
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
                return response
        except FileNotFoundError:
            raise Http404("Archivo no encontrado.")
    
    raise Http404("Archivo no encontrado.")
