"""
Sovereignty Models
"""

# Django
from django.db import models

# Django EVE SDE
from eve_sde.models import ItemType, JSONModel


class SovereigntyUpgrade(JSONModel):
    """
    sovereigntyUpgrades.jsonl
        _key : int
        fuel : dict
            fuel.hourly_upkeep : int
            fuel.startup_cost : int
            fuel.type_id : int
        mutually_exclusive_group : str
        power_allocation : int
        workforce_allocation : int
        power_production : int
        workforce_production : int
    """

    # JsonL Params
    class Import:
        filename = "sovereigntyUpgrades.jsonl"
        lang_fields = False
        data_map = (
            ("item_type_id", "_key"),
            ("hourly_upkeep", "fuel.hourly_upkeep"),
            ("startup_cost", "fuel.startup_cost"),
            ("fuel_item_type_id", "fuel.type_id"),
            ("mutually_exclusive_group", "mutually_exclusive_group"),
            ("power_production", "power_production"),
            ("power_allocation", "power_allocation"),
            ("workforce_production", "workforce_production"),
            ("workforce_allocation", "workforce_allocation"),
        )
        update_fields = False
        custom_names = False

    item_type = models.OneToOneField(
        to=ItemType,
        on_delete=models.CASCADE,
        related_name="sovereignty_upgrade",
        null=True,
        blank=True,
        default=None,
    )
    fuel_item_type = models.ForeignKey(
        to=ItemType,
        on_delete=models.CASCADE,
        related_name="sovereignty_upgrade_fuel",
        null=True,
        blank=True,
        default=None,
    )

    hourly_upkeep = models.IntegerField(null=True, blank=True, default=None)
    startup_cost = models.IntegerField(null=True, blank=True, default=None)
    power_production = models.IntegerField(null=True, blank=True, default=None)
    power_allocation = models.IntegerField(null=True, blank=True, default=None)
    workforce_production = models.IntegerField(null=True, blank=True, default=None)
    workforce_allocation = models.IntegerField(null=True, blank=True, default=None)

    mutually_exclusive_group = models.CharField(
        max_length=250, null=True, blank=True, default=None
    )

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
        return f"{self.item_type.name} ({self.item_type.id})"
