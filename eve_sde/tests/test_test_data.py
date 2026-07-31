"""
Tests for eve_sde/test_data.py: the ModelSpec/dump_model_data utility that
downstream apps use (via the esde_generate_test_data command) to export a
small, self-contained slice of SDE data - including every parent object a
selected row's FKs point to - for use as their own test fixtures.
"""
# Standard Library
import json

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.map import Constellation, Region, SolarSystem
from eve_sde.models.types import ItemCategory
from eve_sde.test_data import (
    ModelSpec,
    _get_model_class,
    _remove_duplicates,
    _return_all_parent_model_fields,
    dump_model_data,
)


class GetModelClassTests(TestCase):

    def test_returns_the_model_class_for_a_valid_jsonmodel_spec(self):
        model = _get_model_class(ModelSpec("ItemCategory", ids=[1]))
        self.assertIs(model, ItemCategory)

    def test_raises_for_a_model_that_is_not_a_jsonmodel(self):
        # EveSDE is a real model in the eve_sde app, but it's a plain
        # SingletonModel, not part of the SDE import tree.
        with self.assertRaises(TypeError):
            _get_model_class(ModelSpec("EveSDE", ids=[1]))


class ReturnAllParentModelFieldsTests(TestCase):

    def test_recursively_collects_every_fk_ancestor(self):
        region = Region.objects.create(id=1, name="The Forge")
        constellation = Constellation.objects.create(id=2, name="Kimotoro", region=region)
        system = SolarSystem.objects.create(id=3, name="Jita", constellation=constellation)

        parents = _return_all_parent_model_fields(system)

        self.assertIn(constellation, parents)
        self.assertIn(region, parents)

    def test_returns_an_empty_list_when_there_are_no_fk_relations_set(self):
        region = Region.objects.create(id=1, name="The Forge")
        self.assertEqual(_return_all_parent_model_fields(region), [])


class RemoveDuplicatesTests(TestCase):

    def test_keeps_only_the_first_occurrence_of_each_object(self):
        region = Region.objects.create(id=1, name="The Forge")
        other = Region.objects.create(id=2, name="Domain")

        result = _remove_duplicates([region, other, region, region, other])

        self.assertEqual(result, [region, other])


class DumpModelDataTests(TestCase):

    def test_includes_the_selected_row_and_all_of_its_parents(self):
        region = Region.objects.create(id=1, name="The Forge")
        constellation = Constellation.objects.create(id=2, name="Kimotoro", region=region)
        SolarSystem.objects.create(id=3, name="Jita", constellation=constellation)

        dumped = json.loads(dump_model_data([ModelSpec("SolarSystem", ids=[3])]))

        models_present = {entry["model"] for entry in dumped}
        self.assertEqual(models_present, {"eve_sde.solarsystem", "eve_sde.constellation", "eve_sde.region"})

        pks_present = {(entry["model"], entry["pk"]) for entry in dumped}
        self.assertIn(("eve_sde.solarsystem", 3), pks_present)
        self.assertIn(("eve_sde.constellation", 2), pks_present)
        self.assertIn(("eve_sde.region", 1), pks_present)

    def test_filters_by_a_custom_field_instead_of_pk(self):
        ItemCategory.objects.create(id=1, name="Ship", icon_id=99)
        ItemCategory.objects.create(id=2, name="Module", icon_id=100)

        dumped = json.loads(dump_model_data([ModelSpec("ItemCategory", ids=[99], field="icon_id")]))

        self.assertEqual(len(dumped), 1)
        self.assertEqual(dumped[0]["pk"], 1)
