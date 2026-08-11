"""
    Standalone lookup/enum tables from the SDE that don't belong under any
    of the other groupings (types, map, lore, industry, freelance, sovereignty).
"""
# Django
from django.db import models

# Django EVE SDE
from eve_sde.models.base import JSONModel
from eve_sde.models.types import TypeBase


class AccountingEntryType(TypeBase):
    """
    accountingEntryTypes.jsonl
        _key : int
        internalName : str
        name : dict
            ...
        journalMessage : dict
            ...
        description : dict
            ...
    """
    # JsonL Params
    class Import:
        filename = "accountingEntryTypes.jsonl"
        lang_fields = ["name", "description", ("journal_message", "journalMessage")]
        data_map = (
            ("internal_name", "internalName"),
            ("name", "name.en"),
            ("description", "description.en"),
            ("journal_message", "journalMessage.en"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    internal_name = models.CharField(max_length=250, null=True, blank=True, default=None)
    description = models.TextField(null=True, blank=True, default=None)  # _en
    journal_message = models.TextField(null=True, blank=True, default=None)  # _en


class NotificationType(JSONModel):
    """
    notificationTypes.jsonl
        _key : int
        displayName : dict
            ...
        internalName : str
    """
    # JsonL Params
    class Import:
        filename = "notificationTypes.jsonl"
        lang_fields = [("name", "displayName")]
        data_map = (
            ("internal_name", "internalName"),
            ("name", "displayName.en"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    id = models.BigIntegerField(primary_key=True)
    # displayName is missing on a handful of rows, so name can't be non-null.
    name = models.CharField(max_length=250, null=True, blank=True, default=None, db_index=True)
    internal_name = models.CharField(max_length=250, null=True, blank=True, default=None)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f"{self.name} ({self.id})"
