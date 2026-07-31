"""Tests for the __str__ methods on Archetype (lore.py) and
SovereigntyUpgrade (sovereignty.py) - the only pieces of either model not
already covered elsewhere."""
# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.lore import Archetype
from eve_sde.models.sovereignty import SovereigntyUpgrade
from eve_sde.models.types import ItemType


class ArchetypeStrTests(TestCase):

    def test_str_includes_name_and_id(self):
        archetype = Archetype(id=1, name="Exploration")
        self.assertEqual(str(archetype), "Exploration (1)")


class SovereigntyUpgradeStrTests(TestCase):

    def test_str_includes_item_type_name_and_id(self):
        item_type = ItemType.objects.create(id=100, name="Cynosural Field Generator")
        upgrade = SovereigntyUpgrade.objects.create(item_type=item_type)
        self.assertEqual(str(upgrade), "Cynosural Field Generator (100)")
