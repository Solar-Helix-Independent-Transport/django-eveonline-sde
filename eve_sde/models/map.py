"""
    Eve Map Models
"""
# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

# AA Example App
from eve_sde.managers.map import MoonManager, PlanetManager

from .base import JSONModel
from .types import ItemType
from .utils import to_roman_numeral


class UniverseBase(JSONModel):
    """
    Common to all universe models
    """
    id = models.BigIntegerField(
        primary_key=True
    )

    name = models.CharField(
        max_length=250
    )

    x = models.FloatField(null=True, default=None, blank=True)
    y = models.FloatField(null=True, default=None, blank=True)
    z = models.FloatField(null=True, default=None, blank=True)

    class Meta:
        abstract = True
        default_permissions = ()

    def __str__(self):
        return f"{self.name} ({self.id})"


class Region(UniverseBase):
    """
    mapRegions.jsonl
        _key : int
        constellationIDs : list
        description : dict
            description.de : str
            description.en : str
            description.es : str
            description.fr : str
            description.ja : str
            description.ko : str
            description.ru : str
            description.zh : str
        factionID : int
        name : dict
            name.de : str
            name.en : str
            name.es : str
            name.fr : str
            name.ja : str
            name.ko : str
            name.ru : str
            name.zh : str
        nebulaID : int
        position : dict
            position.x : float
            position.y : float
            position.z : float
        wormholeClassID : int
    """
    # JsonL Params
    class Import:
        filename = "mapRegions.jsonl"
        lang_fields = ["name", "description"]
        data_map = (
            ("description", "description.en"),
            ("faction_id_raw", "factionID"),
            ("name", "name.en"),
            ("nebular_id_raw", "nebulaID"),
            ("wormhole_class_id_raw", "wormholeClassID"),
            ("x", "position.x"),
            ("y", "position.y"),
            ("z", "position.z"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    description = models.TextField(null=True, blank=True, default=None)  # _en
    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    nebular_id_raw = models.IntegerField(null=True, blank=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)


class Constellation(UniverseBase):
    """
    mapConstellations.jsonl
        _key : int
        factionID : int
        name : dict
            name.de : str
            name.en : str
            name.es : str
            name.fr : str
            name.ja : str
            name.ko : str
            name.ru : str
            name.zh : str
        position : dict
            position.x : float
            position.y : float
            position.z : float
        regionID : int
        solarSystemIDs : list
        wormholeClassID : int
    """
    # JsonL Params
    class Import:
        filename = "mapConstellations.jsonl"
        lang_fields = ["name"]
        data_map = (
            ("faction_id_raw", "factionID"),
            ("name", "name.en"),
            ("region_id", "regionID"),
            ("wormhole_class_id_raw", "wormholeClassID"),
            ("x", "position.x"),
            ("y", "position.y"),
            ("z", "position.z"),
        )
        update_fields = False
        custom_names = False
    # Model Fields
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, default=None)
    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)


