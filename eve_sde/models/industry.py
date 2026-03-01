"""Industry and blueprint-related SDE models."""

# Django
from django.db import models

from .base import JSONModel
from .types import ItemType, TypeBase


class IndustryActivity(TypeBase):
    """Industry activity labels used for blueprint activities."""

    ACTIVITY_ID_TO_NAME = {
        1: "Manufacturing",
        3: "Researching Time Efficiency",
        4: "Researching Material Efficiency",
        5: "Copying",
        8: "Invention",
        9: "Reaction",
        11: "Reactions",
    }

    class Import:
        filename = "blueprints.jsonl"
        lang_fields = False
        data_map = False
        update_fields = ["name"]
        custom_names = False

    @classmethod
    def load_from_sde(cls, folder_name):
        creates = []
        updates = []

        existing = set(cls.objects.values_list("pk", flat=True))
        for activity_id, activity_name in cls.ACTIVITY_ID_TO_NAME.items():
            obj = cls(id=activity_id, name=activity_name)
            if activity_id in existing:
                updates.append(obj)
            else:
                creates.append(obj)

        cls.create_update(creates, updates)
        cls.update_sde_section_state(
            folder_name=folder_name,
            section=cls.__name__,
            total_lines=len(cls.ACTIVITY_ID_TO_NAME),
            total_rows=cls.objects.count(),
        )


class BlueprintActivityProduct(JSONModel):
    """
    blueprints.jsonl
        _key : int
        activities : dict
            <activity_name> : dict
                products : list
                    typeID : int
                    quantity : int
                    probability : float
    """

    ACTIVITY_NAME_TO_ID = {
        "manufacturing": 1,
        "research_time": 3,
        "research_material": 4,
        "copying": 5,
        "invention": 8,
        "reaction": 9,
        "reactions": 11,
    }

    class Import:
        filename = "blueprints.jsonl"
        lang_fields = False
        data_map = (
            ("eve_type_id", "blueprintTypeID"),
            ("activity_id", "activityID"),
            ("product_eve_type_id", "typeID"),
            ("quantity", "quantity"),
            ("probability", "probability"),
        )
        update_fields = False
        custom_names = False

    eve_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="industry_activity_products",
        null=True,
        blank=True,
        default=None,
    )
    activity_id = models.IntegerField(null=True, blank=True, default=None)
    activity_name = models.CharField(max_length=50, null=True, blank=True, default=None)
    product_eve_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None,
    )
    quantity = models.IntegerField(null=True, blank=True, default=None)
    probability = models.FloatField(null=True, blank=True, default=None)

    _VALID_ITEM_TYPE_IDS = None

    @classmethod
    def _valid_item_type_ids(cls):
        if cls._VALID_ITEM_TYPE_IDS is None:
            cls._VALID_ITEM_TYPE_IDS = set(
                ItemType.objects.values_list("id", flat=True)
            )
        return cls._VALID_ITEM_TYPE_IDS

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        blueprint_type_id = json_data.get("blueprintTypeID") or json_data.get("_key")
        valid_ids = cls._valid_item_type_ids()

        if blueprint_type_id not in valid_ids:
            return _out

        for activity_name, activity_data in json_data.get("activities", {}).items():
            activity_id = cls.ACTIVITY_NAME_TO_ID.get(activity_name)
            _base = {
                "blueprintTypeID": blueprint_type_id,
                "activityID": activity_id,
            }
            for product in activity_data.get("products", []):
                product_type_id = product.get("typeID")
                if product_type_id not in valid_ids:
                    continue
                _new = cls.map_to_model(product | _base, name_lookup=name_lookup, pk=False)
                _new.activity_name = activity_name
                _out.append(_new)

        return _out

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            gate_qry._raw_delete(gate_qry.db)
        super().load_from_sde(folder_name)

    class Meta:
        default_permissions = ()
        indexes = [
            models.Index(fields=["eve_type", "activity_id"]),
            models.Index(fields=["product_eve_type", "activity_id"]),
        ]

    def __str__(self):
        blueprint = self.eve_type_id
        product = self.product_eve_type_id
        return (
            f"{blueprint} -> {product} "
            f"(activity={self.activity_name or self.activity_id}, qty={self.quantity})"
        )


class BlueprintActivityMaterial(JSONModel):
    """
    blueprints.jsonl
        _key : int
        activities : dict
            <activity_name> : dict
                materials : list
                    typeID : int
                    quantity : int
    """

    ACTIVITY_NAME_TO_ID = BlueprintActivityProduct.ACTIVITY_NAME_TO_ID

    class Import:
        filename = "blueprints.jsonl"
        lang_fields = False
        data_map = (
            ("eve_type_id", "blueprintTypeID"),
            ("activity_id", "activityID"),
            ("material_eve_type_id", "typeID"),
            ("quantity", "quantity"),
        )
        update_fields = False
        custom_names = False

    eve_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="industry_activity_materials",
        null=True,
        blank=True,
        default=None,
    )
    activity_id = models.IntegerField(null=True, blank=True, default=None)
    activity_name = models.CharField(max_length=50, null=True, blank=True, default=None)
    material_eve_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None,
    )
    quantity = models.IntegerField(null=True, blank=True, default=None)

    _VALID_ITEM_TYPE_IDS = None

    @classmethod
    def _valid_item_type_ids(cls):
        if cls._VALID_ITEM_TYPE_IDS is None:
            cls._VALID_ITEM_TYPE_IDS = set(
                ItemType.objects.values_list("id", flat=True)
            )
        return cls._VALID_ITEM_TYPE_IDS

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        blueprint_type_id = json_data.get("blueprintTypeID") or json_data.get("_key")
        valid_ids = cls._valid_item_type_ids()

        if blueprint_type_id not in valid_ids:
            return _out

        for activity_name, activity_data in json_data.get("activities", {}).items():
            activity_id = cls.ACTIVITY_NAME_TO_ID.get(activity_name)
            _base = {
                "blueprintTypeID": blueprint_type_id,
                "activityID": activity_id,
            }
            for material in activity_data.get("materials", []):
                material_type_id = material.get("typeID")
                if material_type_id not in valid_ids:
                    continue
                _new = cls.map_to_model(material | _base, name_lookup=name_lookup, pk=False)
                _new.activity_name = activity_name
                _out.append(_new)

        return _out

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            gate_qry._raw_delete(gate_qry.db)
        super().load_from_sde(folder_name)

    class Meta:
        default_permissions = ()
        indexes = [
            models.Index(fields=["eve_type", "activity_id"]),
            models.Index(fields=["material_eve_type", "activity_id"]),
        ]

    def __str__(self):
        blueprint = self.eve_type_id
        material = self.material_eve_type_id
        return (
            f"{blueprint} <- {material} "
            f"(activity={self.activity_name or self.activity_id}, qty={self.quantity})"
        )
