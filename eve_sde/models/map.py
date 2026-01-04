"""
    Eve Map Models
"""
# Django
from django.db import models
from django.utils.translation import gettext_lazy as _

from .base import JSONModel
from .utils import get_langs_for_field, lang_key, to_roman_numeral


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
    _filename = "mapRegions.jsonl"
    _update_fields = [
        "description",
        "faction_id_raw",
        "name",
        "nebular_id_raw",
        "wormhole_class_id_raw",
    ]

    # Model Fields
    description = models.TextField()  # _en
    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    nebular_id_raw = models.IntegerField(null=True, blank=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, names=False):
        region = cls(
            id=json_data.get("_key"),
            name=json_data.get("name", {}).get("en"),
            description=json_data.get("description", {}).get("en"),
            faction_id_raw=json_data.get("factionID"),
            nebular_id_raw=json_data.get("nebulaID"),
            wormhole_class_id_raw=json_data.get("wormholeClassID"),
            x=json_data.get("position", {}).get("x"),
            y=json_data.get("position", {}).get("y"),
            z=json_data.get("position", {}).get("z"),
        )
        for lang, name in json_data.get("name", {}).items():
            setattr(region, f"name_{lang_key(lang)}", name)

        for lang, name in json_data.get("description", {}).items():
            setattr(region, f"description_{lang_key(lang)}", name)

        return region


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
    _filename = "mapConstellations.jsonl"
    _update_fields = [
        "name",
        "region",
        "wormhole_class_id_raw",
        "faction_id_raw",

    ]

    # Model Fields
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, default=None)

    faction_id_raw = models.IntegerField(null=True, blank=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)

    @classmethod
    def from_jsonl(cls, json_data, names=False):
        constellation = cls(
            id=json_data.get("_key"),
            name=json_data.get("name", {}).get("en"),
            faction_id_raw=json_data.get("factionID"),
            wormhole_class_id_raw=json_data.get("wormholeClassID"),
            x=json_data.get("position", {}).get("x"),
            y=json_data.get("position", {}).get("y"),
            z=json_data.get("position", {}).get("z"),
        )

        for lang, name in json_data.get("name", {}).items():
            setattr(constellation, f"name_{lang_key(lang)}", name)

        return constellation


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
    _filename = "mapSolarSystems.jsonl"
    _update_fields = [
        "border",
        "constellation",
        "corridor",
        "fringe",
        "hub",
        "international",
        "luminosity",
        "name",
        "radius",
        "regional",
        "security_class",
        "security_status",
        "star_id_raw",
        "wormhole_class_id_raw",
        "visual_effect",
        "x",
        "y",
        "z",
        "x_2d",
        "y_2d",
    ]

    # Model Fields
    border = models.BooleanField(null=True, blank=True, default=False)
    constellation = models.ForeignKey(Constellation, on_delete=models.SET_NULL, null=True, default=None)
    corridor = models.BooleanField(null=True, blank=True, default=False)
    fringe = models.BooleanField(null=True, blank=True, default=False)
    hub = models.BooleanField(null=True, blank=True, default=False)
    international = models.BooleanField(null=True, blank=True, default=False)
    luminosity = models.FloatField(null=True, blank=True, default=None)
    radius = models.FloatField(null=True, blank=True, default=None)
    regional = models.BooleanField(null=True, blank=True, default=False)
    security_class = models.CharField(max_length=5, null=True, default=None)
    security_status = models.FloatField(null=True, blank=True, default=None)
    star_id_raw = models.IntegerField(null=True, default=None)
    wormhole_class_id_raw = models.IntegerField(null=True, blank=True, default=None)
    visual_effect = models.CharField(max_length=50, null=True, default=None)

    x_2d = models.FloatField(null=True, default=None, blank=True)
    y_2d = models.FloatField(null=True, default=None, blank=True)

    @classmethod
    def from_jsonl(cls, json_data, names=False):
        system = cls(
            id=json_data.get("_key"),

            border=json_data.get("border"),
            constellation_id=json_data.get("constellationID"),
            fringe=json_data.get("fringe"),
            hub=json_data.get("hub"),
            international=json_data.get("international"),
            luminosity=json_data.get("luminosity"),
            name=json_data.get("name", {}).get("en"),
            radius=json_data.get("radius"),
            regional=json_data.get("regional"),
            security_class=json_data.get("securityClass"),
            security_status=json_data.get("securityStatus"),
            star_id_raw=json_data.get("starID"),
            wormhole_class_id_raw=json_data.get("wormholeClassID"),
            visual_effect=json_data.get("visualEffect"),

            x_2d=json_data.get("position2D", {}).get("x"),
            y_2d=json_data.get("position2D", {}).get("y"),

            x=json_data.get("position", {}).get("x"),
            y=json_data.get("position", {}).get("y"),
            z=json_data.get("position", {}).get("z"),
        )

        for lang, name in json_data.get("name", {}).items():
            setattr(system, f"name_{lang_key(lang)}", name)

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
    _filename = "mapStargates.jsonl"
    _update_fields = False

    destination = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="+"
    )
    eve_type_id_raw = models.IntegerField()
    solar_system = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
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
    def from_jsonl(cls, json_data, system_names):
        src_id = json_data.get("solarSystemID")
        dst_id = json_data.get("destination", {}).get("solarSystemID")
        return cls(
            id=json_data.get("_key"),
            destination_id=dst_id,
            eve_type_id_raw=json_data.get("typeID"),
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


class Planet(UniverseBase):
    """
    mapPlanets.jsonl
        _key : int
        asteroidBeltIDs : list
        * attributes : dict
            attributes.heightMap1 : int
            attributes.heightMap2 : int
            attributes.population : bool
            attributes.shaderPreset : int
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
            statistics.density : float
            statistics.eccentricity : float
            statistics.escapeVelocity : float
            statistics.locked : bool
            statistics.massDust : float
            statistics.massGas : float
            statistics.orbitPeriod : float
            statistics.orbitRadius : float
            statistics.pressure : float
            statistics.rotationRate : float
            statistics.spectralClass : str
            statistics.surfaceGravity : float
            statistics.temperature : float
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
    _filename = "mapPlanets.jsonl"
    _update_fields = [
        "celestial_index",
        "name",
        "solar_system",
        "x",
        "y",
        "z",
        *get_langs_for_field("name")
    ]

    celestial_index = models.IntegerField()
    eve_type_id_raw = models.IntegerField()
    orbit_id_raw = models.IntegerField()
    orbit_index = models.IntegerField()
    radius = models.IntegerField()
    solar_system = models.ForeignKey(
        SolarSystem,
        on_delete=models.CASCADE,
        related_name="planet"
    )
    # eve_type = models.ForeignKey(
    #     EveType, on_delete=models.SET_NULL, null=True, default=None)

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
    def from_jsonl(cls, json_data, system_names):
        name = f"{system_names[json_data.get('solarSystemID')]["name"]} {to_roman_numeral(json_data.get('celestialIndex'))}"
        planet = cls(
            id=json_data.get("_key"),
            celestial_index=json_data.get("celestialIndex"),
            eve_type_id_raw=json_data.get("typeID"),
            name=name,
            orbit_id_raw=json_data.get("orbitID"),
            orbit_index=json_data.get("orbitIndex"),
            radius=json_data.get("radius"),
            solar_system_id=json_data.get("solarSystemID"),
            x=json_data.get("position", {}).get("x"),
            y=json_data.get("position", {}).get("y"),
            z=json_data.get("position", {}).get("z"),
        )

        for lang, name in system_names.get(json_data.get("solarSystemID"), {}).items():
            if lang.startswith("name_") and name is not None:
                # todo make this translatable properly
                _name = f"{name} {to_roman_numeral(json_data.get('celestialIndex'))}"
                setattr(planet, lang, _name)

        if json_data.get("uniqueName", False):
            for lang, name in json_data.get("name", {}).items():
                setattr(planet, f"name_{lang_key(lang)}", name)
                if lang == "en":
                    planet.name = name

        return planet


class Moon(UniverseBase):
    """
    "system_name planet_roman_numeral - Moon #"

    mapMoons.jsonl
        _key : int
        * attributes : dict
            attributes.heightMap1 : int
            attributes.heightMap2 : int
            attributes.shaderPreset : int
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
            statistics.density : float
            statistics.eccentricity : float
            statistics.escapeVelocity : float
            statistics.locked : bool
            statistics.massDust : float
            statistics.massGas : float
            statistics.orbitPeriod : float
            statistics.orbitRadius : float
            statistics.pressure : float
            statistics.rotationRate : float
            statistics.spectralClass : str
            statistics.surfaceGravity : float
            statistics.temperature : float
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
    _filename = "mapMoons.jsonl"
    _update_fields = [
        "name",
        "solar_system",
        "planet",
        "celestial_index",
        "eve_type_id_raw",
        "x",
        "y",
        "z",
        # *get_langs_for_field("name")
    ]

    celestial_index = models.IntegerField()
    eve_type_id_raw = models.IntegerField()
    orbit_id_raw = models.IntegerField()
    orbit_index = models.IntegerField()
    planet = models.ForeignKey(Planet, on_delete=models.CASCADE)
    solar_system = models.ForeignKey(SolarSystem, on_delete=models.CASCADE, related_name="moon")

    def __str__(self):
        return (self.name)

    @classmethod
    def name_lookup(cls):
        _langs = get_langs_for_field("name")
        return {
            s.get("id"): s for s in
            Planet.objects.all().values("id", "name", *_langs)
        }

    @classmethod
    def from_jsonl(cls, json_data, planet_names):
        name = f"{planet_names[json_data.get('orbitID')]["name"]} - Moon {json_data.get('orbitIndex')}"
        moon = cls(
            id=json_data.get("_key"),
            celestial_index=json_data.get("celestialIndex"),
            eve_type_id_raw=json_data.get("typeID"),
            name=name,
            orbit_id_raw=json_data.get("orbitID"),
            orbit_index=json_data.get("orbitIndex"),
            planet_id=json_data.get("orbitID"),
            solar_system_id=json_data.get("solarSystemID"),
            x=json_data.get("position", {}).get("x"),
            y=json_data.get("position", {}).get("y"),
            z=json_data.get("position", {}).get("z"),
        )

        if json_data.get("uniqueName", False):
            for lang, name in json_data.get("name", {}).items():
                setattr(moon, f"name_{lang_key(lang)}", name)
                if lang == "en":
                    moon.name = name

        return moon
