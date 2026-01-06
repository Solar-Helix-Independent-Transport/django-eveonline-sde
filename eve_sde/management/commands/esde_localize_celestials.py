# Django
from django.core.management.base import BaseCommand

# AA Example App
from eve_sde.sde_tasks import (
    cleanup_sde_po_files,
    generate_sde_celestial_names,
    update_sde_mo_files,
)


class Command(BaseCommand):
    help = "Load SDE"

    def handle(self, *args, **options):
        generate_sde_celestial_names()
        cleanup_sde_po_files()
        update_sde_mo_files()
