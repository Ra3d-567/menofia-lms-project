import requests
from django.conf import settings


def send_discord_log(message):
    webhook_url = getattr(settings, 'DISCORD_WEBHOOK_URL', None)
    if webhook_url:
        try:
            requests.post(webhook_url, json={"content": message}, timeout=5)
        except Exception:
            # Silently fail so we don't crash the main app if Discord is down or times out
            pass
