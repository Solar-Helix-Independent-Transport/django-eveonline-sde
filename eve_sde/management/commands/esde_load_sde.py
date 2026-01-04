# Standard Library
import json

# Django
from django.core.management.base import BaseCommand

from ...tasks import update_models_from_sde


class Command(BaseCommand):
    help = "Load SDE"

    def handle(self, *args, **options):
        update_models_from_sde()
