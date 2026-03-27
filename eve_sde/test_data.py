# Standard Library
from dataclasses import dataclass

# Django
from django.apps import apps
from django.core import serializers
from django.db.models import Model

# Django EVE SDE
from eve_sde.models import JSONModel


@dataclass
class ModelSpec:
    """Defines a model to be saved in a file for testing

    model_name: the name of the model to save
    ids: the list of ids to query for on the model
    field: the field to filter on for the ids, defaults to pk
    """

    model_name: str
    ids: list[int]
    field: str | None = None


def dump_model_data(specs: list[ModelSpec]) -> str:
    """
    Saves the given model specs into a file for reuse
    """

    objects_to_dump = []
    parent_models = []
    for spec in specs:

        model = _get_model_class(spec)
        fields = {}
        if not spec.field:
            fields["pk__in"] = spec.ids
        else:
            fields[f"{spec.field}__in"] = spec.ids
        qry = model.objects.filter(**fields)
        for mdl in qry:
            parent_models += _return_all_parent_model_fields(mdl)

        parent_models.reverse()
        objects_to_dump.extend(parent_models)
        objects_to_dump.extend(qry)

    objects_to_dump = _remove_duplicates(objects_to_dump)

    serialized_data = serializers.serialize("json", objects_to_dump)

    return serialized_data


def _get_model_class(spec: ModelSpec) -> type[JSONModel]:
    """Returns the class associated with a spec"""

    model = apps.get_model("eve_sde", spec.model_name)

    if not issubclass(model, JSONModel):
        raise TypeError(f"Invalid model class {spec.model_name}")

    return model


def _return_all_parent_model_fields(model: type[Model]) -> list[type[Model]]:
    """Returns all parent models of a given model recursively"""
    parents = set()
    for f in model._meta.fields:
        if f.is_relation and f.related_model:
            _f = getattr(model, f.name, None)
            if _f:
                parents.add(_f)
                parents.update(_return_all_parent_model_fields(_f))
    return list(parents)


def _remove_duplicates(objects_to_dump: list[type[Model]]):
    """
    Removes duplicates objects from the list.
    Keeps the first object occurence.
    """

    indexes_to_remove = []
    objects_met = set()

    for i, object in enumerate(objects_to_dump):
        if object in objects_met:
            indexes_to_remove.append(i)
        else:
            objects_met.add(object)

    indexes_to_remove.reverse()

    for index in indexes_to_remove:
        del objects_to_dump[index]

    return objects_to_dump
