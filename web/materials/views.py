from rest_framework import generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, Http404
from django.core.files.storage import default_storage
from .models import Material
from .serializers import MaterialSerializer, MaterialUploadSerializer
from courses.models import Enrollment, Course


class IsInstructorOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.is_teacher() or request.user.user_type == 'admin'
        )

    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_authenticated and
            (obj.uploaded_by == request.user or request.user.user_type == 'admin')
        )


class CanViewMaterial(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if obj.visibility == 'public':
            return True
        elif obj.visibility == 'enrolled':
            # Check if user is enrolled in the course
            return Enrollment.objects.filter(
                student=request.user,
                course=obj.course,
                status='approved'
            ).exists() or obj.uploaded_by == request.user or request.user.user_type == 'admin'
        elif obj.visibility == 'private':
            # Only uploader or admin can view
            return obj.uploaded_by == request.user or request.user.user_type == 'admin'
        return False


class MaterialListCreateView(generics.ListCreateAPIView):
    serializer_class = MaterialSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MaterialUploadSerializer
        return MaterialSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsInstructorOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)

        # Base queryset
        queryset = Material.objects.filter(course=course)

        # Filter based on user permissions
        user = self.request.user
        if user.is_teacher() or user.user_type == 'admin':
            # Teachers and admins see all materials
            pass
        else:
            # Students see materials based on visibility and publication status
            enrolled = Enrollment.objects.filter(
                student=user,
                course=course,
                status='approved'
            ).exists()

            if enrolled:
                # Show public and enrolled materials that are published
                queryset = queryset.filter(
                    visibility__in=['public', 'enrolled'],
                    is_published=True
                )
            else:
                # Show only public materials that are published
                queryset = queryset.filter(
                    visibility='public',
                    is_published=True
                )

        return queryset

    def perform_create(self, serializer):
        course_id = self.kwargs.get('course_id')
        course = get_object_or_404(Course, id=course_id)
        serializer.save(course=course, uploaded_by=self.request.user)


class MaterialDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer
    permission_classes = [permissions.IsAuthenticated, IsInstructorOrAdmin, CanViewMaterial]

    def get_permissions(self):
        if self.request.method in ['GET']:
            return [permissions.IsAuthenticated(), CanViewMaterial()]
        return [permissions.IsAuthenticated(), IsInstructorOrAdmin()]


class MaterialDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated, CanViewMaterial]

    def get(self, request, pk):
        material = get_object_or_404(Material, pk=pk)

        # Check permissions
        permission = CanViewMaterial()
        if not permission.has_object_permission(request, self, material):
            return Response(
                {"detail": "No tienes permiso para descargar este material."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Serve the file
        if material.file:
            try:
                file_path = material.file.path
                with default_storage.open(file_path, 'rb') as f:
                    response = HttpResponse(
                        f.read(),
                        content_type='application/octet-stream'
                    )
                    # Use original filename if available, otherwise use stored filename
                    filename = material.original_filename if material.original_filename else material.file.name.split("/")[-1]
                    response['Content-Disposition'] = f'attachment; filename="{filename}"'
                    return response
            except FileNotFoundError:
                raise Http404("Archivo no encontrado.")

        raise Http404("Archivo no encontrado.")


@login_required
def material_list(request, course_id):
    """List all materials for a course (dashboard view)"""
    course = get_object_or_404(Course, id=course_id)
    
    # Check if user can view the course
    can_view = False
    if request.user.is_teacher() or request.user.user_type == 'admin':
        can_view = True
    elif request.user.is_student():
        # Check if student is enrolled and approved
        enrollment = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).first()
        can_view = enrollment is not None
    
    if not can_view:
        messages.error(request, 'No tienes permiso para ver los materiales de este curso.')
        if request.user.is_student():
            return redirect('course_list_student')
        else:
            return redirect('course_list_teacher')
    
    # Get materials based on user permissions
    if request.user.is_teacher() or request.user.user_type == 'admin':
        # Teachers and admins see all materials
        materials = Material.objects.filter(course=course).order_by('-uploaded_at')
    else:
        # Students see materials based on visibility and publication status
        enrolled = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status='approved'
        ).exists()
        
        if enrolled:
            # Show public and enrolled materials that are published
            materials = Material.objects.filter(
                course=course,
                visibility__in=['public', 'enrolled'],
                is_published=True
            ).order_by('-uploaded_at')
        else:
            # Show only public materials that are published
            materials = Material.objects.filter(
                course=course,
                visibility='public',
                is_published=True
            ).order_by('-uploaded_at')
    
    # Check if user can manage materials
    can_manage = (
        course.instructor == request.user or
        request.user in course.collaborators.all() or
        request.user.user_type == 'admin'
    )
    
    context = {
        'course': course,
        'materials': materials,
        'can_manage': can_manage,
    }
    return render(request, 'materials/material_list.html', context)