class SolarSystem(UniverseBase):
    """
    mapSolarSystems.jsonl
        _key : int
        border : bool
        constellationID : int
        hub : bool
        international : bool
        luminosity : float
        name : dict
            name.de : str
            name.en : str
            name.es : str
            name.fr : str
            name.ja : str
            name.ko : str
            name.ru : str
            name.zh : str
        planetIDs : list
        position : dict
            position.x : float
            position.y : float
            position.z : float
        position2D : dict
            position2D.x : float
            position2D.y : float
        radius : float
        regionID : int
        regional : bool
        securityClass : str
        securityStatus : float
        starID : int
        stargateIDs : list
        corridor : bool
        fringe : bool
        wormholeClassID : int
        visualEffect : str
        * disallowedAnchorCategories : list
        * disallowedAnchorGroups : list
        factionID : int

    * currently not included make an issue with use case to get it added
    """

    # JsonL Params
    class Import:
        filename = "mapSolarSystems.jsonl"
        lang_fields = ["name"]
        data_map = (
            ("border", "border"),
            ("constellation_id", "constellationID"),
            ("corridor", "corridor"),
            ("faction_id_raw", "factionID"),
            ("fringe", "fringe"),
            ("hub", "hub"),
            ("international", "international"),
            ("luminosity", "luminosity"),
            ("name", "name.en"),
            ("radius", "radius"),
            ("regional", "regional"),
            ("security_class", "securityClass"),
            ("security_status", "securityStatus"),
            ("star_id_raw", "starID"),
            ("visual_effect", "visualEffect"),
            ("wormhole_class_id_raw", "wormholeClassID"),
            ("x", "position.x"),
            ("y", "position.y"),
            ("z", "position.z"),
            ("x_2d", "position2D.x"),
            ("y_2d", "position2D.y"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    border = models.BooleanField(null=True, blank=True, default=False)
    constellation = models.ForeignKey(Constellation, on_delete=models.SET_NULL, null=True, blank=True, default=None)
    corridor = models.BooleanField(null=True, blank=True, default=False)
    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    fringe = models.BooleanField(null=True, blank=True, default=False)
    hub = models.BooleanField(null=True, blank=True, default=False)
    international = models.BooleanField(null=True, blank=True, default=False)
    luminosity = models.FloatField(null=True, blank=True, default=None)
    radius = models.FloatField(null=True, blank=True, default=None)
    regional = models.BooleanField(null=True, blank=True, default=False)
    security_class = models.CharField(max_length=5, null=True, blank=True, default=None)
    security_status = models.FloatField(null=True, blank=True, default=None)
    star_id_raw = models.IntegerField(null=True, blank=True, default=None)
    visual_effect = models.CharField(max_length=50, null=True, blank=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)

    x_2d = models.FloatField(null=True, default=None, blank=True)
    y_2d = models.FloatField(null=True, default=None, blank=True)


class Stargate(UniverseBase):
    """
    # Is Deleted and reloaded on updates. Don't F-Key to this model ATM.
    mapStargates.jsonl
        _key : int
        destination : dict
            destination.solarSystemID : int
            destination.stargateID : int
        position : dict
            position.x : float
            position.y : float
            position.z : float
        solarSystemID : int
        typeID : int
    """
    class Import:
        filename = "mapStargates.jsonl"
        lang_fields = False
        update_fields = False
        custom_names = False
        data_map = False

    destination = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="+",
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
    solar_system = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )

    def __str__(self):
        return (self.from_solar_system_id, self.to_solar_system_id)

    @classmethod
    def name_lookup(cls):
        return {
            s.get("id"): s.get("name") for s in
            SolarSystem.objects.all().values("id", "name")
        }

    @classmethod
    def from_jsonl(cls, json_data, system_names, line: int = 0):
        src_id = json_data.get("solarSystemID")
        dst_id = json_data.get("destination", {}).get("solarSystemID")
        return cls(
            id=json_data.get("_key"),
            destination_id=dst_id,
            item_type_id=json_data.get("typeID"),
            name=f"{system_names[src_id]} ≫ {system_names[dst_id]}",
            solar_system_id=src_id,
        ), []

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            # speed and we are not caring about f-keys or signals on these models
            gate_qry._raw_delete(gate_qry.db)
        super().load_from_sde(folder_name)


class Planet(UniverseBase):
    """
    mapPlanets.jsonl
        _key : int
        asteroidBeltIDs : list
        * attributes : dict
        celestialIndex : int
        moonIDs : list
        orbitID : int
        position : dict
            position.x : float
            position.y : float
            position.z : float
        radius : int
        solarSystemID : int
        * statistics : dict
        typeID : int
        npcStationIDs : list
        * uniqueName : dict
            uniqueName.de : str
            uniqueName.en : str
            uniqueName.es : str
            uniqueName.fr : str
            uniqueName.ja : str
            uniqueName.ko : str
            uniqueName.ru : str
            uniqueName.zh : str

    * currently not included make an issue with use case to get it added
    """
    class Import:
        filename = "mapPlanets.jsonl"
        lang_fields = False
        update_fields = False
        custom_names = True
        data_map = (
            ("celestial_index", "celestialIndex"),
            ("orbit_id_raw", "orbitID"),
            ("radius", "radius"),
            ("solar_system_id", "solarSystemID"),
            ("item_type_id", "typeID"),
            ("x", "position.x"),
            ("y", "position.y"),
            ("z", "position.z"),
        )

    objects = PlanetManager()

    celestial_index = models.IntegerField(null=True, blank=True, default=None)
    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )
    orbit_id_raw = models.IntegerField(null=True, blank=True, default=None)
    orbit_index = models.IntegerField(null=True, blank=True, default=None)
    radius = models.IntegerField(null=True, blank=True, default=None)
    solar_system = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )
    # eve_type = models.ForeignKey(
    #     EveType, on_delete=models.SET_NULL, null=True, default=None)

    def __str__(self):
        return (self.name)

    @classmethod
    def name_lookup(cls):
        # _langs = get_langs_for_field("name")
        return {
            s.get("id"): s for s in
            SolarSystem.objects.all().values("id", "name")  # , *_langs)
        }

    @classmethod
    def format_name(cls, json_data, system_names):
        return f"{system_names[json_data.get('solarSystemID')]['name']} {to_roman_numeral(json_data.get('celestialIndex'))}"

    @property
    def localized_name(self):
        return f"{_(self.solar_system.name)} {to_roman_numeral(self.celestial_index)}"


