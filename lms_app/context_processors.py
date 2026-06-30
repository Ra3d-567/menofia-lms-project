from .models import GlobalAnnouncement


def active_announcement(request):
    return {
        'GLOBAL_ANNOUNCEMENT': GlobalAnnouncement.objects.filter(is_active=True).last()
    }

def user_notifications(request):
    if request.user.is_authenticated:
        return {'USER_NOTIFICATIONS': request.user.notifications.filter(is_read=False).order_by('-created_at')}
    return {'USER_NOTIFICATIONS': []}
