from django.core.management.base import BaseCommand

from lms_project import bot


class Command(BaseCommand):
    help = 'Runs the Discord Admin Bot'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Initiating Discord Bot service...'))
        try:
            bot.run()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('Discord Bot service stopped manually.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error starting Discord Bot: {e}'))
