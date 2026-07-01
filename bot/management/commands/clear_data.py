from django.core.management.base import BaseCommand

from bot.cleanup import DataCleanupManager


class Command(BaseCommand):
    help = "Delete all records from all project models one by one (reset to fresh state)"

    def handle(self, *args, **options):
        self.stdout.write("Clearing all model data...\n")

        manager = DataCleanupManager()
        results = manager.delete_all()

        total_deleted = 0
        for label, count in results.items():
            if count == 0:
                self.stdout.write(f"  [OK]   {label} - already empty")
            elif count == -1:
                self.stdout.write(f"  [ERR]  {label} - failed to delete")
            else:
                self.stdout.write(f"  [DEL]  {label} - deleted {count} records")
                total_deleted += count

        self.stdout.write(self.style.SUCCESS(f"\nDone. Deleted {total_deleted} total records across all models."))