class Moon(UniverseBase):
    """
    "system_name planet_roman_numeral - Moon #"

    mapMoons.jsonl
        _key : int
        * attributes : dict
        celestialIndex : int
        orbitID : int
        orbitIndex : int
        position : dict
            position.x : float
            position.y : float
            position.z : float
        radius : float
        solarSystemID : int
        * statistics : dict
        typeID : int
        npcStationIDs : list
        uniqueName : dict
            uniqueName.de : str
            uniqueName.en : str
            uniqueName.es : str
            uniqueName.fr : str
            uniqueName.ja : str
            uniqueName.ko : str
            uniqueName.ru : str
            uniqueName.zh : str

    * currently not included make an issue with use case to get it added
    """
    class Import:
        filename = "mapMoons.jsonl"
        lang_fields = False
        update_fields = False
        custom_names = True
        data_map = (
            ("celestial_index", "celestialIndex"),
            ("item_type_id", "typeID"),
            ("orbit_id_raw", "orbitID"),
            ("orbit_index", "orbitIndex"),
            ("planet_id", "orbitID"),
            ("radius", "radius"),
            ("solar_system_id", "solarSystemID"),
            ("x", "position.x"),
            ("y", "position.y"),
            ("z", "position.z"),
        )

    objects = MoonManager()

    celestial_index = models.IntegerField(null=True, blank=True, default=None)
    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )
    orbit_id_raw = models.IntegerField(null=True, blank=True, default=None)
    orbit_index = models.IntegerField(null=True, blank=True, default=None)
    planet = models.ForeignKey(Planet, on_delete=models.CASCADE, related_name="+", null=True, blank=True, default=None)
    radius = models.IntegerField(null=True, blank=True, default=None)
    solar_system = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )

    def __str__(self):
        return (self.name)

    @classmethod
    def name_lookup(cls):
        # _langs = get_langs_for_field("name")
        return {
            s.get("id"): s for s in
            Planet.objects.all().values("id", "name")  # , *_langs)
        }

    @classmethod
    def format_name(cls, json_data, planet_names):
        return f"{planet_names[json_data.get('orbitID')]['name']} - Moon {json_data.get('orbitIndex')}"

    @property
    def localized_name(self):
        return f"{_(self.solar_system.name)} {to_roman_numeral(self.celestial_index)} - {_(self.item_type.name)} {self.orbit_index}"
