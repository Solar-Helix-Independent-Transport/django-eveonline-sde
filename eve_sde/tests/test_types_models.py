"""
Tests for the remaining under-covered models in types.py:
- ItemMarketGroup's two-pass self-referential load_from_sde (parent_group
    is a self-FK, so the first pass loads every row without it to avoid FK
    ordering issues, then a second pass fills it in).
- ItemType.market_group_id_raw.
- ItemTypeMaterials/TypeDogma/TypeEffect: each flattens a nested list out of
    one jsonl row into several model rows, and each wipes+reloads on every
    run rather than diffing (same pattern as the industry.py blueprint models).
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
    ItemMarketGroup,
    ItemType,
    ItemTypeMaterials,
    TypeDogma,
    TypeEffect,
)


class TypeBaseStrTests(TestCase):

    def test_str_includes_name_and_id(self):
        category = ItemCategory(id=6, name="Ship")
        self.assertEqual(str(category), "Ship (6)")


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
