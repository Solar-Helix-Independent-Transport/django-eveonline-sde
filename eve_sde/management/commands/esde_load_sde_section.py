# Django
from django.core.management.base import BaseCommand

# Django EVE SDE
from eve_sde.sde_tasks import (
    fetch_sde_for_plan,
    get_sde_target,
    process_section_of_sde,
)


class Command(BaseCommand):
    help = "Load SDE"

    def handle(self, *args, **options):
        target, _ = get_sde_target()
        fetch_sde_for_plan(target, {7: None})
        # process_from_sde()
        # process_section_of_sde(8)
        process_section_of_sde(7)
