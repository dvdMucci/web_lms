from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from django.db.models import BooleanField, Case, F, OuterRef, Q, Subquery, Value, When
from courses.models import Course, Enrollment
from core import notifications

from .models import ForumPost, ForumPostRead, ForumReply
from .forms import ForumPostForm, ForumReplyForm


def _get_course_and_role(request, course_id):
    """Return (course, is_teacher) or raise PermissionDenied if no access."""
    course = get_object_or_404(Course, id=course_id)
    user = request.user
    is_teacher = (
        course.is_instructor_or_collaborator(user) or user.user_type == 'admin'
    )
    is_enrolled = Enrollment.objects.filter(
        student=user, course=course, status='approved'
    ).exists()
    if not (is_teacher or is_enrolled):
        raise PermissionDenied
    return course, is_teacher


@login_required
def forum_list(request, course_id):
    course, is_teacher = _get_course_and_role(request, course_id)
    user = request.user

    last_read_sq = Subquery(
        ForumPostRead.objects.filter(
            user=user, post=OuterRef('pk')
        ).values('last_read_at')[:1]
    )

    def annotate_unread(qs):
        return qs.annotate(last_read=last_read_sq).annotate(
            is_unread=Case(
                When(last_read__isnull=True, then=Value(True)),
                When(last_activity_at__gt=F('last_read'), then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )

    base_qs = ForumPost.objects.filter(course=course).select_related(
        'author', 'student_participant'
    ).prefetch_related('replies')

    if is_teacher:
        general_posts = annotate_unread(
            base_qs.filter(is_private=False)
        ).order_by('-is_pinned', '-last_activity_at')
        private_posts = annotate_unread(
            base_qs.filter(is_private=True)
        ).order_by('-last_activity_at')
    else:
        general_posts = annotate_unread(
            base_qs.filter(is_private=False)
        ).order_by('-is_pinned', '-last_activity_at')
        private_posts = annotate_unread(
            base_qs.filter(is_private=True, student_participant=user)
        ).order_by('-last_activity_at')

    context = {
        'course': course,
        'general_posts': general_posts,
        'private_posts': private_posts,
        'is_teacher': is_teacher,
    }
    return render(request, 'forums/forum_list.html', context)


@login_required
def forum_create(request, course_id):
    course, is_teacher = _get_course_and_role(request, course_id)
    user = request.user

    if request.method == 'POST':
        form = ForumPostForm(request.POST, user=user, course=course)
        if form.is_valid():
            post = form.save(commit=False)
            post.course = course
            post.author = user

            if post.is_private:
                if user.is_student():
                    post.student_participant = user
                # For teachers, student_participant comes from the form.

            post.save()

            send_email = form.cleaned_data.get('send_email', False)
            if send_email:
                notifications.notify_forum_post(post)

            messages.success(request, 'Discusión creada exitosamente.')
            return redirect('forum_detail', post_id=post.pk)
    else:
        form = ForumPostForm(user=user, course=course)

    return render(request, 'forums/forum_create.html', {
        'form': form,
        'course': course,
        'is_teacher': is_teacher,
    })


@login_required
def forum_detail(request, post_id):
    post = get_object_or_404(
        ForumPost.objects.select_related('author', 'course', 'student_participant'),
        id=post_id,
    )

    if not post.can_view(request.user):
        raise PermissionDenied

    course = post.course
    user = request.user
    is_teacher = (
        course.is_instructor_or_collaborator(user) or user.user_type == 'admin'
    )

    # Mark this post as read for the current user.
    ForumPostRead.objects.update_or_create(user=user, post=post)

    top_level_replies = ForumReply.objects.filter(
        post=post, parent_reply__isnull=True
    ).select_related('author').prefetch_related('nested_replies__author')

    can_reply = post.can_reply(user)
    reply_form = None

    if request.method == 'POST' and can_reply:
        reply_form = ForumReplyForm(request.POST, user=user, post=post)
        if reply_form.is_valid():
            reply = reply_form.save(commit=False)
            reply.post = post
            reply.author = user

            parent_id = request.POST.get('parent_reply_id')
            if parent_id:
                try:
                    parent = ForumReply.objects.get(id=int(parent_id), post=post)
                    reply.parent_reply = parent
                except (ForumReply.DoesNotExist, ValueError):
                    pass

            reply.save()

            send_email = reply_form.cleaned_data.get('send_email', False)
            if send_email:
                notifications.notify_forum_reply(reply)

            messages.success(request, 'Respuesta enviada.')
            return redirect('forum_detail', post_id=post_id)

    if reply_form is None and can_reply:
        reply_form = ForumReplyForm(user=user, post=post)

    context = {
        'post': post,
        'course': course,
        'replies': top_level_replies,
        'can_reply': can_reply,
        'reply_form': reply_form,
        'can_edit': post.can_edit(user),
        'can_pin': post.can_pin(user),
        'is_teacher': is_teacher,
    }
    return render(request, 'forums/forum_detail.html', context)


@login_required
def forum_edit(request, post_id):
    post = get_object_or_404(ForumPost.objects.select_related('course'), id=post_id)
    if not post.can_edit(request.user):
        raise PermissionDenied

    course = post.course
    user = request.user
    is_teacher = (
        course.is_instructor_or_collaborator(user) or user.user_type == 'admin'
    )

    if request.method == 'POST':
        form = ForumPostForm(request.POST, instance=post, user=user, course=course)
        if form.is_valid():
            form.save()
            messages.success(request, 'Discusión actualizada.')
            return redirect('forum_detail', post_id=post.pk)
    else:
        form = ForumPostForm(instance=post, user=user, course=course)

    return render(request, 'forums/forum_edit.html', {
        'form': form,
        'post': post,
        'course': course,
        'is_teacher': is_teacher,
    })


@login_required
def forum_delete(request, post_id):
    post = get_object_or_404(ForumPost.objects.select_related('course'), id=post_id)
    if not post.can_edit(request.user):
        raise PermissionDenied

    course_id = post.course_id
    if request.method == 'POST':
        post.delete()
        messages.success(request, 'Discusión eliminada.')
        return redirect('forum_list', course_id=course_id)

    raise PermissionDenied


@login_required
def forum_pin(request, post_id):
    post = get_object_or_404(ForumPost.objects.select_related('course'), id=post_id)
    if not post.can_pin(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        post.is_pinned = not post.is_pinned
        post.save(update_fields=['is_pinned'])
        label = 'fijada' if post.is_pinned else 'desfijada'
        messages.success(request, f'Discusión {label}.')
        return redirect('forum_list', course_id=post.course_id)

    raise PermissionDenied


@login_required
def reply_delete(request, post_id, reply_id):
    reply = get_object_or_404(ForumReply, id=reply_id, post_id=post_id)
    if not reply.can_delete(request.user):
        raise PermissionDenied

    if request.method == 'POST':
        reply.delete()
        messages.success(request, 'Respuesta eliminada.')
        return redirect('forum_detail', post_id=post_id)

    raise PermissionDenied
