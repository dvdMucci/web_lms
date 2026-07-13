from django.contrib import admin

from .models import AcademicSituation


@admin.register(AcademicSituation)
class AcademicSituationAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'course',
        'year',
        'semester_1_valuation',
        'semester_2_valuation',
        'semester_1_grade',
        'semester_2_grade',
        'average_grade',
        'updated_at',
    )
    list_filter = ('year', 'course', 'semester_1_valuation', 'semester_2_valuation')
    search_fields = (
        'student__username',
        'student__first_name',
        'student__last_name',
        'course__title',
    )
    raw_id_fields = ('course', 'student', 'updated_by')
