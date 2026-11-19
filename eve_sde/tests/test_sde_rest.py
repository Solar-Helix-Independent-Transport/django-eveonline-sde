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
from unittest import mock

# Third Party
import httpx2

# Django
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

# Django EVE SDE
from eve_sde.models import (
    Certificate,
    EveSDESection,
    FreelanceJobSchema,
    FreelanceJobSchemaParameter,
    ItemCategory,
    ItemGroup,
    ItemType,
    Mastery,
    Moon,
    Planet,
    PlanetResource,
    TypeList,
    TypeListCategory,
    TypeListType,
)
from eve_sde.sde_rest import (
    ETAG_CACHE_PREFIX,
    alias_sde_record,
    fetch_sde_release,
    get_json_conditional,
    get_sde_release,
    sde_tables_for,
)
from eve_sde.tests.rest_fakes import BASE, RELEASE, SCHEMAS, FakeCCP, schema


def write_folder(folder, table, rows, rest, versions=None):
    """
    An SDE folder holding `table`, REST style (with its schema, and the
    release and table versions in _sde.jsonl) or zip style.
    """
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{table}.jsonl"), "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    sde_info = {"_key": "sde", "buildNumber": 3687575, "releaseDate": "2026-11-11T16:04:25Z"}
    if rest:
        shutil.copy(os.path.join(SCHEMAS, f"{table}.schema.json"), folder)
        sde_info = {
            "release": RELEASE, "buildNumber": 3687575, "releaseDate": "2026-11-11T16:04:25Z",
            "versions": {table: f"v-{table}"} if versions is None else versions,
        }
    with open(os.path.join(folder, "_sde.jsonl"), "w") as f:
        f.write(json.dumps(sde_info))


