from rest_framework import generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from .models import Course, Enrollment
from .serializers import CourseSerializer, EnrollmentSerializer
from .forms import CourseForm


class IsTeacherOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_teacher() or request.user.user_type == 'admin'
        )


class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_student()


class IsInstructorOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated and
            (obj.instructor == request.user or request.user.user_type == 'admin')
        )


class CourseListCreateView(generics.ListCreateAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsTeacherOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = Course.objects.filter(is_active=True)
        # Teachers can see all courses, students only active ones
        if not (self.request.user.is_teacher() or self.request.user.user_type == 'admin'):
            queryset = queryset.filter(is_active=True)
        return queryset


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin]

    def get_permissions(self):
        if self.request.method in ['GET']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsInstructorOrAdmin()]


class EnrollmentListCreateView(generics.ListCreateAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsStudent()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)

        # Students can only see their own enrollments
        # Teachers/admins can see all enrollments for the course
        if self.request.user.is_student():
            return Enrollment.objects.filter(course=course, student=self.request.user)
        else:
            return Enrollment.objects.filter(course=course)

    def perform_create(self, serializer):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        serializer.save(course=course, student=self.request.user)


class EnrollmentDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = EnrollmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        course_id = self.kwargs.get('course_id')
        enrollment_id = self.kwargs.get('pk')

        # Students can only access their own enrollments
        # Teachers/admins can access any enrollment in their courses
        if self.request.user.is_student():
            return Enrollment.objects.filter(
                id=enrollment_id,
                course_id=course_id,
                student=self.request.user
            )
        else:
            # Instructors, collaborators, and admins can access enrollments
            return Enrollment.objects.filter(
                id=enrollment_id,
                course_id=course_id
            ).filter(
                Q(course__instructor=self.request.user) |
                Q(course__collaborators=self.request.user) |
                Q(course__instructor__user_type='admin')
            ).distinct()

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH']:
            return [permissions.IsAuthenticated(), IsInstructorOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_object(self):
        queryset = self.get_queryset()
        obj = get_object_or_404(queryset)
        self.check_object_permissions(self.request, obj)
        return obj

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        # Allow updating status for instructors, collaborators, or admins
        can_update = (
            instance.course.instructor == request.user or
            request.user in instance.course.collaborators.all() or
            request.user.user_type == 'admin'
        )
        
        if not can_update:
            return Response(
                {"detail": "No tienes permiso para actualizar esta inscripción."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Only allow status updates
        allowed_fields = {'status'}
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        return Response(serializer.data)


# Dashboard Views for Teachers
@login_required
def course_list_teacher(request):
    """List all courses - teachers can see all, but only manage their own or where they are collaborators"""
    if not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'No tienes permiso para acceder a esta página.')
        return redirect('dashboard')
    
    # Get all courses - any teacher can see them
    courses = Course.objects.all().order_by('-created_at')
    
    context = {
        'courses': courses,
        'user': request.user,
    }
    return render(request, 'courses/course_list_teacher.html', context)


# Dashboard Views for Students
@login_required
def course_list_student(request):
    """List all available courses for students (active and not paused)"""
    if not request.user.is_student():
        messages.error(request, 'Esta página es solo para estudiantes.')
        return redirect('dashboard')
    
    # Get courses that are visible to students (active and not paused)
    courses = Course.objects.filter(
        is_active=True,
        is_paused=False
    ).order_by('-created_at')
    
    # Get enrollments for the current student with their status
    enrollments = Enrollment.objects.filter(student=request.user).select_related('course')
    enrolled_course_ids = set(enrollments.values_list('course_id', flat=True))
    
    # Create a dictionary for quick lookup of enrollment status by course_id
    enrollment_status_by_course = {
        enrollment.course_id: enrollment.status 
        for enrollment in enrollments
    }
    
    context = {
        'courses': courses,
        'enrolled_course_ids': enrolled_course_ids,
        'enrollments': enrollments,
        'enrollment_status_by_course': enrollment_status_by_course,
    }
    return render(request, 'courses/course_list_student.html', context)


@login_required
def course_list_enrolled(request):
    """List courses where the student is enrolled"""
    if not request.user.is_student():
        messages.error(request, 'Esta página es solo para estudiantes.')
        return redirect('dashboard')
    
    # Get enrollments for the current student (including pending ones)
    enrollments = Enrollment.objects.filter(
        student=request.user
    ).select_related('course').order_by('-enrolled_at')
    
    context = {
        'enrollments': enrollments,
    }
    return render(request, 'courses/course_list_enrolled.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def enrollment_create(request, course_id):
    """Create an enrollment request for a student"""
    if not request.user.is_student():
        messages.error(request, 'Solo los estudiantes pueden inscribirse en cursos.')
        return redirect('dashboard')
    
    course = get_object_or_404(Course, id=course_id)
    
    # Check if course is visible to students
    if not course.is_visible_to_students():
        messages.error(request, 'Este curso no está disponible para inscripciones.')
        return redirect('course_list_student')
    
    # Check if already enrolled
    existing_enrollment = Enrollment.objects.filter(
        student=request.user,
        course=course
    ).first()
    
    if existing_enrollment:
        messages.info(request, f'Ya estás inscrito en el curso "{course.title}".')
        return redirect('course_list_enrolled')
    
    # Check if course has available spots
    if course.available_spots <= 0:
        messages.error(request, 'El curso ha alcanzado su límite de inscripción.')
        return redirect('course_list_student')
    
    if request.method == 'POST':
        # Create enrollment with pending status
        enrollment = Enrollment.objects.create(
            student=request.user,
            course=course,
            status='pending'
        )
        
        context = {
            'course': course,
            'enrollment': enrollment,
        }
        return render(request, 'courses/enrollment_created.html', context)
    
    # GET request: show confirmation page
    context = {
        'course': course,
    }
    return render(request, 'courses/enrollment_confirm.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def course_create(request):
    """Create a new course"""
    if not (request.user.is_teacher() or request.user.user_type == 'admin'):
        messages.error(request, 'Solo los profesores pueden crear cursos.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = CourseForm(request.POST, user=request.user)
        if form.is_valid():
            course = form.save(commit=False)
            course.instructor = request.user
            course.save()
            form.save_m2m()  # Save many-to-many relationships (collaborators)
            messages.success(request, f'Curso "{course.title}" creado exitosamente.')
            return redirect('course_list_teacher')
    else:
        form = CourseForm(user=request.user)
    
    context = {
        'form': form,
        'title': 'Crear Curso',
    }
    return render(request, 'courses/course_form.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def course_edit(request, course_id):
    """Edit an existing course - only instructor or admin can edit"""
    course = get_object_or_404(Course, id=course_id)
    
    # Only instructor or admin can edit (collaborators can view but not edit)
    if not (course.instructor == request.user or request.user.user_type == 'admin'):
        messages.error(request, 'Solo el instructor o un administrador pueden editar el curso.')
        return redirect('course_list_teacher')
    
    if request.method == 'POST':
        form = CourseForm(request.POST, instance=course, user=request.user)
        if form.is_valid():
            course = form.save()
            form.save_m2m()  # Save many-to-many relationships (collaborators)
            messages.success(request, f'Curso "{course.title}" actualizado exitosamente.')
            return redirect('course_list_teacher')
    else:
        form = CourseForm(instance=course, user=request.user)
    
    context = {
        'form': form,
        'course': course,
        'title': 'Editar Curso',
    }
    return render(request, 'courses/course_form.html', context)


@login_required
@require_http_methods(["POST"])
def course_pause(request, course_id):
    """Pause or resume a course - only instructor or admin can pause"""
    course = get_object_or_404(Course, id=course_id)
    
    # Only instructor or admin can pause (collaborators cannot)
    if not (course.instructor == request.user or request.user.user_type == 'admin'):
        messages.error(request, 'Solo el instructor o un administrador pueden pausar/reanudar este curso.')
        return redirect('course_list_teacher')
    
    course.is_paused = not course.is_paused
    course.save()
    
    action = 'pausado' if course.is_paused else 'reanudado'
    messages.success(request, f'Curso "{course.title}" {action} exitosamente.')
    return redirect('course_list_teacher')


@login_required
@require_http_methods(["GET", "POST"])
def course_delete(request, course_id):
    """Delete a course (with confirmation) - only instructor or admin can delete"""
    course = get_object_or_404(Course, id=course_id)
    
    # Only instructor or admin can delete (collaborators cannot)
    if not (course.instructor == request.user or request.user.user_type == 'admin'):
        messages.error(request, 'Solo el instructor o un administrador pueden eliminar este curso.')
        return redirect('course_list_teacher')
    
    if request.method == 'POST':
        course_title = course.title
        course.delete()
        messages.success(request, f'Curso "{course_title}" eliminado exitosamente.')
        return redirect('course_list_teacher')
    
    # GET request: show confirmation page
    context = {
        'course': course,
    }
    return render(request, 'courses/course_delete_confirm.html', context)


@login_required
def course_detail(request, course_id):
    """View course details - different content for students and teachers"""
    course = get_object_or_404(Course, id=course_id)
    
    context = {
        'course': course,
    }
    
    # For students: check enrollment status
    if request.user.is_student():
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course
        ).first()
        
        context['enrollment'] = enrollment
        context['is_enrolled'] = enrollment is not None
        context['is_approved'] = enrollment and enrollment.status == 'approved'
        
        # If approved, get additional details
        if context['is_approved']:
            # Get all approved enrollments (participants)
            participants = Enrollment.objects.filter(
                course=course,
                status='approved'
            ).select_related('student').order_by('student__first_name', 'student__last_name')
            context['participants'] = participants
            
            # Get collaborators
            context['collaborators'] = course.collaborators.all()
    
    # For teachers/admins: get all enrollments for management
    elif request.user.is_teacher() or request.user.user_type == 'admin':
        # Check if user can manage this course
        can_manage = (
            course.instructor == request.user or
            request.user in course.collaborators.all() or
            request.user.user_type == 'admin'
        )
        context['can_manage'] = can_manage
        
        # Get all enrollments
        enrollments = Enrollment.objects.filter(
            course=course
        ).select_related('student').order_by('-enrolled_at')
        context['enrollments'] = enrollments
        
        # Get collaborators
        context['collaborators'] = course.collaborators.all()
        
        # Get all teachers for adding as collaborators
        from django.contrib.auth import get_user_model
        User = get_user_model()
        all_teachers = User.objects.filter(user_type='teacher').exclude(id=course.instructor.id)
        context['all_teachers'] = all_teachers
    
    return render(request, 'courses/course_detail.html', context)


@login_required
@require_http_methods(["POST"])
def enrollment_approve(request, course_id, enrollment_id):
    """Approve an enrollment - instructor, collaborator, or admin"""
    course = get_object_or_404(Course, id=course_id)
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, course=course)
    
    # Check permissions
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    if not can_manage:
        messages.error(request, 'No tienes permiso para aprobar esta inscripción.')
        return redirect('course_detail', course_id=course_id)
    
    enrollment.status = 'approved'
    enrollment.save()
    messages.success(request, f'Inscripción de {enrollment.student.get_full_name() or enrollment.student.username} aprobada exitosamente.')
    return redirect('course_detail', course_id=course_id)


@login_required
@require_http_methods(["POST"])
def enrollment_reject(request, course_id, enrollment_id):
    """Reject an enrollment - instructor, collaborator, or admin"""
    course = get_object_or_404(Course, id=course_id)
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, course=course)
    
    # Check permissions
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    if not can_manage:
        messages.error(request, 'No tienes permiso para rechazar esta inscripción.')
        return redirect('course_detail', course_id=course_id)
    
    enrollment.status = 'rejected'
    enrollment.save()
    messages.success(request, f'Inscripción de {enrollment.student.get_full_name() or enrollment.student.username} rechazada.')
    return redirect('course_detail', course_id=course_id)


@login_required
@require_http_methods(["POST"])
def enrollment_cancel(request, course_id, enrollment_id):
    """Cancel/delete an enrollment - instructor, collaborator, or admin"""
    course = get_object_or_404(Course, id=course_id)
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, course=course)
    
    # Check permissions
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    if not can_manage:
        messages.error(request, 'No tienes permiso para cancelar esta inscripción.')
        return redirect('course_detail', course_id=course_id)
    
    student_name = enrollment.student.get_full_name() or enrollment.student.username
    enrollment.delete()
    messages.success(request, f'Inscripción de {student_name} cancelada exitosamente.')
    return redirect('course_detail', course_id=course_id)


@login_required
@require_http_methods(["POST"])
def add_collaborator(request, course_id):
    """Add a collaborator to the course - only instructor or admin"""
    course = get_object_or_404(Course, id=course_id)
    
    # Only instructor or admin can add collaborators
    if not (course.instructor == request.user or request.user.user_type == 'admin'):
        messages.error(request, 'Solo el instructor o un administrador pueden agregar colaboradores.')
        return redirect('course_detail', course_id=course_id)
    
    teacher_id = request.POST.get('teacher_id')
    if not teacher_id:
        messages.error(request, 'Debes seleccionar un docente.')
        return redirect('course_detail', course_id=course_id)
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    teacher = get_object_or_404(User, id=teacher_id, user_type='teacher')
    
    # Check if already a collaborator
    if teacher in course.collaborators.all():
        messages.warning(request, f'{teacher.get_full_name() or teacher.username} ya es colaborador de este curso.')
        return redirect('course_detail', course_id=course_id)
    
    # Check if trying to add the instructor
    if teacher == course.instructor:
        messages.error(request, 'El instructor no puede ser agregado como colaborador.')
        return redirect('course_detail', course_id=course_id)
    
    course.collaborators.add(teacher)
    messages.success(request, f'{teacher.get_full_name() or teacher.username} agregado como colaborador exitosamente.')
    return redirect('course_detail', course_id=course_id)


@login_required
@require_http_methods(["POST"])
def remove_collaborator(request, course_id, teacher_id):
    """Remove a collaborator from the course - only instructor or admin"""
    course = get_object_or_404(Course, id=course_id)
    
    # Only instructor or admin can remove collaborators
    if not (course.instructor == request.user or request.user.user_type == 'admin'):
        messages.error(request, 'Solo el instructor o un administrador pueden eliminar colaboradores.')
        return redirect('course_detail', course_id=course_id)
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    teacher = get_object_or_404(User, id=teacher_id, user_type='teacher')
    
    if teacher not in course.collaborators.all():
        messages.warning(request, f'{teacher.get_full_name() or teacher.username} no es colaborador de este curso.')
        return redirect('course_detail', course_id=course_id)
    
    course.collaborators.remove(teacher)
    messages.success(request, f'{teacher.get_full_name() or teacher.username} eliminado como colaborador exitosamente.')
    return redirect('course_detail', course_id=course_id)
