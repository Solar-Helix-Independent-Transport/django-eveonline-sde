# Standard Library
import json

# Django
from django.core.management.base import BaseCommand

# Django EVE SDE
from eve_sde.models.base import JSONModel


def print_subclasses(self, model_check):
    for m in model_check.__subclasses__():
        try:
            self.stdout.write(f"{m.__name__} - {m.objects.all().count()}")
        except Exception:
            # best-effort diagnostic - skip abstract subclasses (no manager)
            # and any subclass without a real table (e.g. unmigrated)
            pass
        print_subclasses(self, m)


class Command(BaseCommand):
    help = "Print model stats"

    def handle(self, *args, **options):
        print_subclasses(self, JSONModel)
