# Standard Library
import importlib
import json
import re
from types import ModuleType

# Django
from django.apps import apps
from django.core.management.base import BaseCommand

# Django EVE SDE
from eve_sde.sde_tasks import check_sde_version
from eve_sde.test_data import dump_model_data


class Command(BaseCommand):
    help = "Generates test data for an application."

    def add_arguments(self, parser):
        parser.add_argument(
            "application_label",
            type=str,
            help="Label of the application to generate test data",
        )
        parser.add_argument(
            "--force_editable",
            type=bool,
            default=False,
            help="Force the data generation even if path doesn't appear to be editable",
        )
        parser.add_argument(
            "--ignore_version",
            type=bool,
            default=False,
            help="Ignore the version check and generates data from current database",
        )

    def _validate_application(
        self, application_label: str, force_editable: bool
    ) -> ModuleType:
        """
        Runs checks on the application:
        - exists
        - is in an editable path
        - had a valid module_name.tests.testdata module
        """
        application_config = apps.get_app_config(application_label)

        if not force_editable and re.match(
            r"python3.\d+/site-packages", application_config.path
        ):
            raise AssertionError(
                f"Path {application_config.path} doesn't appear to be editable. Run the command with force_editable=True if you are sure it's an editable path."
            )

        module = importlib.import_module(f"{application_label}.fixtures")

        # raises if testdata_spec is not defined
        module.testdata_spec

        return module

    def handle(self, *args, **options):
        if not (check_sde_version() or options["ignore_version"]):
            raise AssertionError(
                "Your SDE version isn't up to date. Use the `esde_load_sde` command to update it."
            )

        application_label = options["application_label"]
        force_editable = options["force_editable"]
        module = self._validate_application(application_label, force_editable)
        path = module.__path__[0]

        spec = module.testdata_spec

        dumped_data = dump_model_data(spec)

        formatted_json = json.dumps(json.loads(dumped_data), indent=4)

        with open(f"{path}/{application_label}_sde.json", "w") as f:
            f.write(formatted_json)
