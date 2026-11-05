"""
    Certificates and ship masteries from the SDE, plus the join tables that
    flatten their nested lists (skill tiers, recommended ships, mastery levels).
"""
# Django
from django.db import models

# Django EVE SDE
from eve_sde.models.base import JSONModel
from eve_sde.models.types import ItemGroup, ItemType, TypeBase


class Certificate(TypeBase):
    """
    certificates.jsonl
        _key : int
        description : dict
            ...
        groupID : int
        name : dict
            ...
        * recommendedFor : list
        * skillTypes : list
            _key : int
            basic : int
            standard : int
            improved : int
            advanced : int
            elite : int
    """
    # JsonL Params
    class Import:
        filename = "certificates.jsonl"
        lang_fields = ["name", "description"]
        data_map = (
            ("name", "name.en"),
            ("description", "description.en"),
            ("group_id", "groupID"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    description = models.TextField(null=True, blank=True, default=None)  # _en
    group = models.ForeignKey(ItemGroup, on_delete=models.SET_NULL, null=True, blank=True, default=None)


class CertificateSkill(JSONModel):
    """
    # Synced in place by natural key, rows no longer in the SDE are deleted.
    certificates.jsonl
        _key : int
        * skillTypes : list
            _key : int
            basic : int
            standard : int
            improved : int
            advanced : int
            elite : int
    """
    # JsonL Params
    class Import:
        filename = "certificates.jsonl"
        lang_fields = False
        data_map = (
            ("certificate_id", "certificateID"),
            ("item_type_id", "_key"),
            ("basic", "basic"),
            ("standard", "standard"),
            ("improved", "improved"),
            ("advanced", "advanced"),
            ("elite", "elite"),
        )
        update_fields = False
        custom_names = False
        natural_key = ("certificate_id", "item_type_id")

    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name="skills",
        null=True,
        blank=True,
        default=None
    )
    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )
    basic = models.IntegerField(null=True, blank=True, default=None)
    standard = models.IntegerField(null=True, blank=True, default=None)
    improved = models.IntegerField(null=True, blank=True, default=None)
    advanced = models.IntegerField(null=True, blank=True, default=None)
    elite = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _key = {"certificateID": json_data.get("_key")}

        for skill in json_data.get("skillTypes", []):
            _out.append(cls.map_to_model(skill | _key, name_lookup=name_lookup, pk=False))

        return _out

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["certificate", "item_type"], name="esde_certificateskill_nk"),
        ]

    def __str__(self):
        return f"{self.certificate.name} ({self.item_type.name})"


class CertificateRecommendedType(JSONModel):
    """
    # Synced in place by natural key, rows no longer in the SDE are deleted.
    certificates.jsonl
        _key : int
        * recommendedFor : list
    """
    # JsonL Params
    class Import:
        filename = "certificates.jsonl"
        lang_fields = False
        data_map = (
            ("certificate_id", "_key"),
            ("item_type_id", "typeID"),
        )
        update_fields = False
        custom_names = False
        natural_key = ("certificate_id", "item_type_id")

    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name="recommended_types",
        null=True,
        blank=True,
        default=None
    )
    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="recommended_certificates",
        null=True,
        blank=True,
        default=None
    )

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _key = {"_key": json_data.get("_key")}

        for type_id in json_data.get("recommendedFor", []):
            _out.append(cls.map_to_model({"typeID": type_id} | _key, name_lookup=name_lookup, pk=False))

        return _out

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["certificate", "item_type"], name="esde_certificaterecommendedtype_nk"),
        ]

    def __str__(self):
        return f"{self.certificate.name} ({self.item_type.name})"


class Mastery(JSONModel):
    """
    # Synced in place by natural key, rows no longer in the SDE are deleted.
    # level is the raw SDE value, 0-4 maps to in-game Mastery I-V.
    masteries.jsonl
        _key : int (shipTypeID)
        * _value : list
            _key : int (level)
            _value : list (certificateIDs)
    """
    # JsonL Params
    class Import:
        filename = "masteries.jsonl"
        lang_fields = False
        data_map = (
            ("item_type_id", "typeID"),
            ("level", "level"),
            ("certificate_id", "certificateID"),
        )
        update_fields = False
        custom_names = False
        natural_key = ("item_type_id", "level", "certificate_id")

    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="masteries",
        null=True,
        blank=True,
        default=None
    )
    level = models.IntegerField(null=True, blank=True, default=None)
    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name="masteries",
        null=True,
        blank=True,
        default=None
    )

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _type = {"typeID": json_data.get("_key")}

        for level in json_data.get("_value", []):
            for certificate_id in level.get("_value", []):
                _out.append(
                    cls.map_to_model(
                        {"level": level.get("_key"), "certificateID": certificate_id} | _type,
                        name_lookup=name_lookup,
                        pk=False
                    )
                )

        return _out

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["item_type", "level", "certificate"], name="esde_mastery_nk"),
        ]

    def __str__(self):
        return f"{self.item_type.name} (Mastery {self.level + 1}: {self.certificate.name})"
