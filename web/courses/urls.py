from django.urls import path
from . import views

app_name = "courses"

urlpatterns = [
    # Course endpoints
    path("", views.CourseListCreateView.as_view(), name="course-list-create"),
    path("<int:pk>/", views.CourseDetailView.as_view(), name="course-detail"),

    # Enrollment endpoints
    path("<int:course_id>/enrollments/", views.EnrollmentListCreateView.as_view(), name="enrollment-list-create"),
    path("<int:course_id>/enrollments/<int:pk>/", views.EnrollmentDetailView.as_view(), name="enrollment-detail"),
]
