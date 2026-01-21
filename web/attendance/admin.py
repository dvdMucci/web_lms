from django.contrib import admin

from .models import AttendanceSession, AttendanceRecord


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('course', 'date', 'created_by', 'updated_by', 'updated_at')
    list_filter = ('course', 'date')
    search_fields = ('course__title',)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('session', 'student', 'status', 'note', 'updated_by', 'updated_at')
    list_filter = ('status', 'session__course')
    search_fields = ('student__username', 'student__first_name', 'student__last_name')
