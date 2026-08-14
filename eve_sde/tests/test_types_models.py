"""
Tests for the remaining under-covered models in types.py:
- ItemMarketGroup's two-pass self-referential load_from_sde (parent_group
    is a self-FK, so the first pass loads every row without it to avoid FK
    ordering issues, then a second pass fills it in).
- ItemType.market_group_id_raw.
- ItemTypeMaterials/TypeDogma/TypeEffect: each flattens a nested list out of
    one jsonl row into several model rows, and each wipes+reloads on every
    run rather than diffing (same pattern as the industry.py blueprint models).
- TypeList/TypeListType/TypeListGroup/TypeListCategory: each of the three
    join models flattens a pair of included/excluded ID lists (e.g.
    includedTypeIDs + excludedTypeIDs) off the same typeLists.jsonl row into
    one row per ID, with an `excluded` flag distinguishing which list it
    came from - same flatten-and-wipe pattern as the other join models, just
    two source lists merged into one instead of one.
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.types import (
    DogmaAttribute,
    DogmaEffect,
    ItemCategory,
    ItemGroup,
    ItemMarketGroup,
    ItemType,
    ItemTypeMaterials,
    TypeDogma,
    TypeEffect,
    TypeList,
    TypeListCategory,
    TypeListGroup,
    TypeListType,
)


class TypeBaseStrTests(TestCase):

    def test_str_includes_name_and_id(self):
        category = ItemCategory(id=6, name="Ship")
        self.assertEqual(str(category), "Ship (6)")


class ItemTypeRepackableAndDynamicFlagTests(TestCase):

    def test_defaults_to_false_when_absent_from_jsonl(self):
        item = ItemType.from_jsonl({"_key": 1, "name": {"en": "Widget"}})
        self.assertFalse(item.is_repackable)
        self.assertFalse(item.is_dynamic_type)

    def test_true_when_present_in_jsonl(self):
        item = ItemType.from_jsonl({
            "_key": 1, "name": {"en": "Widget"},
            "isRepackable": True, "isDynamicType": True,
        })
        self.assertTrue(item.is_repackable)
        self.assertTrue(item.is_dynamic_type)


class ItemMarketGroupTwoPassLoadTests(TestCase):

    def test_second_pass_fills_in_the_self_referential_parent(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        with open(os.path.join(tmpdir, "marketGroups.jsonl"), "w") as f:
            f.write(json.dumps({"_key": 1, "name": {"en": "Ships"}, "hasTypes": False}) + "\n")
            f.write(json.dumps({
                "_key": 2, "name": {"en": "Frigates"}, "hasTypes": True, "parentGroupID": 1,
            }) + "\n")

        ItemMarketGroup.load_from_sde(tmpdir)

        self.assertEqual(ItemMarketGroup.objects.count(), 2)
        child = ItemMarketGroup.objects.get(pk=2)
        self.assertEqual(child.parent_group_id, 1)


class ItemTypeMarketGroupIdRawTests(TestCase):

    def test_none_when_no_market_group_set(self):
        item = ItemType(id=1, name="Widget")
        self.assertIsNone(item.market_group_id_raw)

    def test_returns_the_market_group_id_when_set(self):
        group = ItemMarketGroup.objects.create(id=10, name="Ships", has_types=True)
        item = ItemType.objects.create(id=1, name="Widget", market_group=group)
        self.assertEqual(item.market_group_id_raw, 10)


class ItemTypeMaterialsTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        ItemType.objects.create(id=1, name="Widget")
        ItemType.objects.create(id=100, name="Tritanium")
        ItemType.objects.create(id=101, name="Pyerite")

        row = {
            "_key": 1,
            "materials": [{"materialTypeID": 100, "quantity": 50}],
            "randomizedMaterials": [{"materialTypeID": 101, "quantityMin": 1, "quantityMax": 5}],
        }
        with open(os.path.join(self.tmpdir, "typeMaterials.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

    def test_flattens_both_materials_lists(self):
        ItemTypeMaterials.load_from_sde(self.tmpdir)

        self.assertEqual(ItemTypeMaterials.objects.count(), 2)
        fixed = ItemTypeMaterials.objects.get(material_item_type_id=100)
        self.assertEqual(fixed.quantity, 50)
        randomized = ItemTypeMaterials.objects.get(material_item_type_id=101)
        self.assertEqual(randomized.quantity_min, 1)
        self.assertEqual(randomized.quantity_max, 5)

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        ItemTypeMaterials.load_from_sde(self.tmpdir)
        ItemTypeMaterials.load_from_sde(self.tmpdir)

        self.assertEqual(ItemTypeMaterials.objects.count(), 2)

    def test_str_reports_a_fixed_quantity(self):
        ItemTypeMaterials.load_from_sde(self.tmpdir)
        fixed = ItemTypeMaterials.objects.get(material_item_type_id=100)
        self.assertEqual(str(fixed), "Widget (Tritanium x 50)")

    def test_str_reports_a_randomized_quantity_range(self):
        ItemTypeMaterials.load_from_sde(self.tmpdir)
        randomized = ItemTypeMaterials.objects.get(material_item_type_id=101)
        self.assertEqual(str(randomized), "Widget (Pyerite x (1 - 5))")


class TypeDogmaTests(TestCase):

    def test_flattens_dogma_attributes_and_wipes_on_rerun(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        ItemType.objects.create(id=1, name="Widget")
        DogmaAttribute.objects.create(id=50, name="mass")

        row = {"_key": 1, "dogmaAttributes": [{"attributeID": 50, "value": 100.0}]}
        with open(os.path.join(tmpdir, "typeDogma.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        TypeDogma.load_from_sde(tmpdir)
        TypeDogma.load_from_sde(tmpdir)

        self.assertEqual(TypeDogma.objects.count(), 1)
        entry = TypeDogma.objects.get()
        self.assertEqual(entry.value, 100.0)
        self.assertEqual(str(entry), "Widget (1) (50: mass)")


class TypeEffectTests(TestCase):

    def test_flattens_dogma_effects_and_wipes_on_rerun(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        ItemType.objects.create(id=1, name="Widget")
        DogmaEffect.objects.create(id=60, name="onlineEffect")

        row = {"_key": 1, "dogmaEffects": [{"effectID": 60, "isDefault": True}]}
        with open(os.path.join(tmpdir, "typeDogma.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        TypeEffect.load_from_sde(tmpdir)
        TypeEffect.load_from_sde(tmpdir)

        self.assertEqual(TypeEffect.objects.count(), 1)
        entry = TypeEffect.objects.get()
        self.assertTrue(entry.is_default)
        self.assertEqual(str(entry), "Widget (1) (60: onlineEffect)")


class TypeListLoadTests(TestCase):

    def test_loads_internal_name_and_optional_display_fields(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {"_key": 4, "name": "ShipyardStructureTargets", "includedTypeIDs": [27674]}
        with open(os.path.join(tmpdir, "typeLists.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        TypeList.load_from_sde(tmpdir)

        type_list = TypeList.objects.get(pk=4)
        self.assertEqual(type_list.internal_name, "ShipyardStructureTargets")
        self.assertIsNone(type_list.name)
        self.assertIsNone(type_list.description)
        self.assertEqual(str(type_list), "ShipyardStructureTargets (4)")

    def test_display_name_and_description_populate_name_and_description(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 4,
            "name": "ShipyardStructureTargets",
            "displayName": {"en": "Shipyard Structure Targets", "de": "Werftstruktur-Ziele"},
            "displayDescription": {"en": "Valid targets for shipyard structures."},
        }
        with open(os.path.join(tmpdir, "typeLists.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        TypeList.load_from_sde(tmpdir)

        type_list = TypeList.objects.get(pk=4)
        self.assertEqual(type_list.name, "Shipyard Structure Targets")
        self.assertEqual(type_list.name_de, "Werftstruktur-Ziele")
        self.assertEqual(type_list.description, "Valid targets for shipyard structures.")


class TypeListTypeGroupCategoryLoadTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        self.type_list = TypeList.objects.create(id=6, internal_name="BehaviourStructureWeaponModules")
        ItemType.objects.create(id=100, name="Included Type")
        ItemType.objects.create(id=200, name="Excluded Type")
        ItemGroup.objects.create(id=1327, name="Included Group")
        ItemGroup.objects.create(id=1328, name="Excluded Group")
        ItemCategory.objects.create(id=7, name="Included Category")
        ItemCategory.objects.create(id=8, name="Excluded Category")

    def _write_row(self, extra):
        row = {"_key": 6, **extra}
        with open(os.path.join(self.tmpdir, "typeLists.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

    def test_type_list_type_flags_included_vs_excluded(self):
        self._write_row({"includedTypeIDs": [100], "excludedTypeIDs": [200]})

        TypeListType.load_from_sde(self.tmpdir)

        self.assertEqual(TypeListType.objects.count(), 2)
        included = TypeListType.objects.get(item_type_id=100)
        excluded = TypeListType.objects.get(item_type_id=200)
        self.assertFalse(included.excluded)
        self.assertTrue(excluded.excluded)
        self.assertEqual(str(included), "BehaviourStructureWeaponModules (included: Included Type)")
        self.assertEqual(str(excluded), "BehaviourStructureWeaponModules (excluded: Excluded Type)")

    def test_type_list_group_flags_included_vs_excluded(self):
        self._write_row({"includedGroupIDs": [1327], "excludedGroupIDs": [1328]})

        TypeListGroup.load_from_sde(self.tmpdir)

        self.assertEqual(TypeListGroup.objects.count(), 2)
        included = TypeListGroup.objects.get(item_group_id=1327)
        excluded = TypeListGroup.objects.get(item_group_id=1328)
        self.assertFalse(included.excluded)
        self.assertTrue(excluded.excluded)
        self.assertEqual(str(included), "BehaviourStructureWeaponModules (included: Included Group)")
        self.assertEqual(str(excluded), "BehaviourStructureWeaponModules (excluded: Excluded Group)")

    def test_type_list_category_flags_included_vs_excluded(self):
        self._write_row({"includedCategoryIDs": [7], "excludedCategoryIDs": [8]})

        TypeListCategory.load_from_sde(self.tmpdir)

        self.assertEqual(TypeListCategory.objects.count(), 2)
        included = TypeListCategory.objects.get(item_category_id=7)
        excluded = TypeListCategory.objects.get(item_category_id=8)
        self.assertFalse(included.excluded)
        self.assertTrue(excluded.excluded)
        self.assertEqual(str(included), "BehaviourStructureWeaponModules (included: Included Category)")
        self.assertEqual(str(excluded), "BehaviourStructureWeaponModules (excluded: Excluded Category)")

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        self._write_row({
            "includedTypeIDs": [100], "excludedTypeIDs": [200],
            "includedGroupIDs": [1327], "excludedGroupIDs": [1328],
            "includedCategoryIDs": [7], "excludedCategoryIDs": [8],
        })

        TypeListType.load_from_sde(self.tmpdir)
        TypeListType.load_from_sde(self.tmpdir)
        TypeListGroup.load_from_sde(self.tmpdir)
        TypeListGroup.load_from_sde(self.tmpdir)
        TypeListCategory.load_from_sde(self.tmpdir)
        TypeListCategory.load_from_sde(self.tmpdir)

        self.assertEqual(TypeListType.objects.count(), 2)
        self.assertEqual(TypeListGroup.objects.count(), 2)
        self.assertEqual(TypeListCategory.objects.count(), 2)
