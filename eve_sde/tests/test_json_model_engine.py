"""
Tests for the generic JSONModel import engine in models/base.py: the
map_to_model/format_name/get_data_fields/is_equal/load_extra machinery
shared by every concrete SDE model, plus the multi-row-per-line and
extra-data-merge paths in load_from_sde that no existing model test
happened to exercise.

Every test here uses a real, already-migrated SDE model rather than a
throwaway test-only model class - a JSONModel subclass defined only for a
test is still a real Django model as far as JSONModel.__subclasses__() is
concerned (that's exactly what eve_sde_model_stats walks), so an unmigrated
one crashes that command for the rest of the test run. Real models sidestep
that entirely and exercise the same base-class code paths.
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
from eve_sde.models.base import JSONModel
from eve_sde.models.industry import BlueprintActivity
from eve_sde.models.lore import Archetype
from eve_sde.models.map import Planet, SolarSystem
from eve_sde.models.sovereignty import SovereigntyUpgrade
from eve_sde.models.types import ItemCategory, ItemType


class MapToModelCustomNamesTests(TestCase):
    """
    Planet is a real model with custom_names=True: it derives its own name
    from its solar system's name plus a roman-numeral celestial index,
    via its own format_name() override - map_to_model's custom_names
    branch calls into that polymorphically, same as it would for any model.
    """

    def test_custom_names_builds_the_name_from_the_solar_system_lookup(self):
        SolarSystem.objects.create(id=30000142, name="Jita", name_en="Jita")
        name_lookup = Planet.name_lookup()

        data = {"_key": 1, "solarSystemID": 30000142, "celestialIndex": 4}
        instance = Planet.from_jsonl(data, name_lookup)

        self.assertEqual(instance.name, "Jita IV")


class MapToModelTupleLangFieldsTests(TestCase):
    """
    Archetype mixes the plain-string lang_fields form ("description") with
    the (field, json_key) tuple form (("name", "title")) - its per-language
    "name" values are read from the "title" key in the jsonl row, not "name".
    """

    def test_tuple_form_lang_field_uses_its_own_json_key(self):
        data = {
            "title": {"en": "Archetype EN", "de": "Archetype DE"},
            "description": {"en": "Desc EN", "de": "Desc DE"},
        }

        instance = Archetype.from_jsonl(data)

        self.assertEqual(instance.name, "Archetype EN")  # from data_map's "title.en"
        self.assertEqual(instance.name_de, "Archetype DE")  # from the lang_fields tuple
        self.assertEqual(instance.description, "Desc EN")
        self.assertEqual(instance.description_de, "Desc DE")


class FromJsonlNotImplementedTests(TestCase):

    def test_raises_when_no_data_map_is_configured(self):
        # JSONModel.Import.data_map defaults to False - calling the base
        # class's own from_jsonl directly hits that guard with no need for
        # any (mis)configured subclass.
        with self.assertRaises(AttributeError):
            JSONModel.from_jsonl({})


class FormatNameTests(TestCase):
    """format_name is inherited as-is by any model that doesn't override it
    (Archetype doesn't) - calling it directly exercises both branches."""

    def test_no_lang_returns_plain_name_key(self):
        self.assertEqual(
            Archetype.format_name({"name": "Plain"}, False),
            "Plain",
        )

    def test_with_lang_returns_suffixed_name_key(self):
        self.assertEqual(
            Archetype.format_name({"name_fr": "Nom"}, False, lang="fr"),
            "Nom",
        )


class LocalizedNameTests(TestCase):

    def test_wraps_name_through_gettext(self):
        category = ItemCategory(id=1, name="Tritanium")
        self.assertEqual(category.localized_name, "Tritanium")


class IsEqualTests(TestCase):

    def test_update_fields_branch_detects_a_difference(self):
        old = BlueprintActivity(pk="1:manufacturing", time=100, max_production_limit=10)
        new_same = BlueprintActivity(pk="1:manufacturing", time=100, max_production_limit=10)
        new_diff = BlueprintActivity(pk="1:manufacturing", time=200, max_production_limit=10)

        self.assertTrue(BlueprintActivity.is_equal(new_same, old))
        self.assertFalse(BlueprintActivity.is_equal(new_diff, old))

    def test_data_map_branch_detects_a_difference(self):
        old = ItemCategory(id=1, name="Tritanium", published=True, icon_id=1)
        new_same = ItemCategory(id=1, name="Tritanium", published=True, icon_id=1)
        new_diff = ItemCategory(id=1, name="Tritanium", published=False, icon_id=1)

        self.assertTrue(ItemCategory.is_equal(new_same, old))
        self.assertFalse(ItemCategory.is_equal(new_diff, old))


class LoadExtraTests(TestCase):

    def test_success_returns_id_keyed_field_dict(self):
        fake_response = mock.MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"100001": 12.5}

        with mock.patch("eve_sde.models.base.httpx.get", return_value=fake_response):
            result = ItemType.load_extra()

        self.assertEqual(result, {100001: {"packaged_volume": 12.5}})

    def test_non_200_status_is_logged_and_skipped(self):
        fake_response = mock.MagicMock()
        fake_response.status_code = 404

        with mock.patch("eve_sde.models.base.httpx.get", return_value=fake_response):
            result = ItemType.load_extra()

        self.assertEqual(result, {})

    def test_request_exception_is_logged_and_does_not_raise(self):
        with mock.patch("eve_sde.models.base.httpx.get", side_effect=RuntimeError("network down")):
            result = ItemType.load_extra()

        self.assertEqual(result, {})

    def test_no_extra_data_configured_returns_false(self):
        self.assertFalse(BlueprintActivity.load_extra())


