from django.urls import path
from . import views

app_name = "assignments"

urlpatterns = [
    # Assignment CRUD
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/', views.assignment_list, name='assignment_list'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/create/', views.assignment_create, name='assignment_create'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/', views.assignment_detail, name='assignment_detail'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/edit/', views.assignment_edit, name='assignment_edit'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/delete/', views.assignment_delete, name='assignment_delete'),
    
    # Submissions
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/upload/', views.submission_upload, name='submission_upload'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/submissions/<int:submission_id>/', views.submission_detail, name='submission_detail'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/submissions/<int:submission_id>/view/', views.submission_view, name='submission_view'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/submissions/<int:submission_id>/feedback/', views.submission_feedback, name='submission_feedback'),
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/submissions/<int:submission_id>/download/', views.submission_download, name='submission_download'),
    
    # Collaborators
    path('courses/<int:course_id>/units/<int:unit_id>/assignments/<int:assignment_id>/submissions/<int:submission_id>/collaborator/add/', views.collaborator_add, name='collaborator_add'),
]
