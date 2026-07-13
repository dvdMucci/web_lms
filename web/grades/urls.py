from django.urls import path

from . import views

app_name = 'grades'

urlpatterns = [
    path('', views.academic_situation_list, name='academic_situation_list'),
    path(
        'student/<int:student_id>/',
        views.academic_situation_student,
        name='academic_situation_student',
    ),
    path('my/', views.academic_situation_my, name='academic_situation_my'),
]
