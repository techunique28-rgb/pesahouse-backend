from django.core.management.base import BaseCommand

from rbac.services import sync_permissions


class Command(BaseCommand):
    help = "Synchronize permission catalog and system role templates"

    def handle(self, *args, **options):
        sync_permissions()
        self.stdout.write(self.style.SUCCESS("Permissions synchronized"))
