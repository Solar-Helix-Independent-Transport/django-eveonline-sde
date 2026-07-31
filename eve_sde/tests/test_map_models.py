"""
Tests for the remaining under-covered pieces of map.py:
- Region/Constellation's reverse-lookup convenience properties.
- SolarSystem's security-classification properties (high/low/null/wh/
    triglavian/abyssal), including the two deprecated aliases.
- Stargate: a fully custom from_jsonl/name_lookup (no data_map at all) that
    builds a "system A >> system B" display name, wiped and reloaded on
    every run like the other "don't F-key to this" models.
- Planet/Moon's __str__ and localized_name, and Moon's two-part
    name_lookup/format_name (it derives its name from both its parent planet
    AND its own item type, unlike Planet which only needs the solar system).
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.map import (
    POCHVEN_REGION_ID,
    Constellation,
    Moon,
    Planet,
    Region,
    SolarSystem,
    Stargate,
)
from eve_sde.models.types import ItemType


class RegionConstellationLookupPropertyTests(TestCase):

    def setUp(self):
        self.region = Region.objects.create(id=1, name="The Forge")
        self.constellation = Constellation.objects.create(id=2, name="Kimotoro", region=self.region)
        self.system = SolarSystem.objects.create(id=3, name="Jita", constellation=self.constellation)

    def test_universe_base_str(self):
        self.assertEqual(str(self.region), "The Forge (1)")

    def test_region_constellations_and_solar_systems(self):
        self.assertEqual(list(self.region.constellations), [self.constellation])
        self.assertEqual(list(self.region.solar_systems), [self.system])

    def test_constellation_solar_systems(self):
        self.assertEqual(list(self.constellation.solar_systems), [self.system])


class SolarSystemSecurityClassificationTests(TestCase):

    def setUp(self):
        self.region = Region.objects.create(id=1, name="The Forge")
        self.pochven = Region.objects.create(id=POCHVEN_REGION_ID, name="Pochven")
        self.constellation = Constellation.objects.create(id=2, name="Kimotoro", region=self.region)
        self.pochven_constellation = Constellation.objects.create(id=3, name="Kino", region=self.pochven)

    def test_high_sec(self):
        system = SolarSystem.objects.create(
            id=30000001, name="Jita", constellation=self.constellation, security_status=0.9,
        )
        self.assertTrue(system.is_high_sec)
        self.assertFalse(system.is_low_sec)
        self.assertFalse(system.is_null_sec)

    def test_low_sec(self):
        system = SolarSystem.objects.create(
            id=30000002, name="Rancer", constellation=self.constellation, security_status=0.3,
        )
        self.assertFalse(system.is_high_sec)
        self.assertTrue(system.is_low_sec)
        self.assertFalse(system.is_null_sec)

    def test_null_sec(self):
        system = SolarSystem.objects.create(
            id=30000003, name="Deklein System", constellation=self.constellation, security_status=-0.2,
        )
        self.assertTrue(system.is_null_sec)
        self.assertFalse(system.is_wh_space)
        self.assertFalse(system.is_triglavian_space)
        self.assertFalse(system.is_abyssal_deadspace)

    def test_triglavian_space(self):
        system = SolarSystem.objects.create(
            id=30000004, name="Kino System", constellation=self.pochven_constellation, security_status=-0.2,
        )
        self.assertTrue(system.is_triglavian_space)
        self.assertTrue(system.is_trig_space)  # deprecated alias
        # null-sec explicitly excludes triglavian space
        self.assertFalse(system.is_null_sec)

    def test_wormhole_space(self):
        system = SolarSystem.objects.create(
            id=31000005, name="J000000", constellation=self.constellation, security_status=-1.0,
        )
        self.assertTrue(system.is_wh_space)
        self.assertTrue(system.is_w_space)  # deprecated alias
        self.assertFalse(system.is_null_sec)

    def test_abyssal_deadspace(self):
        system = SolarSystem.objects.create(
            id=32000006, name="Abyssal Pocket", constellation=self.constellation, security_status=-1.0,
        )
        self.assertTrue(system.is_abyssal_deadspace)
        self.assertFalse(system.is_null_sec)


class StargateTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        SolarSystem.objects.create(id=30000001, name="Jita")
        SolarSystem.objects.create(id=30000002, name="Perimeter")

        row = {
            "_key": 1000,
            "solarSystemID": 30000001,
            "destination": {"solarSystemID": 30000002, "stargateID": 1001},
        }
        with open(os.path.join(self.tmpdir, "mapStargates.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

    def test_builds_a_display_name_from_both_systems(self):
        Stargate.load_from_sde(self.tmpdir)

        self.assertEqual(Stargate.objects.count(), 1)
        gate = Stargate.objects.get(pk=1000)
        self.assertEqual(gate.name, "Jita ≫ Perimeter")
        self.assertEqual(str(gate), "Jita ≫ Perimeter")
        self.assertEqual(gate.solar_system_id, 30000001)
        self.assertEqual(gate.destination_id, 30000002)

    def test_rerun_wipes_and_reloads_instead_of_duplicating(self):
        Stargate.load_from_sde(self.tmpdir)
        Stargate.load_from_sde(self.tmpdir)

        self.assertEqual(Stargate.objects.count(), 1)


class PlanetMoonDisplayTests(TestCase):

    def setUp(self):
        self.system = SolarSystem.objects.create(id=30000001, name="Jita", name_en="Jita")
        self.moon_type = ItemType.objects.create(id=14, name="Moon", name_en="Moon")
        self.planet = Planet.objects.create(
            id=40000001, name="Jita IV", celestial_index=4, solar_system=self.system,
        )

    def test_planet_str_and_localized_name(self):
        self.assertEqual(str(self.planet), "Jita IV")
        self.assertEqual(self.planet.localized_name, "Jita IV")

    def test_moon_str_and_localized_name(self):
        moon = Moon.objects.create(
            id=40000002,
            name="Jita IV - Moon 1",
            celestial_index=4,
            orbit_index=1,
            planet=self.planet,
            solar_system=self.system,
            item_type=self.moon_type,
        )

        self.assertEqual(str(moon), "Jita IV - Moon 1")
        self.assertEqual(moon.localized_name, "Jita IV - Moon 1")

    def test_moon_name_lookup_and_format_name(self):
        name_lookup = Moon.name_lookup()

        data = {"orbitID": self.planet.pk, "typeID": self.moon_type.pk, "orbitIndex": 1}
        name = Moon.format_name(data, name_lookup, lang="en")

        self.assertEqual(name, "Jita IV - Moon 1")

    def test_format_name_falls_back_to_plain_name_when_language_variant_is_unset(self):
        # neither the planet nor the (real) moon item type has a name_de
        # value set - both fall back to their plain "name" field rather
        # than the literal "Moon" default parameter
        name_lookup = Moon.name_lookup()

        data = {"orbitID": self.planet.pk, "typeID": self.moon_type.pk, "orbitIndex": 1}
        name = Moon.format_name(data, name_lookup, lang="de")

        self.assertEqual(name, "Jita IV - Moon 1")
