# Standard Library
import time

# Django
from django.core.management.base import BaseCommand

# Django EVE SDE
from eve_sde.sde_tasks import process_from_sde


class Command(BaseCommand):
    help = "Load SDE"

    def handle(self, *args, **options):
        start = time.perf_counter()
        process_from_sde()
        print(f"Took {time.perf_counter() - start:,.2f}s")
