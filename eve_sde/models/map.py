"""
    Eve Map Models
"""
# Django
from django.db import models
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _

# Django EVE SDE
from eve_sde.managers.map import MoonManager, PlanetManager
from eve_sde.models.base import JSONModel
from eve_sde.models.types import ItemType
from eve_sde.models.utils import get_langs_for_field, to_roman_numeral

POCHVEN_REGION_ID = 10000070


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
            ...
        factionID : int
        name : dict
            ...
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

    @property
    def constellations(self) -> QuerySet["Constellation", "Constellation"]:
        """
        Return all constellations for this region

        :return:
        :rtype:
        """

        return Constellation.objects.filter(region=self)

    @property
    def solar_systems(self) -> QuerySet["SolarSystem", "SolarSystem"]:
        """
        Return all solar systems for this region

        :return:
        :rtype:
        """

        return SolarSystem.objects.filter(constellation__region=self)


class Constellation(UniverseBase):
    """
    mapConstellations.jsonl
        _key : int
        factionID : int
        name : dict
            ...
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
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        null=True,
        default=None
    )
    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)

    @property
    def solar_systems(self) -> QuerySet["SolarSystem", "SolarSystem"]:
        """
        Return all solar systems for this constellation

        :return:
        :rtype:
        """

        return SolarSystem.objects.filter(constellation=self)


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
            ...
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
        starID : int  # see Star.solar_system (reverse: solar_system.star)
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
    visual_effect = models.CharField(max_length=50, null=True, blank=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)

    x_2d = models.FloatField(null=True, default=None, blank=True)
    y_2d = models.FloatField(null=True, default=None, blank=True)

    @property
    def is_high_sec(self) -> bool:
        """
        Return True when this solar system is in high sec, else False.
        """
        return self.security_status >= 0.45

    @property
    def is_low_sec(self) -> bool:
        """
        Return True when this solar system is in low sec, else False.
        """
        return 0.0 < self.security_status < 0.45

    @property
    def is_null_sec(self) -> bool:
        """
        Return True when this solar system is in null sec, else False.
        """
        return (
            not self.is_wh_space
            and not self.is_triglavian_space
            and not self.is_abyssal_deadspace
            and self.security_status <= 0.0
        )

    @property
    def is_w_space(self) -> bool:
        """
        Deprecated - Use `is_wh_space`

        Return True when this solar system is in wormhole space, else False.
        """
        return self.is_wh_space

    @property
    def is_wh_space(self) -> bool:
        """
        Return True when this solar system is in wormhole space, else False.
        """
        return 31_000_000 <= self.id < 32_000_000

    @property
    def is_trig_space(self) -> bool:
        """
        Deprecated - Use `is_triglavian_space`

        Return True when this solar system is in Triglavian space, else False.
        """
        return self.is_triglavian_space

    @property
    def is_triglavian_space(self) -> bool:
        """
        Return True when this solar system is in Triglavian space, else False.
        """
        return self.constellation.region.id == POCHVEN_REGION_ID

    @property
    def is_abyssal_deadspace(self) -> bool:
        """
        Return True when this solar system is in abyssal deadspace, else False.
        """
        return 32_000_000 <= self.id < 33_000_000


class Star(UniverseBase):
    """
    Named after the solar system it belongs to.

    mapStars.jsonl
        _key : int
        radius : int
        solarSystemID : int
        statistics : dict
            statistics.age : float
            statistics.life : float
            statistics.luminosity : float
            statistics.spectralClass : str
            statistics.temperature : float
        typeID : int
    """
    class Import:
        filename = "mapStars.jsonl"
        lang_fields = False
        update_fields = False
        custom_names = True
        data_map = (
            ("age", "statistics.age"),
            ("item_type_id", "typeID"),
            ("life", "statistics.life"),
            ("luminosity", "statistics.luminosity"),
            ("radius", "radius"),
            ("solar_system_id", "solarSystemID"),
            ("spectral_class", "statistics.spectralClass"),
            ("temperature", "statistics.temperature"),
        )

    age = models.FloatField(null=True, blank=True, default=None)
    item_type = models.ForeignKey(
        ItemType,
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
        default=None
    )
    life = models.FloatField(null=True, blank=True, default=None)
    luminosity = models.FloatField(null=True, blank=True, default=None)
    radius = models.IntegerField(null=True, blank=True, default=None)
    solar_system = models.OneToOneField(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="star",
        null=True,
        blank=True,
        default=None
    )
    spectral_class = models.CharField(max_length=10, null=True, blank=True, default=None)
    temperature = models.FloatField(null=True, blank=True, default=None)

    def __str__(self):
        return (self.name)

    @classmethod
    def name_lookup(cls):
        _langs = get_langs_for_field("name")
        return {
            s.get("id"): s for s in
            SolarSystem.objects.all().values("id", "name", *_langs)
        }

    @classmethod
    def format_name(cls, json_data, name_lookup, lang: str = None):
        system = name_lookup[json_data.get('solarSystemID')][f"name_{lang}"]
        if not system:
            system = name_lookup[json_data.get('solarSystemID')][f"name"]
        return system


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
        related_name="stargates",
        null=True,
        blank=True,
        default=None
    )

    def __str__(self):
        return self.name

    @classmethod
    def name_lookup(cls):
        return {
            s.get("id"): s.get("name") for s in
            SolarSystem.objects.all().values("id", "name")
        }

    @classmethod
    def from_jsonl(cls, json_data, system_names):
        src_id = json_data.get("solarSystemID")
        dst_id = json_data.get("destination", {}).get("solarSystemID")
        return cls(
            id=json_data.get("_key"),
            destination_id=dst_id,
            item_type_id=json_data.get("typeID"),
            name=f"{system_names[src_id]} ≫ {system_names[dst_id]}",
            solar_system_id=src_id,
        )

    @classmethod
    def load_from_sde(cls, folder_name):
        gate_qry = cls.objects.all()
        if gate_qry.exists():
            # speed and we are not caring about f-keys or signals on these models
            gate_qry._raw_delete(gate_qry.db)
        super().load_from_sde(folder_name)


class NPCStation(UniverseBase):
    """
    npcStations.jsonl
        _key : int
        celestialIndex : int
        operationID : int
        orbitID : int
        orbitIndex : int
        ownerID : int
        position : dict
            position.x : float
            position.y : float
            position.z : float
        reprocessingEfficiency : float
        reprocessingHangarFlag : int
        reprocessingStationsTake : float
        solarSystemID : int
        typeID : int
        useOperationName : bool
    """
    # JsonL Params
    class Import:
        filename = "npcStations.jsonl"
        lang_fields = ["name"]
        data_map = (
            ("celestial_index", "celestialIndex"),
            ("operation_id_raw", "operationID"),
            ("orbit_id_raw", "orbitID"),
            ("orbit_index", "orbitIndex"),
            ("owner_id_raw", "ownerID"),
            ("x", "position.x"),
            ("y", "position.y"),
            ("z", "position.z"),
            ("reprocessing_efficiency", "reprocessingEfficiency"),
            ("reprocessing_hangar_flag", "reprocessingHangarFlag"),
            ("reprocessing_stations_take", "reprocessingStationsTake"),
            ("solar_system_id", "solarSystemID"),
            ("item_type_id", "typeID"),
            ("use_operation_name", "useOperationName"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    celestial_index = models.IntegerField(null=True, blank=True, default=None)
    operation_id_raw = models.IntegerField(null=True, blank=True, default=None)
    orbit_id_raw = models.IntegerField(null=True, blank=True, default=None)
    orbit_index = models.IntegerField(null=True, blank=True, default=None)
    owner_id_raw = models.IntegerField(null=True, blank=True, default=None)
    reprocessing_efficiency = models.FloatField(null=True, blank=True, default=None)
    reprocessing_hangar_flag = models.IntegerField(null=True, blank=True, default=None)
    reprocessing_stations_take = models.FloatField(null=True, blank=True, default=None)
    solar_system = models.ForeignKey(
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
    use_operation_name = models.BooleanField(null=True, blank=True, default=None)


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
            ...

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
        related_name="planets",
        null=True,
        blank=True,
        default=None
    )
    # eve_type = models.ForeignKey(
    #     EveType, on_delete=models.SET_NULL, null=True, default=None)

    def __str__(self):
        return (self.name)

    @property
    def localized_name(self):
        return f"{_(self.solar_system.name)} {to_roman_numeral(self.celestial_index)}"

    @classmethod
    def name_lookup(cls):
        _langs = get_langs_for_field("name")
        return {
            s.get("id"): s for s in
            SolarSystem.objects.all().values("id", "name", *_langs)
        }

    @classmethod
    def format_name(cls, json_data, system_names, lang: str = None):
        system = system_names[json_data.get('solarSystemID')][f"name_{lang}"]
        if not system:
            system = system_names[json_data.get('solarSystemID')][f"name"]
        return f"{system} {to_roman_numeral(json_data.get('celestialIndex'))}"


class PlanetResource(JSONModel):
    """
    planetResources.jsonl
        _key : int
        power : int
        workforce : int
        reagent : dict
            reagent.amount_per_cycle : int
            reagent.cycle_period : int
            reagent.secured_capacity : int
            reagent.type_id : int
            reagent.unsecured_capacity : int
    """

    class Import:
        filename = "planetResources.jsonl"
        lang_fields = False
        data_map = (
            ("planet_id", "_key"),
            ("power", "power"),
            ("workforce", "workforce"),
            ("reagent_amount_per_cycle", "reagent.amount_per_cycle"),
            ("reagent_cycle_period", "reagent.cycle_period"),
            ("reagent_secured_capacity", "reagent.secured_capacity"),
            ("reagent_type_id", "reagent.type_id"),
            ("reagent_unsecured_capacity", "reagent.unsecured_capacity"),
        )
        update_fields = False
        custom_names = False
        field_filters = (
            # only include planets, stars are included in the same file
            ("_key", lambda: Planet.objects.values_list("id", flat=True)),
        )

    planet = models.OneToOneField(
        Planet,
        primary_key=True,
        related_name="resource",
        on_delete=models.CASCADE
    )

    power = models.IntegerField(null=True, blank=True, default=None)
    workforce = models.IntegerField(null=True, blank=True, default=None)

    reagent_amount_per_cycle = models.IntegerField(null=True, blank=True, default=None)
    reagent_cycle_period = models.IntegerField(null=True, blank=True, default=None)
    reagent_secured_capacity = models.IntegerField(null=True, blank=True, default=None)
    reagent_type = models.ForeignKey(
        ItemType,
        related_name="+",
        null=True,
        blank=True,
        default=None,
        on_delete=models.CASCADE
    )
    reagent_unsecured_capacity = models.IntegerField(null=True, blank=True, default=None)


class StarResource(JSONModel):
    """
    planetResources.jsonl
        _key : int
        power : int
        workforce : int
        reagent : dict
            reagent.amount_per_cycle : int
            reagent.cycle_period : int
            reagent.secured_capacity : int
            reagent.type_id : int
            reagent.unsecured_capacity : int
    """

    class Import:
        filename = "planetResources.jsonl"
        lang_fields = False
        data_map = (
            ("star_id", "_key"),
            ("power", "power"),
            ("workforce", "workforce"),
            ("reagent_amount_per_cycle", "reagent.amount_per_cycle"),
            ("reagent_cycle_period", "reagent.cycle_period"),
            ("reagent_secured_capacity", "reagent.secured_capacity"),
            ("reagent_type_id", "reagent.type_id"),
            ("reagent_unsecured_capacity", "reagent.unsecured_capacity"),
        )
        update_fields = False
        custom_names = False
        field_filters = (
            # only include stars, planets are included in the same file
            ("_key", lambda: Star.objects.values_list("id", flat=True)),
        )

    star = models.OneToOneField(
        Star,
        primary_key=True,
        related_name="resource",
        on_delete=models.CASCADE
    )

    power = models.IntegerField(null=True, blank=True, default=None)
    workforce = models.IntegerField(null=True, blank=True, default=None)

    reagent_amount_per_cycle = models.IntegerField(null=True, blank=True, default=None)
    reagent_cycle_period = models.IntegerField(null=True, blank=True, default=None)
    reagent_secured_capacity = models.IntegerField(null=True, blank=True, default=None)
    reagent_type = models.ForeignKey(
        ItemType,
        related_name="+",
        null=True,
        blank=True,
        default=None,
        on_delete=models.CASCADE
    )
    reagent_unsecured_capacity = models.IntegerField(null=True, blank=True, default=None)


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
            ...

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
    planet = models.ForeignKey(
        Planet,
        on_delete=models.CASCADE,
        related_name="moons",
        null=True,
        blank=True,
        default=None
    )
    radius = models.IntegerField(null=True, blank=True, default=None)
    solar_system = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="moons",
        null=True,
        blank=True,
        default=None
    )

    def __str__(self):
        return (self.name)

    @property
    def localized_name(self):
        return f"{_(self.solar_system.name)} {to_roman_numeral(self.celestial_index)} - {_(self.item_type.name)} {self.orbit_index}"

    @classmethod
    def name_lookup(cls):
        _langs = get_langs_for_field("name")
        planets = {
            s.get("id"): s for s in
            Planet.objects.all().values("id", "name", *_langs)
        }
        item_types = {
            s.get("id"): s for s in
            ItemType.objects.filter(id=14).values("id", "name", *_langs)
        }
        return {
            "planet": planets,
            "item_type": item_types
        }

    @classmethod
    def format_name(cls, json_data, name_lookup, lang):
        planet = name_lookup["planet"][json_data.get('orbitID')][f"name_{lang}"]
        if not planet:
            planet = name_lookup["planet"][json_data.get('orbitID')][f"name"]

        moon = name_lookup["item_type"].get(json_data.get("typeID"), {}).get(f"name_{lang}", "Moon")
        if not moon:
            moon = name_lookup["item_type"].get(json_data.get("typeID"), {}).get(f"name", "Moon")

        return (
            f"{planet} - {moon} {json_data.get('orbitIndex')}"
        )


class Landmark(UniverseBase):
    """
    landmarks.jsonl
        _key : int
        description : dict
            ...
        name : dict
            ...
        position : dict
            position.x : float
            position.y : float
            position.z : float
        iconID : int
        locationID : int
    """
    # JsonL Params
    class Import:
        filename = "landmarks.jsonl"
        lang_fields = ["name", "description"]
        data_map = (
            ("name", "name.en"),
            ("description", "description.en"),
            ("icon_id", "iconID"),
            ("solar_system_id", "locationID"),
            ("x", "position.x"),
            ("y", "position.y"),
            ("z", "position.z"),
        )
        update_fields = False
        custom_names = False

    # Model Fields
    description = models.TextField(null=True, blank=True, default=None)  # _en
    icon_id = models.IntegerField(null=True, blank=True, default=None)
    solar_system = models.ForeignKey(
        SolarSystem,
        on_delete=models.SET_NULL,
        related_name="landmarks",
        null=True,
        blank=True,
        default=None
    )
