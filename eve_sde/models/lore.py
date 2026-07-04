"""
    Misc reference/lore models from the SDE, referenced by other SDE data
    (e.g. Freelance Job parameters) but not tied to the map or item type trees.
"""
# Django
from django.db import models

from .base import JSONModel


class Archetype(JSONModel):
    """
    archetypes.jsonl
        _key : int
        title : dict
            ...
        description : dict
            ...
    """
    # JsonL Params
    class Import:
        filename = "archetypes.jsonl"
        lang_fields = [("name", "title"), "description"]
        data_map = (
            ("name", "title.en"),
            ("description", "description.en"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=250, null=True, blank=True, default=None, db_index=True)
    description = models.TextField(null=True, blank=True, default=None)  # _en

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f"{self.name} ({self.id})"
