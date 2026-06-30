from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection


MODEL_DELETE_ORDER = [
    "swipes.SwipeHistory",
    "swipes.SavedServiceRequest",
    "approvals.CustomerSurvey",
    "approvals.ContactRequest",
    "services.ProviderDenialLog",
    "services.PhotoChangeRequest",
    "services.ServicePhoto",
    "services.ServicePrice",
    "services.ServiceProfile",
    "services.CityLocation",
    "services.ServiceCategory",
    "verification.VerifiedBadge",
    "moderation.Report",
    "bot.BotRegistrationSession",
    "approvals.AdminSettings",
    "accounts.TelegramUser",
    "authtoken.Token",
    "sessions.Session",
    "admin.LogEntry",
    "auth.User",
    "auth.Group",
    "auth.Permission",
    "contenttypes.ContentType",
]


class Command(BaseCommand):
    help = "Delete all records from all project models one by one (reset to fresh state)"

    def handle(self, *args, **options):
        self.stdout.write("Clearing all model data...\n")

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF;")

        total_deleted = 0
        for model_path in MODEL_DELETE_ORDER:
            try:
                app_label, model_name = model_path.split(".")
                model = apps.get_model(app_label, model_name)
                if model is None:
                    self.stdout.write(f"  [SKIP] {model_path} - not found")
                    continue
                count = model.objects.count()
                if count == 0:
                    self.stdout.write(f"  [OK]   {model_path} - already empty")
                    continue
                model.objects.all().delete()
                total_deleted += count
                self.stdout.write(f"  [DEL]  {model_path} - deleted {count} records")
            except Exception as e:
                self.stdout.write(f"  [ERR]  {model_path} - {e}")

        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("DELETE FROM sqlite_sequence;")

        self.stdout.write(self.style.SUCCESS(f"\nDone. Deleted {total_deleted} total records across all models."))
