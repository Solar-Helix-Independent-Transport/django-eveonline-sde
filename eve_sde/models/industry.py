"""Industry and blueprint-related SDE models."""

# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# Django EVE SDE
from eve_sde.models.base import JSONModel
from eve_sde.models.types import ItemType


class BlueprintActivity(JSONModel):
    """
    blueprints.jsonl
        _key : int
        activities : dict
            <activity_name> : dict
        blueprintTypeID : int
        maxProductionLimit : int
    """
    class Activities(models.TextChoices):
        manufacturing = "manufacturing", _("Manufacturing")
        research_time = "research_time", _("Researching Time Efficiency")
        research_material = "research_material", _("Researching Material Efficiency")
        copying = "copying", _("Copying")
        invention = "invention", _("Invention")
        reaction = "reaction", _("Reaction")

    class Import:
        filename = "blueprints.jsonl"
        lang_fields = False
        data_map = (
            ("activity", "activity"),
            ("time", "time"),
            ("blueprint_item_type_id", "blueprintTypeID"),
            ("max_production_limit", "maxProductionLimit"),
        )
        update_fields = ["time", "max_production_limit"]
        custom_names = False

    @staticmethod
    def build_pk(bp_id: int, activity: str):
        return f"{bp_id}:{activity}"

    # PK
    id = models.CharField(
        max_length=25,
        unique=True,
        primary_key=True,
    )
    activity = models.CharField(
        max_length=20,
        choices=Activities.choices
    )

    # Fields
    blueprint_item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="blueprint_activities",
        null=True,
        blank=True,
        default=None,
    )
    time = models.IntegerField(null=True, blank=True, default=None)
    max_production_limit = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        for activity_name, activity_data in json_data.get("activities", {}).items():
            _base = {
                "activity": activity_name,
                "time": activity_data.get("time"),
                "_key": cls.build_pk(json_data.get("_key"), activity_name),
            }
            _out.append(cls.map_to_model(json_data | _base))

        return _out


class BlueprintActivityProduct(JSONModel):
    """
    # Is Deleted and reloaded on updates. Don't F-Key to this model.
    blueprints.jsonl
        _key : int
        activities : dict
            <activity_name> : dict
                products : list
                    typeID : int
                    quantity : int
                    probability : float
    """

    class Import:
        filename = "blueprints.jsonl"
        lang_fields = False
        data_map = (
            ("blueprint_activity_id", "blueprint_activity_id"),  # Added manually
            ("item_type_id", "typeID"),
            ("quantity", "quantity"),
            ("probability", "probability"),
        )
        update_fields = False
        custom_names = False

    blueprint_activity = models.ForeignKey(
        BlueprintActivity,
        related_name="products",
        on_delete=models.CASCADE
    )

    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None,
    )
    quantity = models.IntegerField(null=True, blank=True, default=None)
    probability = models.FloatField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []

        for activity_name, activity_data in json_data.get("activities", {}).items():
            if "products" in activity_data:
                _activity = {
                    "blueprint_activity_id": BlueprintActivity.build_pk(json_data.get("_key"), activity_name),
                }
                for product in activity_data.get("products", []):
                    if product.get("typeID") not in cls.pks:
                        product["typeID"] = None
                    _out.append(cls.map_to_model(product | _activity, pk=False))

        return _out

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            gate_qry._raw_delete(gate_qry.db)

        # there is a bad typeID in the product list.
        # we will just ignore them

        cls.pks = set(
            ItemType.objects.all().values_list("pk", flat=True)
        )
        super().load_from_sde(folder_name)

    def __str__(self):
        return (
            f"{self.blueprint_activity.blueprint_item_type.name} -> {self.item_type.name} "
            f"(p={self.probability}, qty={self.quantity})"
        )


class BlueprintActivityMaterial(JSONModel):
    """
    # Is Deleted and reloaded on updates. Don't F-Key to this model.

    blueprints.jsonl
        _key : int
        activities : dict
            <activity_name> : dict
                materials : list
                    typeID : int
                    quantity : int
    """

    class Import:
        filename = "blueprints.jsonl"
        lang_fields = False
        data_map = (
            ("blueprint_activity_id", "blueprint_activity_id"),
            ("item_type_id", "typeID"),
            ("quantity", "quantity"),
        )
        update_fields = False
        custom_names = False

    blueprint_activity = models.ForeignKey(
        BlueprintActivity,
        related_name="materials",
        on_delete=models.CASCADE
    )

    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None,
    )
    quantity = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []

        for activity_name, activity_data in json_data.get("activities", {}).items():
            if "materials" in activity_data:
                _activity = {
                    "blueprint_activity_id": BlueprintActivity.build_pk(json_data.get("_key"), activity_name),
                }
                for material in activity_data.get("materials", []):
                    if material.get("typeID") not in cls.pks:
                        material["typeID"] = None
                    _out.append(cls.map_to_model(material | _activity, pk=False))

        return _out

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            gate_qry._raw_delete(gate_qry.db)

        # there is a bad typeID in the materials list.
        # we will just ignore them
        # 3927 - Clones  (met: 3924)
        cls.pks = set(
            ItemType.objects.all().values_list("pk", flat=True)
        )
        super().load_from_sde(folder_name)

    def __str__(self):
        return (
            f"{self.blueprint_activity.blueprint_item_type.name} <- {self.item_type.name if self.item_type else 'Unknown Type'} "
            f"(qty={self.quantity})"
        )
