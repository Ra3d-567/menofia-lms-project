import requests
from django.conf import settings

def send_security_alert(title, description, color=16776960):
    webhook_url = getattr(settings, 'DISCORD_SECURITY_WEBHOOK_URL', None)
    if not webhook_url or webhook_url == "YOUR_SECURITY_WEBHOOK_URL_HERE":
        return

    payload = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color
            }
        ]
    }

    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception:
        pass

def send_activity_alert(title, description, color):
    webhook_url = getattr(settings, 'DISCORD_ACTIVITY_WEBHOOK_URL', None)
    if not webhook_url or webhook_url == "YOUR_ACTIVITY_WEBHOOK_URL_HERE":
        return

    payload = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color
            }
        ]
    }

    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception:
        pass
