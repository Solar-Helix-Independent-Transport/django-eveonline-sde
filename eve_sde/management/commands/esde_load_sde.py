# Standard Library
import time

# Django
from django.core.management.base import BaseCommand

# Django EVE SDE
from eve_sde.sde_tasks import (
    SDE_PARTS_TO_UPDATE,
    get_latest_sde,
    plan_sde_update,
    process_from_sde,
)


class Command(BaseCommand):
    help = "Load SDE, only the models changed since they were last loaded unless --full"

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="Reload every model.")
        parser.add_argument("--plan", action="store_true", help="Show what would be loaded and why, load nothing.")

    def handle(self, *args, **options):
        if options["plan"]:
            build = get_latest_sde().get("buildNumber")
            plan = plan_sde_update(build, full=options["full"])
            print(f"Build {build} - {len(plan)}/{len(SDE_PARTS_TO_UPDATE)} models to load")
            for idx, reason in plan.items():
                print(f"  {SDE_PARTS_TO_UPDATE[idx].__name__}: {reason}")
            return

        start = time.perf_counter()
        process_from_sde(full=options["full"])
        print(f"Took {time.perf_counter() - start:,.2f}s")
