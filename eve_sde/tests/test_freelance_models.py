"""
Tests for FreelanceJobSchema/FreelanceJobSchemaParameter (freelance.py).

FreelanceJobSchema.from_jsonl unwraps the single-row "_value" list into one
model per schema and stashes the irregular extra config fields as a raw
blob. FreelanceJobSchemaParameter.from_jsonl is more involved: each
parameter is a oneOf of 4 shapes ("matcher", "boolean", "itemDelivery",
"options"), only "matcher" is normalized into real columns, "boolean"
falls back to its "choiceLabel" as a title, and load_from_sde wipes and
fully reloads on every run (same pattern as the blueprint activity models).
"""
# Standard Library
import json
import os
import shutil
import tempfile
from unittest import mock

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.freelance import (
    FreelanceJobSchema,
    FreelanceJobSchemaParameter,
    _build_value_type_models,
    _import_optional_model,
)
from eve_sde.models.lore import Archetype
from eve_sde.models.map import SolarSystem


class FreelanceModelsTestsBase(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 1,
            "_value": [
                {
                    "_key": "BoostShield",
                    "title": {"en": "Boost Shield"},
                    "description": {"en": "Boost a shield."},
                    "progressDescription": {"en": "Boosting..."},
                    "rewardDescription": {"en": "Reward"},
                    "targetDescription": {"en": "Target"},
                    "iconID": "icon123",
                    "contentTags": ["combat"],
                    "maxContributionsPerParticipant": {"count": 1},
                    "parameters": [
                        {
                            "_key": "target",
                            "matcher": {
                                "type": "solarsystem",
                                "acceptedValueTypes": ["solarsystem"],
                                "optional": False,
                                "maxEntries": 1,
                                "title": {"en": "Target System"},
                                "description": {"en": "Pick a system"},
                            },
                        },
                        {
                            "_key": "confirm",
                            "boolean": {
                                "choiceLabel": {"en": "Confirm?"},
                            },
                        },
                    ],
                },
            ],
        }
        with open(os.path.join(self.tmpdir, "freelanceJobSchemas.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")


class FreelanceJobSchemaTests(FreelanceModelsTestsBase):

    def test_unwraps_the_value_list_and_keeps_extra_config_as_a_blob(self):
        FreelanceJobSchema.load_from_sde(self.tmpdir)

        self.assertEqual(FreelanceJobSchema.objects.count(), 1)
        schema = FreelanceJobSchema.objects.get(pk="BoostShield")
        self.assertEqual(schema.title, "Boost Shield")
        self.assertEqual(schema.icon_key, "icon123")
        self.assertEqual(schema.content_tags, ["combat"])
        self.assertEqual(schema.extra_config, {"maxContributionsPerParticipant": {"count": 1}})

    def test_str(self):
        FreelanceJobSchema.load_from_sde(self.tmpdir)
        schema = FreelanceJobSchema.objects.get(pk="BoostShield")
        self.assertEqual(str(schema), "Boost Shield (BoostShield)")


class FreelanceJobSchemaParameterTests(FreelanceModelsTestsBase):

    def setUp(self):
        super().setUp()
        FreelanceJobSchema.load_from_sde(self.tmpdir)

    def test_matcher_parameter_is_normalized_into_columns(self):
        FreelanceJobSchemaParameter.load_from_sde(self.tmpdir)

        target = FreelanceJobSchemaParameter.objects.get(pk="BoostShield:target")
        self.assertEqual(target.kind, "matcher")
        self.assertEqual(target.matcher_type, "solarsystem")
        self.assertEqual(target.accepted_value_types, ["solarsystem"])
        self.assertEqual(target.max_entries, 1)
        self.assertEqual(target.title, "Target System")
        # raw keeps the full parameter entry (including its "_key"), not just
        # the matcher sub-dict
        self.assertEqual(target.raw, {
            "_key": "target",
            "matcher": {
                "type": "solarsystem",
                "acceptedValueTypes": ["solarsystem"],
                "optional": False,
                "maxEntries": 1,
                "title": {"en": "Target System"},
                "description": {"en": "Pick a system"},
            },
        })

    def test_boolean_parameter_falls_back_to_choice_label_as_title(self):
        FreelanceJobSchemaParameter.load_from_sde(self.tmpdir)

        confirm = FreelanceJobSchemaParameter.objects.get(pk="BoostShield:confirm")
        self.assertEqual(confirm.kind, "boolean")
        self.assertEqual(confirm.title, "Confirm?")

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        FreelanceJobSchemaParameter.load_from_sde(self.tmpdir)
        FreelanceJobSchemaParameter.load_from_sde(self.tmpdir)

        self.assertEqual(FreelanceJobSchemaParameter.objects.count(), 2)

    def test_str(self):
        FreelanceJobSchemaParameter.load_from_sde(self.tmpdir)
        target = FreelanceJobSchemaParameter.objects.get(pk="BoostShield:target")
        self.assertEqual(str(target), "BoostShield:target")


class ImportOptionalModelTests(TestCase):
    """
    _import_optional_model is what keeps the character/corporation/alliance/
    faction entries from being a hard AllianceAuth dependency: importing
    eve_sde.models must not crash just because AllianceAuth (or whatever a
    project points these settings at) isn't installed - it should degrade to
    None for that one value type instead.
    """

    def test_resolves_a_real_dotted_path(self):
        self.assertIs(_import_optional_model("eve_sde.models.lore.Archetype"), Archetype)

    def test_returns_none_for_an_unimportable_path(self):
        self.assertIsNone(_import_optional_model("not_an_installed_package.models.Something"))

    def test_returns_none_when_unset(self):
        self.assertIsNone(_import_optional_model(None))
        self.assertIsNone(_import_optional_model(""))


class BuildValueTypeModelsTests(TestCase):

    def test_ships_null_for_a_value_type_whose_model_setting_is_unimportable(self):
        with mock.patch(
            "eve_sde.models.freelance.ESDE_FREELANCE_FACTION_MODEL",
            "not_an_installed_package.models.Something",
        ):
            result = _build_value_type_models()

        self.assertIsNone(result["faction"])
        # unrelated entries are untouched
        self.assertIs(result["solarsystem"], SolarSystem)
