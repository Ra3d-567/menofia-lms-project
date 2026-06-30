from axes.signals import user_locked_out
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from lms_project.discord_alerts import send_security_alert


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    username = credentials.get('username', 'Unknown')
    ip = get_client_ip(request) if request else 'Unknown'
    
    send_security_alert(
        title="⚠️ Failed Login Attempt",
        description=f"**Username:** {username}\n**IP Address:** {ip}",
        color=16776960 # Yellow
    )
    
    from lms_app.utils import send_discord_log
    send_discord_log(f"⚠️ **Security Alert:** Failed login attempt for username: {username}")

@receiver(user_locked_out)
def log_axes_lockout(sender, request, credentials, **kwargs):
    username = credentials.get('username', 'Unknown')
    ip = get_client_ip(request) if request else 'Unknown'
    
    send_security_alert(
        title="🚨 Security Lockout Triggered",
        description=f"**Username/IP Blocked:** {username} / {ip}\nToo many failed login attempts.",
        color=16711680 # Red
    )

from django.db.models.signals import post_save

from lms_app.models import Announcement, Notification


@receiver(post_save, sender=Announcement)
def notify_students_of_announcement(sender, instance, created, **kwargs):
    if created:
        if instance.subject_section:
            students = instance.subject.enrolled_students.filter(section_group=instance.subject_section.section_group)
        else:
            students = instance.subject.enrolled_students.all()
            
        notifications = []
        for student in students:
            notifications.append(
                Notification(
                    recipient=student, 
                    message=f"📢 إعلان جديد: {instance.title}", 
                    link=f"/subject/{instance.subject.id}/"
                )
            )
            
        if notifications:
            Notification.objects.bulk_create(notifications)
