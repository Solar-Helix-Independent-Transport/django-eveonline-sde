# Django
from django.core.management.base import BaseCommand

# AA Example App
from eve_sde.sde_tasks import (
    download_extract_sde,
    process_from_sde,
    process_section_of_sde,
)


class Command(BaseCommand):
    help = "Load SDE"

    def handle(self, *args, **options):
        # download_extract_sde()
        process_from_sde()
        # process_section_of_sde(2)
