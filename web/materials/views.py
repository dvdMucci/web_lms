from rest_framework import generics, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
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
            # Students see materials based on visibility
            enrolled = Enrollment.objects.filter(
                student=user,
                course=course,
                status='approved'
            ).exists()

            if enrolled:
                # Show public and enrolled materials
                queryset = queryset.filter(visibility__in=['public', 'enrolled'])
            else:
                # Show only public materials
                queryset = queryset.filter(visibility='public')

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
                    response['Content-Disposition'] = f'attachment; filename="{material.file.name.split("/")[-1]}"'
                    return response
            except FileNotFoundError:
                raise Http404("Archivo no encontrado.")

        raise Http404("Archivo no encontrado.")
