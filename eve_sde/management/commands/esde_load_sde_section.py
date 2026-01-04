# Django
from django.core.management.base import BaseCommand

# AA Example App
from eve_sde.sde_tasks import process_from_sde


class Command(BaseCommand):
    help = "Load SDE"

    def handle(self, *args, **options):
        process_from_sde(4)
