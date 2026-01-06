"""
    Eve type models
"""
# Django
from django.db import models

from .base import JSONModel


class TypeBase(JSONModel):
    id = models.BigIntegerField(
        primary_key=True
    )

    name = models.CharField(
        max_length=250
    )

    class Meta:
        abstract = True
        default_permissions = ()

    def __str__(self):
        return f"{self.name} ({self.id})"


class ItemCategory(TypeBase):
    """
    categories.jsonl
        _key : int
        name : dict
            ...
        published : bool
        iconID : int
    """
    # JsonL Params
    class Import:
        filename = "categories.jsonl"
        lang_fields = ["name"]
        data_map = (
            ("name", "name.en"),
            ("published", ("published", False)),
            ("icon_id", "iconID"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    published = models.BooleanField(default=False)
    icon_id = models.IntegerField(null=True, blank=True, default=None)


class ItemGroup(TypeBase):
    """
    groups.jsonl
        _key : int
        anchorable : bool
        anchored : bool
        categoryID : int
        fittableNonSingleton : bool
        name : dict
            ...
        published : bool
        useBasePrice : bool
        iconID : int
    """
    # JsonL Params
    class Import:
        filename = "groups.jsonl"
        lang_fields = ["name"]
        data_map = (
            ("anchorable", "anchorable"),
            ("anchored", "anchored"),
            ("category_id", "categoryID"),
            ("fittable_non_singleton", "fittableNonSingleton"),
            ("icon_id", "iconID"),
            ("name", "name.en"),
            ("published", "published"),
            ("use_base_price", "useBasePrice"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    anchorable = models.BooleanField(default=False)
    anchored = models.BooleanField(default=False)
    category = models.ForeignKey(ItemCategory, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    fittable_non_singleton = models.BooleanField(default=False)
    icon_id = models.IntegerField(null=True, blank=True, default=None)
    published = models.BooleanField(default=False)
    use_base_price = models.BooleanField(default=False)


class ItemType(TypeBase):
    """
    types.jsonl
        _key : int
        groupID : int
        mass : float
        name : dict
            ...
        portionSize : int
        published : bool
        volume : float
        radius : float
        description : dict
            ...
        graphicID : int
        soundID : int
        iconID : int
        raceID : int
        basePrice : float
        marketGroupID : int
        capacity : float
        metaGroupID : int
        variationParentTypeID : int
        factionID : int

    """
    # JsonL Params
    class Import:
        filename = "types.jsonl"
        lang_fields = ["name", "description"]
        data_map = (
            ("base_price", "basePrice"),
            ("capacity", "capacity"),
            ("description", "description.en"),
            ("faction_id_raw", "factionID"),
            ("graphic_id", "graphicID"),
            ("group_id", "groupID"),
            ("icon_id", "iconID"),
            ("market_group_id_raw", "marketGroupID"),
            ("mass", "mass"),
            ("meta_group_id_raw", "metaGroupID"),
            ("name", "name.en"),
            ("portion_size", "portionSize"),
            ("published", "published"),
            ("race_id", "raceID"),
            ("radius", "radius"),
            ("sound_id", "soundID"),
            ("variation_parent_type_id", "variationParentTypeID"),
            ("volume", "volume"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    base_price = models.FloatField(null=True, blank=True, default=None)
    capacity = models.FloatField(null=True, blank=True, default=None)
    description = models.TextField(null=True, blank=True, default=None)  # _en
    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    graphic_id = models.IntegerField(null=True, blank=True, default=None)
    group = models.ForeignKey(ItemGroup, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    icon_id = models.IntegerField(null=True, blank=True, default=None)
    market_group_id_raw = models.IntegerField(null=True, blank=True, default=None)
    mass = models.FloatField(null=True, blank=True, default=None)
    meta_group_id_raw = models.IntegerField(null=True, blank=True, default=None)
    portion_size = models.IntegerField(null=True, blank=True, default=None)
    published = models.BooleanField(default=False)
    race_id = models.IntegerField(null=True, blank=True, default=None)
    radius = models.FloatField(null=True, blank=True, default=None)
    sound_id = models.IntegerField(null=True, blank=True, default=None)
    variation_parent_type_id = models.IntegerField(null=True, blank=True, default=None)
    volume = models.FloatField(null=True, blank=True, default=None)


class ItemTypeMaterials(JSONModel):
    """
    # Is Deleted and reloaded on updates. Don't F-Key to this model.
    typeMaterials.jsonl
        _key : int
        materials : list
            materialTypeID: int
            quantity: int
        randomizedMaterials : list
            materialTypeID: int
            quantityMax: int
            quantityMin: int
    """
    # JsonL Params
    class Import:
        filename = "typeMaterials.jsonl"
        lang_fields = False
        data_map = (
            ("item_type_id", "_key"),
            ("material_item_type_id", "materialTypeID"),
            ("quantity", "quantity"),
            ("quantity_max", "quantityMax"),
            ("quantity_min", "quantityMin"),
        )
        update_fields = False
        custom_names = False

    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="materials",
        null=True,
        blank=True,
        default=None
    )
    material_item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )
    quantity = models.IntegerField(null=True, blank=True, default=None)

    quantity_max = models.IntegerField(null=True, blank=True, default=None)
    quantity_min = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _key = {"_key": json_data.get("_key")}

        for ob in json_data.get("materials", []):
            _out.append(cls.map_to_model(ob | _key, name_lookup=name_lookup, pk=False))
        for ob in json_data.get("randomizedMaterials", []):
            _out.append(cls.map_to_model(ob | _key, name_lookup=name_lookup, pk=False))

        return _out

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            # speed and we are not caring about f-keys or signals on these models
            gate_qry._raw_delete(gate_qry.db)
        super().load_from_sde(folder_name)

    class Meta:
        default_permissions = ()

    def __str__(self):
        qty = f" x {self.quantity}"
        if self.quantity_max and self.quantity_min:
            qty = f" x ({self.quantity_min} - {self.quantity_max})"
        return f"{self.item_type.name} ({self.material_item_type.name}{qty})"


class DogmaAttributeCategory(TypeBase):
    """
    dogmaAttributeCategories.jsonl
        _key : int
        description : str
        name : str
    """
    # JsonL Params
    class Import:
        filename = "dogmaAttributeCategories.jsonl"
        lang_fields = False
        data_map = (
            ("description", "description"),
            ("name", "name"),
        )
        update_fields = False
        custom_names = False

    description = models.TextField(null=True, blank=True, default=None)  # _en


class DogmaUnit(TypeBase):
    """
    dogmaUnits.jsonl
        _key : int
        description : dict
            ...
        displayName : dict
            ...
        name : str
    """
    # JsonL Params
    class Import:
        filename = "dogmaUnits.jsonl"
        lang_fields = [("display_name", "displayName"), "description"]
        data_map = (
            ("name", "name"),
        )
        update_fields = False
        custom_names = False

    description = models.TextField(null=True, blank=True, default=None)  # _en
    display_name = models.CharField(max_length=250, null=True, blank=True, default=None)  # _en


class DogmaAttribute(TypeBase):
    """
    dogmaAttributes.jsonl
        _key : int
        attributeCategoryID : int
        dataType : int
        defaultValue : float
        description : str
        displayWhenZero : bool
        highIsGood : bool
        name : str
        published : bool
        stackable : bool
        displayName : dict
            ...
        iconID : int
        tooltipDescription : dict
            ...
        tooltipTitle : dict
            ...
        unitID : int
        chargeRechargeTimeID : int
        maxAttributeID : int
    """
    class Import:
        filename = "dogmaAttributes.jsonl"
        lang_fields = [
            ("tooltip_description", "tooltipDescription"),
            ("tooltip_title", "tooltipTitle"),
            ("display_name", "displayName"),
        ]
        data_map = (
            ("attribute_category_id", "attributeCategoryID"),
            ("chargeRecharge_time_id", "chargeRechargeTimeID"),
            ("data_type_id_raw", "dataType"),
            ("default_value", "defaultValue"),
            ("description", "description"),
            ("display_when_zero", "displayWhenZero"),
            ("high_is_good", "highIsGood"),
            ("icon_id", "iconID"),
            ("max_attribute_id_raw", "maxAttributeID"),
            ("name", "name"),
            ("published", "published"),
            ("stackable", "stackable"),
            ("unit_id", "unitID"),
        )
        update_fields = False
        custom_names = False

    attribute_category = models.ForeignKey(
        DogmaAttributeCategory,
        null=True,
        blank=True,
        default=None,
        on_delete=models.CASCADE
    )
    chargeRecharge_time_id = models.IntegerField(null=True, blank=True, default=None)  # _en
    data_type_id_raw = models.IntegerField(null=True, blank=True, default=None)
    default_value = models.FloatField(null=True, blank=True, default=None)
    description = models.TextField(null=True, blank=True, default=None)  # _en
    display_name = models.CharField(max_length=250, null=True, blank=True, default=None)  # _en
    display_when_zero = models.BooleanField(null=True, blank=True, default=None)
    high_is_good = models.BooleanField(null=True, blank=True, default=None)
    icon_id = models.IntegerField(null=True, blank=True, default=None)  # _en
    max_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)  # _en
    published = models.BooleanField(null=True, blank=True, default=None)
    stackable = models.BooleanField(null=True, blank=True, default=None)
    tooltip_description = models.TextField(max_length=250, null=True, blank=True, default=None)  # _en
    tooltip_title = models.CharField(max_length=250, null=True, blank=True, default=None)  # _en
    unit = models.ForeignKey(DogmaUnit, null=True, blank=True, default=None, on_delete=models.CASCADE)


# class DogmaEffect(TypeBase):
#     """
#     dogmaEffects.jsonl
#         _key : int
#         disallowAutoRepeat : bool
#         dischargeAttributeID : int
#         durationAttributeID : int
#         effectCategoryID : int
#         electronicChance : bool
#         guid : str
#         isAssistance : bool
#         isOffensive : bool
#         isWarpSafe : bool
#         name : str
#         propulsionChance : bool
#         published : bool
#         rangeChance : bool
#         distribution : int
#         falloffAttributeID : int
#         rangeAttributeID : int
#         trackingSpeedAttributeID : int
#         description : dict
#             description.de : str
#             description.en : str
#             description.es : str
#             description.fr : str
#             description.ja : str
#             description.ko : str
#             description.ru : str
#             description.zh : str
#         displayName : dict
#             displayName.de : str
#             displayName.en : str
#             displayName.es : str
#             displayName.fr : str
#             displayName.ja : str
#             displayName.ko : str
#             displayName.ru : str
#             displayName.zh : str
#         iconID : int
#         * modifierInfo : list
#         npcUsageChanceAttributeID : int
#         npcActivationChanceAttributeID : int
#         fittingUsageChanceAttributeID : int
#         resistanceAttributeID : int
#     """
#     # JsonL Params
#     class Import:
#         filename = "dogmaUnits.jsonl"
#         lang_fields = [("display_name", "displayName"), "description"]
#         data_map = (
#             ("name", "name"),
#             # TODO this...
#         )
#         update_fields = False
#         custom_names = False

#     description = models.TextField(null=True, blank=True, default=None)  # _en
#     display_name = models.CharField(max_length=250, null=True, blank=True, default=None)  # _en

#     disallow_auto_repeat = models.BooleanField(null=True, blank=True, default=None)

#     discharge_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     duration_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     effect_category_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     electronic_chance = models.BooleanField(null=True, blank=True, default=None)
#     guid = models.CharField(max_length=250, null=True, blank=True, default=None)
#     is_assistance = models.BooleanField(null=True, blank=True, default=None)
#     is_offensive = models.BooleanField(null=True, blank=True, default=None)
#     is_offensive = models.BooleanField(null=True, blank=True, default=None)
#     is_warp_safe = models.BooleanField(null=True, blank=True, default=None)
#     propulsion_chance = models.BooleanField(null=True, blank=True, default=None)
#     published = models.BooleanField(null=True, blank=True, default=None)
#     range_chance = models.BooleanField(null=True, blank=True, default=None)
#     distribution = models.IntegerField(null=True, blank=True, default=None)
#     falloff_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     range_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     tracking_speed_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     icon_id = models.IntegerField(null=True, blank=True, default=None)
#     npc_usage_chance_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     npc_activation_chance_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     fitting_usage_chance_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)
#     resistance_attribute_id_raw = models.IntegerField(null=True, blank=True, default=None)


class TypeDogma(JSONModel):
    """
    typeDogma.jsonl
        _key : int
        dogmaAttributes : list
            attributeID: int
            value: float
        dogmaEffects : list
            effectID: int
            isDefault: bool
    """
    # JsonL Params
    class Import:
        filename = "typeDogma.jsonl"
        lang_fields = False
        data_map = (
            ("item_type_id", "_key"),
            ("value", "value"),
            ("dogma_attribute_id", "attributeID"),
        )
        update_fields = False
        custom_names = False

    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="dogma",
        null=True,
        blank=True,
        default=None
    )

    dogma_attribute = models.ForeignKey(
        DogmaAttribute,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )

    value = models.FloatField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _key = {"_key": json_data.get("_key")}

        for ob in json_data.get("dogmaAttributes", []):
            _out.append(cls.map_to_model(ob | _key, name_lookup=name_lookup, pk=False))

        return _out

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            # speed and we are not caring about f-keys or signals on these models
            gate_qry._raw_delete(gate_qry.db)
        super().load_from_sde(folder_name)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f"{self.item_type} ({self.dogma_attribute_id}: {self.dogma_attribute.name})"