class LoadFromSdeExtraDataMergeTests(TestCase):

    def test_extra_field_is_merged_into_the_row_before_mapping(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))
        with open(os.path.join(tmpdir, "types.jsonl"), "w") as f:
            f.write(json.dumps({"_key": 100001, "name": {"en": "Test Widget"}, "published": True}) + "\n")

        fake_response = mock.MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"100001": 12.5}

        with mock.patch("eve_sde.models.base.httpx.get", return_value=fake_response):
            ItemType.load_from_sde(tmpdir)

        self.assertEqual(ItemType.objects.get(pk=100001).packaged_volume, 12.5)


class LoadFromSdeMultiRowPerLineTests(TestCase):
    """
    BlueprintActivity.from_jsonl expands one jsonl line into multiple model
    instances (one per activity) - this is the isinstance(_new, list) branch
    of load_from_sde, exercised here for both a first-time create pass and a
    second update pass so create_update's bulk_update path runs too.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

    def _write_blueprint(self, manufacturing_time):
        row = {
            "_key": 500,
            "maxProductionLimit": 10,
            "activities": {
                "manufacturing": {"time": manufacturing_time},
                "copying": {"time": 50},
            },
        }
        with open(os.path.join(self.tmpdir, "blueprints.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

    def test_first_pass_creates_one_row_per_activity(self):
        self._write_blueprint(manufacturing_time=100)

        BlueprintActivity.load_from_sde(self.tmpdir)

        self.assertEqual(BlueprintActivity.objects.count(), 2)
        self.assertEqual(BlueprintActivity.objects.get(pk="500:manufacturing").time, 100)
        self.assertEqual(BlueprintActivity.objects.get(pk="500:copying").time, 50)

    def test_second_pass_updates_the_changed_row_only(self):
        self._write_blueprint(manufacturing_time=100)
        BlueprintActivity.load_from_sde(self.tmpdir)

        self._write_blueprint(manufacturing_time=200)
        BlueprintActivity.load_from_sde(self.tmpdir)

        self.assertEqual(BlueprintActivity.objects.count(), 2)
        self.assertEqual(BlueprintActivity.objects.get(pk="500:manufacturing").time, 200)
        self.assertEqual(BlueprintActivity.objects.get(pk="500:copying").time, 50)


class LoadFromSdeSingleRowUpdateTests(TestCase):
    """
    ItemCategory has no update_fields configured, so its updates go through
    create_update's data_map-derived bulk_update branch rather than an
    explicit update_fields list - and, unlike BlueprintActivity, from_jsonl
    returns a single instance rather than a list, exercising the
    single-row/pks-present branch of load_from_sde's main loop.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

    def _write_category(self, icon_id):
        row = {"_key": 1, "name": {"en": "Tritanium"}, "published": True, "iconID": icon_id}
        with open(os.path.join(self.tmpdir, "categories.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

    def test_second_pass_updates_a_changed_field_via_data_map_bulk_update(self):
        self._write_category(icon_id=1)
        ItemCategory.load_from_sde(self.tmpdir)

        self._write_category(icon_id=2)
        ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.objects.count(), 1)
        self.assertEqual(ItemCategory.objects.get(pk=1).icon_id, 2)

    def test_second_pass_with_no_changes_does_not_error(self):
        self._write_category(icon_id=1)
        ItemCategory.load_from_sde(self.tmpdir)
        ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.objects.count(), 1)
        self.assertEqual(ItemCategory.objects.get(pk=1).icon_id, 1)


class CreateUpdateNonIdPrimaryKeyTests(TestCase):
    """
    create_update's update-detection query used to hardcode id__in, which
    only works for models whose primary key column is actually named "id".
    SovereigntyUpgrade's pk is item_type (a OneToOneField with
    primary_key=True), so its Django-generated pk column is "item_type_id"
    - id__in raised FieldError against it. This exercises the real
    load_from_sde update path (not create_update directly) so it fails the
    same way the production traceback did if the regression comes back.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))
        ItemType.objects.create(id=1, name="Test Upgrade")

    def _write_upgrade(self, power_production):
        row = {
            "_key": 1,
            "fuel": {"hourly_upkeep": 10, "startup_cost": 5, "type_id": None},
            "mutually_exclusive_group": "group_a",
            "power_production": power_production,
            "power_allocation": 1,
            "workforce_production": 1,
            "workforce_allocation": 1,
        }
        with open(os.path.join(self.tmpdir, "sovereigntyUpgrades.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

    def test_second_pass_update_does_not_raise_field_error(self):
        self._write_upgrade(power_production=100)
        SovereigntyUpgrade.load_from_sde(self.tmpdir)

        self._write_upgrade(power_production=200)
        SovereigntyUpgrade.load_from_sde(self.tmpdir)

        self.assertEqual(SovereigntyUpgrade.objects.count(), 1)
        self.assertEqual(SovereigntyUpgrade.objects.get(pk=1).power_production, 200)


class LoadFromSdeChunkedFlushTests(TestCase):

    def test_flushes_mid_loop_when_chunk_size_is_small(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))
        with open(os.path.join(tmpdir, "categories.jsonl"), "w") as f:
            for i in range(1, 4):
                f.write(json.dumps({"_key": i, "name": {"en": f"Cat {i}"}, "published": True, "iconID": i}) + "\n")

        with mock.patch("eve_sde.models.base.ESDE_CHUNK_SIZE", 1):
            ItemCategory.load_from_sde(tmpdir)

        self.assertEqual(ItemCategory.objects.count(), 3)
