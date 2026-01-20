from django.urls import path
from . import views

app_name = "units"

urlpatterns = [
    path('<int:course_id>/', views.unit_list, name='unit_list'),
    path('<int:course_id>/create/', views.unit_create, name='unit_create'),
    path('<int:course_id>/<int:unit_id>/', views.unit_detail, name='unit_detail'),
    path('<int:course_id>/<int:unit_id>/edit/', views.unit_edit, name='unit_edit'),
    path('<int:course_id>/<int:unit_id>/pause/', views.unit_pause, name='unit_pause'),
    path('<int:course_id>/<int:unit_id>/delete/', views.unit_delete, name='unit_delete'),
    path('<int:course_id>/<int:unit_id>/material/upload/', views.material_upload, name='material_upload'),
    path('<int:course_id>/<int:unit_id>/material/<int:material_id>/edit/', views.material_edit, name='material_edit'),
    path('<int:course_id>/<int:unit_id>/material/<int:material_id>/delete/', views.material_delete, name='material_delete'),
]
