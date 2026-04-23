from django.contrib import admin
from .models import ForumPost, ForumReply


class ForumReplyInline(admin.TabularInline):
    model = ForumReply
    extra = 0
    readonly_fields = ('author', 'created_at')
    fields = ('author', 'content', 'parent_reply', 'created_at')


@admin.register(ForumPost)
class ForumPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'author', 'is_private', 'is_pinned', 'is_locked', 'created_at')
    list_filter = ('course', 'is_private', 'is_pinned', 'is_locked')
    search_fields = ('title', 'content', 'author__username', 'course__title')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ForumReplyInline]


@admin.register(ForumReply)
class ForumReplyAdmin(admin.ModelAdmin):
    list_display = ('author', 'post', 'parent_reply', 'created_at')
    list_filter = ('post__course',)
    search_fields = ('content', 'author__username', 'post__title')
    readonly_fields = ('created_at', 'updated_at')
