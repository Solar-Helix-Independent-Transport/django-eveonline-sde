"""
    Standalone lookup/enum tables from the SDE that don't belong under any
    of the other groupings (types, map, lore, industry, freelance, sovereignty),
    plus the join tables between them (e.g. CorporationRoleGroupMembership).
"""
# Django
from django.db import models

# Django EVE SDE
from eve_sde.models.base import JSONModel
from eve_sde.models.types import ItemType, TypeBase


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


class CorporationRoleGroup(TypeBase):
    """
    corporationRoleGroups.jsonl
        _key : int
        appliesTo : str
        appliesToGrantable : str
        isDivisional : bool
        isLocational : bool
        name : dict
            ...
    """
    # JsonL Params
    class Import:
        filename = "corporationRoleGroups.jsonl"
        lang_fields = ["name"]
        data_map = (
            ("name", "name.en"),
            ("applies_to", "appliesTo"),
            ("applies_to_grantable", "appliesToGrantable"),
            ("is_divisional", "isDivisional"),
            ("is_locational", "isLocational"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    applies_to = models.CharField(max_length=250, null=True, blank=True, default=None)
    applies_to_grantable = models.CharField(max_length=250, null=True, blank=True, default=None)
    is_divisional = models.BooleanField(default=False)
    is_locational = models.BooleanField(default=False)


class CorporationRole(TypeBase):
    """
    corporationRoles.jsonl
        _key : int
        description : dict
            ...
        name : dict
            ...
        * roleGroupIDs : list
        shortName : str
    """
    # JsonL Params
    class Import:
        filename = "corporationRoles.jsonl"
        lang_fields = ["name", "description"]
        data_map = (
            ("name", "name.en"),
            ("description", "description.en"),
            ("short_name", "shortName"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    description = models.TextField(null=True, blank=True, default=None)  # _en
    short_name = models.CharField(max_length=250, null=True, blank=True, default=None)


class CorporationRoleGroupMembership(JSONModel):
    """
    # Is deleted and reloaded on updates, same as ItemTypeMaterials/TypeDogma.
    corporationRoles.jsonl
        _key : int
        * roleGroupIDs : list
    """
    # JsonL Params
    class Import:
        filename = "corporationRoles.jsonl"
        lang_fields = False
        data_map = (
            ("corporation_role_id", "_key"),
            ("role_group_id", "roleGroupID"),
        )
        update_fields = False
        custom_names = False

    corporation_role = models.ForeignKey(
        CorporationRole,
        on_delete=models.CASCADE,
        related_name="role_groups",
        null=True,
        blank=True,
        default=None
    )
    role_group = models.ForeignKey(
        CorporationRoleGroup,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _key = {"_key": json_data.get("_key")}

        for role_group_id in json_data.get("roleGroupIDs", []):
            _out.append(cls.map_to_model({"roleGroupID": role_group_id} | _key, name_lookup=name_lookup, pk=False))

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
        return f"{self.corporation_role.name} ({self.role_group.name})"


class MetenoxMoonDrill(JSONModel):
    """
    metenoxMoonDrill.jsonl
        _key : int
        miningCycleTime : int
        miningEfficiency : float
        reagentsConsumedPerCycle : int
    """
    # JsonL Params
    class Import:
        filename = "metenoxMoonDrill.jsonl"
        lang_fields = False
        data_map = (
            ("mining_cycle_time", "miningCycleTime"),
            ("mining_efficiency", "miningEfficiency"),
            ("reagents_consumed_per_cycle", "reagentsConsumedPerCycle"),
        )
        update_fields = False
        custom_names = False

    item_type = models.OneToOneField(
        to=ItemType,
        on_delete=models.CASCADE,
        related_name="metenox_moon_drill",
        primary_key=True,
    )
    mining_cycle_time = models.IntegerField(null=True, blank=True, default=None)
    mining_efficiency = models.FloatField(null=True, blank=True, default=None)
    reagents_consumed_per_cycle = models.IntegerField(null=True, blank=True, default=None)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f"{self.item_type.name} ({self.item_type.id})"


class SkillPlan(TypeBase):
    """
    skillPlans.jsonl
        _key : int
        careerPathID : int
        description : dict
            ...
        factionID : int
        internalName : str
        * milestones : list
            level : int
            typeID : int
        name : dict
            ...
        * skillRequirements : list
            level : int
            typeID : int
        npcCorporationDivision : int
    """
    # JsonL Params
    class Import:
        filename = "skillPlans.jsonl"
        lang_fields = ["name", "description"]
        data_map = (
            ("name", "name.en"),
            ("description", "description.en"),
            ("internal_name", "internalName"),
            ("career_path_id_raw", "careerPathID"),
            ("faction_id_raw", "factionID"),
            ("npc_corporation_division_id_raw", "npcCorporationDivision"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    internal_name = models.CharField(max_length=250, null=True, blank=True, default=None)
    description = models.TextField(null=True, blank=True, default=None)  # _en
    career_path_id_raw = models.IntegerField(null=True, blank=True, default=None)
    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    npc_corporation_division_id_raw = models.IntegerField(null=True, blank=True, default=None)


class SkillPlanMilestone(JSONModel):
    """
    # Is deleted and reloaded on updates, same as ItemTypeMaterials/TypeDogma.
    skillPlans.jsonl
        _key : int
        * milestones : list
            level : int
            typeID : int
    """
    # JsonL Params
    class Import:
        filename = "skillPlans.jsonl"
        lang_fields = False
        data_map = (
            ("skill_plan_id", "_key"),
            ("item_type_id", "typeID"),
            ("level", "level"),
        )
        update_fields = False
        custom_names = False

    skill_plan = models.ForeignKey(
        SkillPlan,
        on_delete=models.CASCADE,
        related_name="milestones",
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
    level = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _key = {"_key": json_data.get("_key")}

        for milestone in json_data.get("milestones", []):
            _out.append(cls.map_to_model(milestone | _key, name_lookup=name_lookup, pk=False))

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
        return f"{self.skill_plan.name} ({self.item_type.name} {self.level})"


class SkillPlanSkillRequirement(JSONModel):
    """
    # Is deleted and reloaded on updates, same as ItemTypeMaterials/TypeDogma.
    skillPlans.jsonl
        _key : int
        * skillRequirements : list
            level : int
            typeID : int
    """
    # JsonL Params
    class Import:
        filename = "skillPlans.jsonl"
        lang_fields = False
        data_map = (
            ("skill_plan_id", "_key"),
            ("item_type_id", "typeID"),
            ("level", "level"),
        )
        update_fields = False
        custom_names = False

    skill_plan = models.ForeignKey(
        SkillPlan,
        on_delete=models.CASCADE,
        related_name="skill_requirements",
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
    level = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        _key = {"_key": json_data.get("_key")}

        for requirement in json_data.get("skillRequirements", []):
            _out.append(cls.map_to_model(requirement | _key, name_lookup=name_lookup, pk=False))

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
        return f"{self.skill_plan.name} ({self.item_type.name} {self.level})"
