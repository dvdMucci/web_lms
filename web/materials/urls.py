from django.urls import path
from . import views

app_name = "materials"

urlpatterns = [
    # Dashboard views
    path("courses/<int:course_id>/materials/", views.material_list, name="material-list-create"),
    # API endpoints (for API access)
    path("api/courses/<int:course_id>/materials/", views.MaterialListCreateView.as_view(), name="material-list-create-api"),
    path("materials/<int:pk>/", views.MaterialDetailView.as_view(), name="material-detail"),
    path("materials/<int:pk>/download/", views.MaterialDownloadView.as_view(), name="material-download"),
]