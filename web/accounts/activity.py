from .models import UserActivityLog


def log_user_activity(action, actor=None, target_user=None, target_username='', details=''):
    resolved_target_user = target_user
    if resolved_target_user is None and actor is not None and actor.is_authenticated:
        resolved_target_user = actor

    UserActivityLog.objects.create(
        actor=actor if actor and actor.is_authenticated else None,
        target_user=resolved_target_user,
        target_username=target_username or (resolved_target_user.username if resolved_target_user else ''),
        action=action,
        details=details,
    )
