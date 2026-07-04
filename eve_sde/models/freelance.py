"""
    Freelance Job schema/definition data from the SDE.

    Note: actual posted Freelance Jobs (ESI `GetCorporationsFreelanceJobs`) are
    live game state, not SDE data, and are not modeled here - only the static
    job-type definitions ("schemas") describing what a posted job of that type
    looks like.
"""
# Django
from django.db import models

from .base import JSONModel
from .lore import Archetype
from .map import Constellation, Region, SolarSystem
from .types import ItemGroup, ItemType


class FreelanceJobSchema(JSONModel):
    """
    freelanceJobSchemas.jsonl
        _key : int (always 1 - the whole file is a single row wrapping `_value`)
        _value : list
            _key : str
            contentTags : list[str]
            description : dict
                ...
            iconID : str
            maxContributionsPerParticipant : dict
            parameters : list
            progressDescription : dict
                ...
            rewardDescription : dict
                ...
            targetDescription : dict
                ...
            title : dict
                ...
            * contributionMultiplier : dict
            * maxProgressPerContribution : dict

    * not present on every schema
    """
    class Import:
        filename = "freelanceJobSchemas.jsonl"
        lang_fields = [
            "title",
            "description",
            ("progress_description", "progressDescription"),
            ("reward_description", "rewardDescription"),
            ("target_description", "targetDescription"),
        ]
        data_map = (
            ("title", "title.en"),
            ("description", "description.en"),
            ("progress_description", "progressDescription.en"),
            ("reward_description", "rewardDescription.en"),
            ("target_description", "targetDescription.en"),
            ("icon_key", "iconID"),
            ("content_tags", "contentTags"),
        )
        update_fields = False
        custom_names = False

    # Kept as a raw blob: irregular/optional shape, only display copy and
    # contribution-limit numbers, no relational lookup value.
    _EXTRA_CONFIG_KEYS = (
        "maxContributionsPerParticipant",
        "contributionMultiplier",
        "maxProgressPerContribution",
    )

    # PK - the schema's own key, e.g. "BoostShield"
    id = models.CharField(max_length=64, primary_key=True)

    title = models.CharField(max_length=250)
    description = models.TextField(null=True, blank=True, default=None)  # _en
    progress_description = models.CharField(max_length=250, null=True, blank=True, default=None)  # _en
    reward_description = models.CharField(max_length=250, null=True, blank=True, default=None)  # _en
    target_description = models.CharField(max_length=250, null=True, blank=True, default=None)  # _en

    icon_key = models.CharField(max_length=100, null=True, blank=True, default=None)
    content_tags = models.JSONField(default=list, blank=True)

    extra_config = models.JSONField(default=dict, blank=True)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f"{self.title} ({self.id})"

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        for ob in json_data.get("_value", []):
            _model = cls.map_to_model(ob, name_lookup=name_lookup, pk=True)
            _model.extra_config = {k: ob[k] for k in cls._EXTRA_CONFIG_KEYS if k in ob}
            _out.append(_model)
        return _out


class FreelanceJobSchemaParameter(JSONModel):
    """
    One entry from a FreelanceJobSchema's `parameters` list.

    Each parameter is a `oneOf` of shapes in the SDE - `matcher` (pick a
    location/ship/character/etc.), `boolean`, `itemDelivery`, or `options`.
    Only `matcher` (the shape every current schema actually links to other
    models with) is normalized into columns; the other kinds still keep full
    fidelity via `raw`, since their internal shape isn't uniform.

    Note: ESI's live job data names the `itemDelivery` kind
    `corporation_item_delivery` - the two refer to the same thing.
    """
    class Import:
        filename = "freelanceJobSchemas.jsonl"
        lang_fields = [
            "title",
            "description",
            ("unset_description", "unsetDescription"),
        ]
        data_map = (
            ("schema_id", "schema_id"),
            ("key", "key"),
            ("kind", "kind"),
            ("matcher_type", "type"),
            ("accepted_value_types", ("acceptedValueTypes", [])),
            ("optional", ("optional", False)),
            ("max_entries", "maxEntries"),
            ("title", "title.en"),
            ("description", "description.en"),
            ("unset_description", "unsetDescription.en"),
        )
        update_fields = False
        custom_names = False

    _KINDS = ("matcher", "boolean", "itemDelivery", "options")

    id = models.CharField(max_length=128, primary_key=True)
    schema = models.ForeignKey(FreelanceJobSchema, on_delete=models.CASCADE, related_name="parameters")
    key = models.CharField(max_length=64)

    # Which of the 4 SDE parameter shapes this row was built from.
    kind = models.CharField(max_length=32, null=True, blank=True, default=None)

    # `matcher`-only fields - what other models this parameter can link to.
    matcher_type = models.CharField(max_length=50, null=True, blank=True, default=None)
    accepted_value_types = models.JSONField(default=list, blank=True)
    optional = models.BooleanField(default=False)
    max_entries = models.IntegerField(null=True, blank=True, default=None)

    title = models.CharField(max_length=250, null=True, blank=True, default=None)
    description = models.TextField(null=True, blank=True, default=None)
    unset_description = models.CharField(max_length=250, null=True, blank=True, default=None)

    # Full untouched parameter dict - the only source of truth for
    # boolean/itemDelivery/options kinds beyond title/description.
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return f"{self.schema_id}:{self.key}"

    @staticmethod
    def build_pk(schema_key: str, param_key: str) -> str:
        return f"{schema_key}:{param_key}"

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        _out = []
        for job in json_data.get("_value", []):
            schema_key = job.get("_key")
            for p in job.get("parameters", []):
                kind = next((k for k in cls._KINDS if k in p), None)
                merged = dict(p.get(kind, {})) if kind else {}
                if "title" not in merged and "choiceLabel" in merged:
                    # `boolean` params label themselves via `choiceLabel` instead of `title`
                    merged["title"] = merged["choiceLabel"]
                merged.update({
                    "schema_id": schema_key,
                    "key": p.get("_key"),
                    "kind": kind,
                    "_key": cls.build_pk(schema_key, p.get("_key")),
                })
                _model = cls.map_to_model(merged, name_lookup=name_lookup, pk=True)
                _model.raw = p
                _out.append(_model)
        return _out

    @classmethod
    def load_from_sde(cls, folder_name):
        # Is deleted and reloaded on every update - don't F-key to this model.
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            gate_qry._raw_delete(gate_qry.db)
        super().load_from_sde(folder_name)


def _build_value_type_models() -> dict:
    """Maps a parameter's `accepted_value_types` entries to the model each resolves to."""
    # Alliance Auth
    from allianceauth.eveonline.models import (
        EveAllianceInfo,
        EveCharacter,
        EveCorporationInfo,
        EveFactionInfo,
    )

    return {
        "solarsystem": SolarSystem,
        "constellation": Constellation,
        "region": Region,
        "ship_type": ItemType,
        "ship_class": ItemGroup,
        "ore_type": ItemType,
        "ore_group": ItemGroup,
        "archetype": Archetype,
        "faction": EveFactionInfo,
        "character": EveCharacter,
        "corporation": EveCorporationInfo,
        "alliance": EveAllianceInfo,
    }


# Not every "acceptedValueTypes" entry has been observed in the SDE yet, so
# this may not be exhaustive of everything ESI can send - extend as needed.
FREELANCE_VALUE_TYPE_MODELS = _build_value_type_models()