class AliasSdeRecordTests(SimpleTestCase):

    def test_top_level_key_gets_a_key_alias(self):
        row = {"typeID": 587, "groupID": 25, "mass": 1067000}

        self.assertEqual(
            alias_sde_record(row, schema("types")),
            {"typeID": 587, "groupID": 25, "mass": 1067000, "_key": 587},
        )

    def test_masteries_get_key_aliases_at_both_levels(self):
        # zip: {"_key": 587, "_value": [{"_key": 0, "_value": [96, 99]}, ...]}
        row = {"typeID": 587, "levels": [
            {"level": 0, "certificateIDs": [96, 99]},
            {"level": 4, "certificateIDs": [96, 117]},
        ]}

        out = alias_sde_record(row, schema("masteries"))

        self.assertEqual(out["_key"], 587)
        self.assertEqual([_l["_key"] for _l in out["levels"]], [0, 4])

    def test_value_is_never_guessed(self):
        # the schema doesn't say which property was the zip's _value, so a
        # {key, one other} row isn't assumed to be a pair
        masteries = alias_sde_record(
            {"typeID": 587, "levels": [{"level": 0, "certificateIDs": [96]}]}, schema("masteries"))
        types = alias_sde_record({"typeID": 587, "groupID": 25}, schema("types"))

        self.assertNotIn("_value", masteries)
        self.assertNotIn("_value", masteries["levels"][0])
        self.assertNotIn("_value", types)

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

        job = out["schemas"][0]
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
        # MySQL checks foreign keys on insert, not at commit like sqlite / postgres
        ItemGroup.objects.create(id=25)
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
        ItemType.objects.create(id=587)
        for certificate_id in (96, 99, 117):
            Certificate.objects.create(id=certificate_id)
        self.assertLoadsTheSame(
            [Mastery], "masteries",
            zip_rows=[{"_key": 587, "_value": [{"_key": 0, "_value": [96, 99]}, {"_key": 4, "_value": [117]}]}],
            rest_rows=[{"typeID": 587, "levels": [
                {"level": 0, "certificateIDs": [96, 99]}, {"level": 4, "certificateIDs": [117]}]}],
        )

    def test_mastery_level_with_a_new_property_still_loads(self):
        # CCP adding a field next to certificateIDs mustn't lose the certificates
        ItemType.objects.create(id=587)
        for certificate_id in (96, 99):
            Certificate.objects.create(id=certificate_id)
        self.assertLoadsTheSame(
            [Mastery], "masteries",
            zip_rows=[{"_key": 587, "_value": [{"_key": 0, "_value": [96, 99]}]}],
            rest_rows=[{"typeID": 587, "levels": [{"level": 0, "certificateIDs": [96, 99], "note": "new"}]}],
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


class SectionStateTests(TestCase):
    """
    REST state (release + table versions) on EveSDESection only exists when
    the last load came from REST, so a later REST run never trusts hashes
    that don't describe what's in the DB.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        EveSDESection.objects.create(
            sde_section="ItemCategory", build_number=3682781, last_update="2026-11-11T08:39:00Z",
            total_lines=1, total_rows=1, release="20261111T083900Z", versions={"categories": "abc"},
        )

    def load(self, rest):
        folder = os.path.join(self.tmpdir, "rest" if rest else "zip")
        key = "categoryID" if rest else "_key"
        write_folder(folder, "categories", [{key: 6, "name": {"en": "Ship"}, "published": True}], rest)
        ItemCategory.load_from_sde(folder)
        return EveSDESection.objects.get(sde_section="ItemCategory")

    def test_zip_load_clears_rest_state(self):
        section = self.load(rest=False)

        self.assertIsNone(section.release)
        self.assertEqual(section.versions, {})
        self.assertEqual(section.build_number, 3687575)
        self.assertEqual(section.total_rows, 1)

    def test_rest_load_records_the_release_and_table_version(self):
        section = self.load(rest=True)

        self.assertEqual(section.release, RELEASE)
        self.assertEqual(section.versions, {"categories": "v-categories"})
        self.assertEqual(section.build_number, 3687575)

    def test_rest_load_records_only_the_tables_the_model_watches(self):
        folder = os.path.join(self.tmpdir, "rest")
        write_folder(folder, "mapMoons", [], rest=True, versions={
            "mapMoons": "m", "mapPlanets": "p", "mapSolarSystems": "s", "types": "t",
            "categories": "c",  # fetched for another model
        })

        Moon.load_from_sde(folder)

        section = EveSDESection.objects.get(sde_section="Moon")
        self.assertEqual(section.release, RELEASE)
        self.assertEqual(section.versions, {"mapMoons": "m", "mapPlanets": "p", "mapSolarSystems": "s", "types": "t"})


class SdeTablesForTests(SimpleTestCase):

    def test_own_table_and_everything_it_depends_on(self):
        self.assertEqual(
            sde_tables_for([Moon]),
            ["mapMoons", "mapPlanets", "mapSolarSystems", "types"],
        )

    def test_a_table_shared_by_models_is_listed_once(self):
        self.assertEqual(
            sde_tables_for([TypeList, TypeListType, TypeListCategory, ItemType]),
            ["typeLists", "types"],
        )


class FetchSdeReleaseTests(SimpleTestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.folder = os.path.join(self.tmpdir, "eve-sde")
        self.ccp = FakeCCP({
            "types": [{"typeID": 587, "groupID": 25}],
            "masteries": [{"typeID": 587, "levels": []}],
            "groups": [{"groupID": 25}],
        })
        self.ccp.install(self)

    def test_latest_release_index(self):
        index = get_sde_release()

        self.assertEqual(index["release"], RELEASE)
        self.assertEqual(index["buildNumber"], 3687575)
        self.assertEqual(index["tables"]["types"]["version"], "v-types")

    def test_fetches_only_the_tables_asked_for_from_the_pinned_release(self):
        index = get_sde_release()
        self.ccp.requested.clear()

        fetch_sde_release(index, ["types", "masteries"], self.folder)

        self.assertEqual(sorted(os.listdir(self.folder)), [
            "_sde.jsonl",
            "masteries.jsonl", "masteries.schema.json",
            "types.jsonl", "types.schema.json",
        ])
        with open(os.path.join(self.folder, "types.jsonl")) as f:
            self.assertEqual(json.loads(f.readline()), {"typeID": 587, "groupID": 25})
        self.assertEqual(self.ccp.table_urls(), ["masteries", "types"])

    def test_downloads_straight_from_the_blobs_the_versions_name(self):
        # the release URLs only 302 to these, so they're never asked for
        index = get_sde_release()
        self.ccp.requested.clear()

        fetch_sde_release(index, ["types", "masteries"], self.folder)

        self.assertEqual(sorted(self.ccp.requested), [
            "https://sde.evetech.net/blobs/v-masteries.jsonl",
            "https://sde.evetech.net/blobs/v-masteries.schema.json",
            "https://sde.evetech.net/blobs/v-types.jsonl",
            "https://sde.evetech.net/blobs/v-types.schema.json",
        ])

    def test_falls_back_to_the_release_urls_without_blobs(self):
        index = get_sde_release()
        self.ccp.blobs.clear()

        with self.assertLogs("eve_sde", level="WARNING") as logs:
            fetch_sde_release(index, ["types"], self.folder)

        with open(os.path.join(self.folder, "types.jsonl")) as f:
            self.assertEqual(json.loads(f.readline()), {"typeID": 587, "groupID": 25})
        self.assertIn(f"{BASE}/{RELEASE}/types.jsonl", self.ccp.requested)
        self.assertTrue(all(_r.levelname == "WARNING" for _r in logs.records), logs.output)

    def test_sde_file_records_the_release_and_every_table_version(self):
        fetch_sde_release(get_sde_release(), ["types", "masteries"], self.folder)

        with open(os.path.join(self.folder, "_sde.jsonl")) as f:
            self.assertEqual(json.loads(f.read()), {
                "release": RELEASE,
                "buildNumber": 3687575,
                "releaseDate": "2026-11-11T16:04:25Z",
                # groups wasn't fetched, a model depending on it still records its version
                "versions": {"types": "v-types", "masteries": "v-masteries", "groups": "v-groups"},
            })

    def test_table_not_in_the_release_is_logged_and_skipped(self):
        with self.assertLogs("eve_sde", level="ERROR"):
            fetch_sde_release(get_sde_release(), ["types", "mapPlanets"], self.folder)

        self.assertNotIn("mapPlanets.jsonl", os.listdir(self.folder))
        with open(os.path.join(self.folder, "_sde.jsonl")) as f:
            self.assertNotIn("mapPlanets", json.loads(f.read())["versions"])

    def test_missing_table_raises_and_leaves_no_partial_file(self):
        index = get_sde_release()
        self.ccp.blobs.clear()
        index["tables"]["types"]["jsonl"]["url"] = f"{BASE}/{RELEASE}/gone.jsonl"

        with self.assertRaises(httpx2.HTTPStatusError):
            fetch_sde_release(index, ["types"], self.folder)

        self.assertFalse(os.path.exists(os.path.join(self.folder, "types.jsonl")))


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ConditionalGetTests(SimpleTestCase):
    """Version checks send the last ETag and reuse the cached body on a 304."""
    URL = "https://example.test/latest.jsonl"

    def setUp(self):
        cache.clear()

    def response(self, status=200, body=None, etag=None):
        response = mock.MagicMock(status_code=status, headers={"etag": etag} if etag else {})
        response.json.return_value = body
        return response

    def test_first_get_has_no_etag_and_caches_the_body(self):
        with mock.patch.object(httpx2, "get", return_value=self.response(body={"v": 1}, etag='"a"')) as get:
            self.assertEqual(get_json_conditional(self.URL), {"v": 1})

        self.assertEqual(get.call_args.kwargs["headers"], {})
        self.assertEqual(cache.get(f"{ETAG_CACHE_PREFIX}{self.URL}"), {"etag": '"a"', "data": {"v": 1}})

    def test_not_modified_returns_the_cached_body(self):
        cache.set(f"{ETAG_CACHE_PREFIX}{self.URL}", {"etag": '"a"', "data": {"v": 1}})

        with mock.patch.object(httpx2, "get", return_value=self.response(status=304)) as get:
            self.assertEqual(get_json_conditional(self.URL), {"v": 1})

        self.assertEqual(get.call_args.kwargs["headers"], {"If-None-Match": '"a"'})

    def test_changed_file_replaces_the_cached_body(self):
        cache.set(f"{ETAG_CACHE_PREFIX}{self.URL}", {"etag": '"a"', "data": {"v": 1}})

        with mock.patch.object(httpx2, "get", return_value=self.response(body={"v": 2}, etag='"b"')):
            self.assertEqual(get_json_conditional(self.URL), {"v": 2})

        self.assertEqual(cache.get(f"{ETAG_CACHE_PREFIX}{self.URL}"), {"etag": '"b"', "data": {"v": 2}})

    def test_no_etag_is_not_cached(self):
        with mock.patch.object(httpx2, "get", return_value=self.response(body={"v": 1})):
            get_json_conditional(self.URL)

        self.assertIsNone(cache.get(f"{ETAG_CACHE_PREFIX}{self.URL}"))

    def test_broken_cache_falls_back_to_a_plain_get(self):
        with mock.patch("eve_sde.sde_rest.cache") as broken, \
                mock.patch.object(httpx2, "get", return_value=self.response(body={"v": 1}, etag='"a"')) as get:
            broken.get.side_effect = RuntimeError("redis down")
            broken.set.side_effect = RuntimeError("redis down")
            self.assertEqual(get_json_conditional(self.URL), {"v": 1})

        self.assertEqual(get.call_args.kwargs["headers"], {})
