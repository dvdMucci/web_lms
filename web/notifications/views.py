import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from .models import Notification


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user)[:50]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    return render(request, 'notifications/notification_list.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def notification_fetch(request):
    """AJAX: return recent notifications as JSON."""
    notifications = Notification.objects.filter(user=request.user)[:15]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    data = {
        'unread_count': unread_count,
        'notifications': [
            {
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'url': n.url,
                'is_read': n.is_read,
                'icon': n.icon,
                'color': n.color,
                'created_at': n.created_at.strftime('%d/%m/%Y %H:%M'),
                'notification_type': n.notification_type,
            }
            for n in notifications
        ],
    }
    return JsonResponse(data)


@login_required
@require_http_methods(['POST'])
def notification_mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    return JsonResponse({'ok': True})


@login_required
@require_http_methods(['POST'])
def notification_mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'ok': True})
