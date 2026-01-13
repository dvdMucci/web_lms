from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import dashboard # Importa el dashboard de tu app 'accounts'
from courses import views as course_views # Importa las vistas de cursos para el dashboard

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard, name='dashboard'), # Redirección de la raíz al dashboard
    path('dashboard/', dashboard, name='dashboard'),
    path('accounts/', include('accounts.urls')), # Incluye las URLs de la aplicación 'accounts'
    path('api/courses/', include('courses.urls')), # Incluye las URLs de la API de 'courses'
    path('api/', include('materials.urls')), # Incluye las URLs de la aplicación 'materials'
    path('units/', include('units.urls')), # Incluye las URLs de la aplicación 'units'
    path('', include('assignments.urls')), # Incluye las URLs de la aplicación 'assignments'
    
    # Dashboard URLs for courses
    path('courses/', include([
        # Teacher/Admin URLs
        path('', course_views.course_list_teacher, name='course_list_teacher'),
        path('create/', course_views.course_create, name='course_create'),
        path('<int:course_id>/', course_views.course_detail, name='course_detail'),
        path('<int:course_id>/edit/', course_views.course_edit, name='course_edit'),
        path('<int:course_id>/pause/', course_views.course_pause, name='course_pause'),
        path('<int:course_id>/delete/', course_views.course_delete, name='course_delete'),
        
        # Enrollment management
        path('<int:course_id>/enrollments/<int:enrollment_id>/approve/', course_views.enrollment_approve, name='enrollment_approve'),
        path('<int:course_id>/enrollments/<int:enrollment_id>/reject/', course_views.enrollment_reject, name='enrollment_reject'),
        path('<int:course_id>/enrollments/<int:enrollment_id>/cancel/', course_views.enrollment_cancel, name='enrollment_cancel'),
        
        # Collaborator management
        path('<int:course_id>/collaborators/add/', course_views.add_collaborator, name='add_collaborator'),
        path('<int:course_id>/collaborators/<int:teacher_id>/remove/', course_views.remove_collaborator, name='remove_collaborator'),
        
        # Student URLs
        path('available/', course_views.course_list_student, name='course_list_student'),
        path('enrolled/', course_views.course_list_enrolled, name='course_list_enrolled'),
        path('<int:course_id>/enroll/', course_views.enrollment_create, name='enrollment_create'),
    ])),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
