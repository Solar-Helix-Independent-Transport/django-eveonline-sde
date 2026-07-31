"""
Tests for BlueprintActivityProduct/BlueprintActivityMaterial (industry.py):
both have a custom load_from_sde that (a) wipes and fully reloads on every
run rather than diffing, and (b) nulls out any typeID that isn't a real,
known ItemType instead of dropping the row or letting an FK violation blow
up the whole import - the SDE is known to contain a few bad references.
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.industry import (
    BlueprintActivity,
    BlueprintActivityMaterial,
    BlueprintActivityProduct,
)
from eve_sde.models.types import ItemType


class BlueprintActivityProductMaterialTestsBase(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        ItemType.objects.create(id=111, name="Good Widget")
        ItemType.objects.create(id=222, name="The Blueprint")

        row = {
            "_key": 500,
            "blueprintTypeID": 222,
            "maxProductionLimit": 10,
            "activities": {
                "manufacturing": {
                    "time": 100,
                    "products": [
                        {"typeID": 111, "quantity": 5, "probability": 1.0},
                        {"typeID": 999999, "quantity": 1, "probability": 1.0},
                    ],
                    "materials": [
                        {"typeID": 111, "quantity": 2},
                        {"typeID": 999999, "quantity": 3},
                    ],
                },
            },
        }
        with open(os.path.join(self.tmpdir, "blueprints.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        # BlueprintActivityProduct/Material both FK to a BlueprintActivity row
        BlueprintActivity.load_from_sde(self.tmpdir)


class BlueprintActivityProductTests(BlueprintActivityProductMaterialTestsBase):

    def test_unknown_type_id_is_nulled_not_dropped(self):
        BlueprintActivityProduct.load_from_sde(self.tmpdir)

        self.assertEqual(BlueprintActivityProduct.objects.count(), 2)
        good = BlueprintActivityProduct.objects.get(item_type_id=111)
        self.assertEqual(good.quantity, 5)
        self.assertEqual(good.probability, 1.0)
        bad = BlueprintActivityProduct.objects.get(item_type__isnull=True)
        self.assertEqual(bad.quantity, 1)

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        BlueprintActivityProduct.load_from_sde(self.tmpdir)
        BlueprintActivityProduct.load_from_sde(self.tmpdir)

        self.assertEqual(BlueprintActivityProduct.objects.count(), 2)

    def test_str(self):
        BlueprintActivityProduct.load_from_sde(self.tmpdir)
        good = BlueprintActivityProduct.objects.get(item_type_id=111)
        self.assertIn("Good Widget", str(good))


class BlueprintActivityMaterialTests(BlueprintActivityProductMaterialTestsBase):

    def test_unknown_type_id_is_nulled_not_dropped(self):
        BlueprintActivityMaterial.load_from_sde(self.tmpdir)

        self.assertEqual(BlueprintActivityMaterial.objects.count(), 2)
        good = BlueprintActivityMaterial.objects.get(item_type_id=111)
        self.assertEqual(good.quantity, 2)
        bad = BlueprintActivityMaterial.objects.get(item_type__isnull=True)
        self.assertEqual(bad.quantity, 3)

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        BlueprintActivityMaterial.load_from_sde(self.tmpdir)
        BlueprintActivityMaterial.load_from_sde(self.tmpdir)

        self.assertEqual(BlueprintActivityMaterial.objects.count(), 2)

    def test_str_handles_a_nulled_out_unknown_item_type(self):
        BlueprintActivityMaterial.load_from_sde(self.tmpdir)
        bad = BlueprintActivityMaterial.objects.get(item_type__isnull=True)
        self.assertIn("Unknown Type", str(bad))
