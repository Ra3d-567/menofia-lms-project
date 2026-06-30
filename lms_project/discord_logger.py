import logging
import requests
from django.conf import settings

class DiscordExceptionHandler(logging.Handler):
    def emit(self, record):
        webhook_url = getattr(settings, 'DISCORD_WEBHOOK_URL', None)
        if not webhook_url or webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
            return

        try:
            # Format the exception traceback using the logging formatter
            traceback = self.format(record)
            
            # Construct the Discord Embed payload
            payload = {
                "embeds": [
                    {
                        "title": "🚨 LMS System Alert",
                        "color": 16711680,  # Red color
                        "description": f"**Level:** {record.levelname}\n**Message:** {record.getMessage()}\n\n**Traceback:**\n```python\n{traceback[:3800]}\n```" # Truncate to avoid hitting Discord's 4096 char limit
                    }
                ]
            }

            # Send the request silently
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception:
            # Fail silently to avoid crashing the Django application
            pass
