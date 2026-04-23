from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


@receiver(post_save, sender='forums.ForumReply')
def update_post_activity(sender, instance, created, **kwargs):
    """When a new reply is saved, bump last_activity_at on the parent post."""
    if created:
        sender.__class__  # noqa: just to avoid unused import warnings
        instance.post.__class__.objects.filter(pk=instance.post_id).update(
            last_activity_at=timezone.now()
        )
