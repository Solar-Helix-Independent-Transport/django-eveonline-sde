# Standard Library
import json
import os

# Django
from django.core.management.base import BaseCommand

from ...sde_tasks import SDE_FOLDER, delete_sde_folder, download_extract_sde


class Command(BaseCommand):
    help = "Output all the fields/types from all SDE files."

    def handle(self, *args, **options):
        download_extract_sde()
        files = [f for f in os.listdir(SDE_FOLDER) if os.path.isfile(os.path.join(SDE_FOLDER, f))]
        for fl in files:
            self.stdout.write(f"{fl}")
            fields = set()
            with open(f"{SDE_FOLDER}/{fl}") as json_file:
                while line := json_file.readline():
                    rg = json.loads(line)
                    if not isinstance(rg, list):
                        for fld, typ in rg.items():
                            if fld not in fields:
                                self.stdout.write(f"    {fld} : {typ.__class__.__name__}")
                                if isinstance(typ, dict):
                                    _b = f"        {fld}."
                                    for _fld, _typ in typ.items():
                                        self.stdout.write(f"{_b}{_fld} : {_typ.__class__.__name__}")
                                fields.add(fld)
        delete_sde_folder()
