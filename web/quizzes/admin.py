from django.contrib import admin

from .models import (
    ExamAnswerOption,
    ExamAttempt,
    ExamAttemptAnswer,
    ExamQuestion,
    ThemeExam,
)


class ExamAnswerOptionInline(admin.TabularInline):
    model = ExamAnswerOption
    extra = 0


class ExamQuestionInline(admin.StackedInline):
    model = ExamQuestion
    extra = 0
    show_change_link = True
    fields = ('text', 'order', 'correct_explanation')


@admin.register(ThemeExam)
class ThemeExamAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'course',
        'tema',
        'is_published',
        'available_from',
        'available_until',
    )
    list_filter = ('is_published', 'course')
    inlines = [ExamQuestionInline]


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ('text', 'exam', 'order')
    inlines = [ExamAnswerOptionInline]


class ExamAttemptAnswerInline(admin.TabularInline):
    model = ExamAttemptAnswer
    extra = 0
    raw_id_fields = ('question', 'selected_option')


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ('exam', 'student', 'score', 'submitted_at')
    list_filter = ('exam',)
    inlines = [ExamAttemptAnswerInline]
