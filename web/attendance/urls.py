from django.urls import path

from . import views

app_name = 'attendance'

urlpatterns = [
    path('take/', views.attendance_take, name='attendance_take'),
    path('report/', views.attendance_report, name='attendance_report'),
    path('report/student/<int:student_id>/', views.attendance_student_detail, name='attendance_student_detail'),
    path('report/excel/', views.attendance_report_excel, name='attendance_report_excel'),
    path('report/pdf/', views.attendance_report_pdf, name='attendance_report_pdf'),
    path('my/', views.attendance_student_view, name='attendance_student_view'),
]
