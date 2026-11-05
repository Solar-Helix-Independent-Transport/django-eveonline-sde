"""
Tests for data migrations.

0038_natural_key_constraints removes duplicate rows from the tables that
used to be wiped and reloaded, so their new unique constraints can be added
to an existing database. NULL keys never clash, so those rows are left alone.
The test DB already has the constraints, so the model is stubbed out.
"""
# Standard Library
from importlib import import_module
from unittest import mock

# Django
from django.test import SimpleTestCase

migration = import_module("eve_sde.migrations.0038_natural_key_constraints")


class RemoveDuplicatesTests(SimpleTestCase):

    def test_keeps_the_lowest_pk_for_each_natural_key(self):
        rows = {
            # (type_list_id, item_type_id, excluded, pk)
            "typelisttype": [
                (36, 63816, False, 1),
                (36, 63816, True, 2),
                (36, 63816, False, 3),
                (36, None, False, 4),
                (36, None, False, 5),
            ],
        }
        models = {}

        def get_model(app_label, model_name):
            model = mock.MagicMock()
            model.objects.order_by.return_value.values_list.return_value.iterator.return_value = (
                rows.get(model_name, [])
            )
            models[model_name] = model
            return model

        migration.remove_duplicates(mock.Mock(get_model=get_model), None)

        typelisttype = models["typelisttype"]
        typelisttype.objects.filter.assert_called_once_with(pk__in=[3])
        typelisttype.objects.filter.return_value.delete.assert_called_once_with()
        models["typedogma"].objects.filter.assert_not_called()
