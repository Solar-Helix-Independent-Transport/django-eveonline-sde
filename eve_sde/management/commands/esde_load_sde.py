# Standard Library
import time

# Django
from django.core.management.base import BaseCommand

from ...sde_tasks import generate_sde_celestial_names, process_from_sde


class Command(BaseCommand):
    help = "Load SDE"

    def handle(self, *args, **options):
        start = time.perf_counter()
        process_from_sde()
        generate_sde_celestial_names()
        print(f"Took {time.perf_counter() - start:,.2f}s")
