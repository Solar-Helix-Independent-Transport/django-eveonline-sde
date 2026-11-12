"""
Reading the SDE REST API's JSONL (sde.evetech.net), where CCP renamed the
zip's `_key` / `_value` to real names. alias_sde_record puts `_key` /
`_value` back next to them, using the table's schema, so the loader's
existing Import configs keep working.

Schemas in test_jsons/rest_schemas are real, from release 20261111T160425Z.
Rows are real too, trimmed.
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import SimpleTestCase, TestCase

# Django EVE SDE
from eve_sde.models import (
    FreelanceJobSchema,
    FreelanceJobSchemaParameter,
    ItemType,
    Mastery,
    Planet,
    PlanetResource,
)
from eve_sde.sde_rest import alias_sde_record

SCHEMAS = os.path.join(os.path.dirname(__file__), "test_jsons", "rest_schemas")


def schema(table):
    with open(os.path.join(SCHEMAS, f"{table}.schema.json")) as f:
        return json.load(f)


def write_folder(folder, table, rows, rest):
    """An SDE folder holding `table`, REST style (with its schema) or zip style."""
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{table}.jsonl"), "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    if rest:
        shutil.copy(os.path.join(SCHEMAS, f"{table}.schema.json"), folder)
    with open(os.path.join(folder, "_sde.jsonl"), "w") as f:
        f.write(json.dumps({"_key": "sde", "buildNumber": 3687575, "releaseDate": "2026-11-11T16:04:25Z"}))


class AliasSdeRecordTests(SimpleTestCase):

    def test_top_level_key_gets_a_key_alias(self):
        row = {"typeID": 587, "groupID": 25, "mass": 1067000}

        self.assertEqual(
            alias_sde_record(row, schema("types")),
            {"typeID": 587, "groupID": 25, "mass": 1067000, "_key": 587},
        )

    def test_masteries_get_value_aliases_at_both_levels(self):
        # zip: {"_key": 587, "_value": [{"_key": 0, "_value": [96, 99]}, ...]}
        row = {"typeID": 587, "levels": [
            {"level": 0, "certificateIDs": [96, 99]},
            {"level": 4, "certificateIDs": [96, 117]},
        ]}

        out = alias_sde_record(row, schema("masteries"))

        self.assertEqual(out["_key"], 587)
        self.assertEqual(
            [(_l["_key"], _l["_value"]) for _l in out["_value"]],
            [(0, [96, 99]), (4, [96, 117])],
        )
        # the real names are still there
        self.assertEqual(out["levels"][1]["certificateIDs"], [96, 117])

    def test_freelance_schemas_and_their_parameters_get_key_aliases(self):
        # zip: {"_key": 1, "_value": [{"_key": "BoostShield", "parameters": [{"_key": "solarsystem", ...}]}]}
        row = {"major": 1, "schemas": [{
            "name": "BoostShield",
            "iconID": "shields",
            "parameters": [
                {"key": "solarsystem", "matcher": {"iconID": "location"}},
                {"key": "ship", "boolean": {"iconID": "ship"}},
            ],
        }]}

        out = alias_sde_record(row, schema("freelanceJobSchemas"))

        job = out["_value"][0]
        self.assertEqual(job["_key"], "BoostShield")
        self.assertEqual([_p["_key"] for _p in job["parameters"]], ["solarsystem", "ship"])

    def test_zip_row_is_left_alone(self):
        row = {"_key": 587, "_value": [{"_key": 0, "_value": [96]}]}

        self.assertEqual(
            alias_sde_record(row, schema("masteries")),
            {"_key": 587, "_value": [{"_key": 0, "_value": [96]}]},
        )

    def test_row_missing_the_schema_key_is_logged(self):
        # CCP renamed the key again, or the schema and data disagree
        row = {"type_id": 587, "groupID": 25}

        with self.assertLogs("eve_sde.sde_rest", level="WARNING") as logs:
            out = alias_sde_record(row, schema("types"))

        self.assertEqual(out, {"type_id": 587, "groupID": 25})
        self.assertIn("typeID", logs.output[0])


class LoadFromRestFolderTests(TestCase):
    """
    A model loaded from a REST folder (renamed keys + schema) ends up with
    the same rows as from the same data in zip shape.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def assertLoadsTheSame(self, models, table, zip_rows, rest_rows):
        """Load zip_rows, then rest_rows into an empty DB, and compare every model's rows."""
        def load(rows, rest):
            folder = os.path.join(self.tmpdir, "rest" if rest else "zip")
            write_folder(folder, table, rows, rest)
            for mdl in models:
                mdl.load_from_sde(folder)
            out = {
                mdl.__name__: sorted(
                    mdl.objects.values_list(*[
                        _f.attname for _f in mdl._meta.concrete_fields if not _f.auto_created
                    ]),
                    key=repr,
                )
                for mdl in models
            }
            for mdl in reversed(models):
                mdl.objects.all().delete()
            return out

        from_zip = load(zip_rows, rest=False)
        from_rest = load(rest_rows, rest=True)
        for mdl in models:
            self.assertTrue(from_zip[mdl.__name__], f"{mdl.__name__} loaded nothing")
        self.assertEqual(from_rest, from_zip)

    def test_item_type(self):
        self.assertLoadsTheSame(
            [ItemType], "types",
            zip_rows=[{
                "_key": 587, "groupID": 25, "mass": 1067000.0,
                "name": {"en": "Rifter", "de": "Rifter"}, "published": True,
            }],
            rest_rows=[{
                "typeID": 587, "groupID": 25, "mass": 1067000,
                "name": {"en": "Rifter", "de": "Rifter"}, "published": True,
            }],
        )

    def test_mastery(self):
        self.assertLoadsTheSame(
            [Mastery], "masteries",
            zip_rows=[{"_key": 587, "_value": [{"_key": 0, "_value": [96, 99]}, {"_key": 4, "_value": [117]}]}],
            rest_rows=[{"typeID": 587, "levels": [
                {"level": 0, "certificateIDs": [96, 99]}, {"level": 4, "certificateIDs": [117]}]}],
        )

    def test_freelance_schemas_and_parameters(self):
        title = {"en": "Solar System", "de": "Sonnensystem"}

        job = {"iconID": "shields", "contentTags": ["activity_logistics"], "title": {"en": "BoostShield"}}
        matcher = {"matcher": {"title": title}}
        boolean = {"boolean": {"choiceLabel": title}}

        self.assertLoadsTheSame(
            [FreelanceJobSchema, FreelanceJobSchemaParameter], "freelanceJobSchemas",
            zip_rows=[{"_key": 1, "_value": [
                job | {"_key": "BoostShield", "parameters": [
                    {"_key": "solarsystem"} | matcher,
                    {"_key": "ship"} | boolean,
                ]},
            ]}],
            rest_rows=[{"major": 1, "schemas": [
                job | {"name": "BoostShield", "parameters": [
                    {"key": "solarsystem"} | matcher,
                    {"key": "ship"} | boolean,
                ]},
            ]}],
        )

    def test_planet_resources_only_load_planets(self):
        # one file holds planets and stars, field_filters on _key keeps the planets
        Planet.objects.create(id=40000002)
        self.assertLoadsTheSame(
            [PlanetResource], "planetResources",
            zip_rows=[
                {"_key": 40000002, "power": 10, "workforce": 5},
                {"_key": 40000001, "power": 99},  # a star
            ],
            rest_rows=[
                {"celestialID": 40000002, "power": 10, "workforce": 5},
                {"celestialID": 40000001, "power": 99},
            ],
        )
