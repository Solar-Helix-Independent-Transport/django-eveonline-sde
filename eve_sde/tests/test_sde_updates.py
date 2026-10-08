"""
End to end SDE update tests: rows added, changed, translated and removed in
every way an SDE release can do it, run through the real selective update
(changes feed -> plan -> load), and compared table by table with what a
fresh full load of the same build gives.

See mini_sde.py for the harness and test_jsons/mini_sde for the fixture.
"""
# Standard Library
import copy
from datetime import timedelta
from unittest import mock

# Django
from django.test import TestCase
from django.utils import timezone

# Django EVE SDE
from eve_sde import sde_tasks
from eve_sde import tasks as celery_tasks
from eve_sde.models import (
    BlueprintActivity,
    BlueprintActivityMaterial,
    BlueprintActivityProduct,
    Certificate,
    CertificateSkill,
    Constellation,
    CorporationRoleGroupMembership,
    EveSDE,
    EveSDESection,
    FreelanceJobSchemaParameter,
    ItemCategory,
    ItemType,
    Landmark,
    Mastery,
    Moon,
    Planet,
    PlanetResource,
    Region,
    SkillPlanMilestone,
    SolarSystem,
    Star,
    Stargate,
    StarResource,
    TypeDogma,
    TypeListType,
)
from eve_sde.tests.mini_sde import SDEUpdateHarness, load_fixture

ALL_MODELS = [_m.__name__ for _m in sde_tasks.SDE_PARTS_TO_UPDATE]

RIFTER = 587
RIFTER_BLUEPRINT = 691
MOON_TYPE = 14
TANOO = 30000001
TANOO_I = 40000002
TANOO_I_MOON = 40000004
NULL_STAR = 40013180
NULL_SYSTEM = 30000208


def _names(**names):
    """A full set of SDE translations, en/de given, the rest derived from en."""
    out = {_l: f"{names['en']} ({_l})" for _l in ("es", "fr", "ja", "ko", "ru", "zh")}
    return out | names


def _pks(model, **filters):
    """{natural key: pk} so a test can check rows kept their pk."""
    fields = model.Import.natural_key
    return {_r[:-1]: _r[-1] for _r in model.objects.filter(**filters).values_list(*fields, "pk")}


# Mutations, each takes and edits a copy of the SDE, and they don't overlap
# so test_everything_at_once can apply them all in one build.

def change_types(sde):
    sde["types"][RIFTER]["mass"] = 1234567.0
    sde["types"][RIFTER]["name"]["de"] = "Rifter (neu)"  # translation only
    sde["types"][99001] = copy.deepcopy(sde["types"][RIFTER]) | {
        "_key": 99001, "name": _names(en="Rifter II", de="Rifter II de"),
    }
    del sde["types"][99001]["description"]


def change_categories(sde):
    # a language dropped from a row, and a new row
    del sde["categories"][6]["name"]["de"]
    sde["categories"][99] = {"_key": 99, "name": _names(en="New Category", de="Neu"), "published": True}


def change_type_dogma(sde):
    dogma = sde["typeDogma"][RIFTER]
    dogma["dogmaAttributes"] = [_a for _a in dogma["dogmaAttributes"] if _a["attributeID"] != 14]
    for _a in dogma["dogmaAttributes"]:
        if _a["attributeID"] == 9:
            _a["value"] = 400.0
    sde["dogmaAttributes"][99] = copy.deepcopy(sde["dogmaAttributes"][3]) | {"_key": 99, "name": "newAttribute"}
    dogma["dogmaAttributes"].append({"attributeID": 99, "value": 7.0})
    dogma["dogmaEffects"] = [_e for _e in dogma["dogmaEffects"] if _e["effectID"] != 7248]


def change_type_lists(sde):
    skills = sde["typeLists"][93]
    skills["includedTypeIDs"] = [_t for _t in skills["includedTypeIDs"] if _t not in (3300, 3302)]
    skills["excludedTypeIDs"] = [3300]  # moved from included to excluded
    sde["typeLists"][92]["includedGroupIDs"].append(7)
    sde["typeLists"][35]["excludedCategoryIDs"] = [6]
    sde["typeLists"][50]["displayName"] = _names(en="Renamed list", de="Umbenannt")


def change_blueprints(sde):
    manufacturing = sde["blueprints"][RIFTER_BLUEPRINT]["activities"]["manufacturing"]
    manufacturing["time"] = 9999
    manufacturing["materials"] = [_m for _m in manufacturing["materials"] if _m["typeID"] != 37]
    for _m in manufacturing["materials"]:
        if _m["typeID"] == 34:
            _m["quantity"] = 1
    invention = sde["blueprints"][RIFTER_BLUEPRINT]["activities"]["invention"]
    invention["products"][0]["probability"] = 0.5
    invention["products"] = invention["products"][:1]


def change_certificates(sde):
    cert = sde["certificates"][71]
    cert["skillTypes"][0]["elite"] = 4
    cert["skillTypes"] = cert["skillTypes"][:1]
    sde["certificates"][89]["recommendedFor"] = []
    sde["masteries"][RIFTER]["_value"][4]["_value"] = [71]


def change_misc(sde):
    sde["skillPlans"][4]["milestones"][0]["level"] = 5
    sde["skillPlans"][4]["milestones"].pop()
    sde["corporationRoles"][1]["roleGroupIDs"] = [4, 9]
    sde["typeMaterials"][RIFTER]["materials"].pop()
    sde["typeMaterials"][RIFTER]["materials"][0]["quantity"] = 1
    schemas = sde["freelanceJobSchemas"][1]["_value"]
    schemas[0]["parameters"] = schemas[0]["parameters"][:2]
    sde["accountingEntryTypes"][1]["name"]["de"] = "Spielerhandel (neu)"
    sde["notificationTypes"][4] = {
        "_key": 4, "displayName": _names(en="New Notification", de="Neu"),
        "internalName": "New"}


def remove_rows(sde):
    del sde["landmarks"][3]
    del sde["archetypes"][24]
    del sde["accountingEntryTypes"][2]
    del sde["notificationTypes"][3]
    del sde["types"][2502]  # the trade post type, and both stations of that type
    del sde["npcStations"][60012526]
    del sde["npcStations"][60014437]
    del sde["blueprints"][RIFTER_BLUEPRINT]["activities"]["copying"]


def rename_tanoo(sde):
    sde["mapSolarSystems"][TANOO]["name"] = _names(en="Tanoo Prime", de="Tanoo Prim")


def renumber_tanoo_i(sde):
    sde["mapPlanets"][TANOO_I]["celestialIndex"] = 3


def rename_moon_type(sde):
    sde["types"][MOON_TYPE]["name"] = _names(en="Moonlet", de="Mondchen")


MUTATIONS = [
    change_types, change_categories, change_type_dogma, change_type_lists, change_blueprints,
    change_certificates, change_misc, remove_rows, rename_tanoo, renumber_tanoo_i, rename_moon_type,
]


class SDEUpdateTestCase(SDEUpdateHarness, TestCase):
    """Starts each test with the fixture fully loaded as the first build."""

    def setUp(self):
        super().setUp()
        self.release(load_fixture())
        self.update()

    def next_build(self, *mutations):
        """Release the current build with `mutations` applied, run the update, return the models loaded."""
        sde = copy.deepcopy(self.releases[self.build])
        for mutation in mutations:
            mutation(sde)
        self.release(sde)
        return self.update()


class InitialAndNoChangeTests(SDEUpdateTestCase):

    def test_initial_load_loads_everything(self):
        self.assertEqual(set(self.plans[0].values()), {"never loaded"})
        self.assertEqual(self.loaded[0], ALL_MODELS)
        self.assertConstraintsHold()
        self.assertMatchesFullLoad()

    def test_new_build_without_changes_loads_and_downloads_nothing(self):
        with mock.patch.object(sde_tasks, "write_sde", create=True):
            loaded = self.next_build()

        self.assertEqual(loaded, [])
        self.assertEqual(EveSDE.get_solo().build_number, self.build)
        self.assertEqual(set(EveSDESection.objects.values_list("build_number", flat=True)), {self.build})
        self.assertMatchesFullLoad()


class PrimaryKeyModelTests(SDEUpdateTestCase):
    """Models whose rows are matched by the SDE _key."""

    def test_types_added_changed_and_translated(self):
        loaded = self.next_build(change_types)

        self.assertEqual(loaded, ["ItemType", "BlueprintActivityProduct", "BlueprintActivityMaterial"])
        rifter = ItemType.objects.get(pk=RIFTER)
        self.assertEqual(rifter.mass, 1234567.0)
        self.assertEqual(rifter.name_de, "Rifter (neu)")
        self.assertEqual(rifter.name_en, "Rifter")
        new = ItemType.objects.get(pk=99001)
        self.assertEqual((new.name_en, new.name_de, new.group_id), ("Rifter II", "Rifter II de", 25))
        self.assertMatchesFullLoad()

    def test_language_removed_from_a_row_is_cleared(self):
        self.assertIsNotNone(ItemCategory.objects.get(pk=6).name_de)

        self.assertEqual(self.next_build(change_categories), ["ItemCategory"])

        self.assertIsNone(ItemCategory.objects.get(pk=6).name_de)
        self.assertEqual(ItemCategory.objects.get(pk=99).name_de, "Neu")
        self.assertMatchesFullLoad()

    def test_translation_only_change(self):
        def german(sde):
            sde["mapRegions"][10000001]["name"]["de"] = "Derelik (de)"

        self.assertEqual(self.next_build(german), ["Region"])
        self.assertEqual(self.plans[-1]["Region"], "mapRegions changedLocalization")
        self.assertMatchesFullLoad()

    def test_rows_removed(self):
        self.next_build(remove_rows)

        self.assertFalse(ItemType.objects.filter(pk=2502).exists())
        self.assertFalse(BlueprintActivity.objects.filter(
            blueprint_item_type_id=RIFTER_BLUEPRINT, activity="copying").exists())
        self.assertFalse(Landmark.objects.filter(pk=3).exists())
        # nothing left waiting to be deleted
        self.assertEqual([_p for _p in EveSDESection.objects.values_list("removed_pks", flat=True) if _p], [])
        self.assertConstraintsHold()
        self.assertMatchesFullLoad()

    def test_planet_removed_with_its_moons_and_resources(self):
        def remove(sde):
            del sde["mapPlanets"][40013183]
            del sde["mapMoons"][40013185]
            del sde["planetResources"][40013183]

        # StarResource shares planetResources.jsonl
        self.assertEqual(self.next_build(remove), ["Planet", "PlanetResource", "StarResource", "Moon"])

        self.assertFalse(Planet.objects.filter(pk=40013183).exists())
        self.assertFalse(Moon.objects.filter(pk=40013185).exists())
        self.assertFalse(PlanetResource.objects.filter(planet_id=40013183).exists())
        self.assertMatchesFullLoad()

    def test_children_moved_before_their_old_parent_is_deleted(self):
        """
        A region removed and its constellation moved to another region. If the
        old region were deleted before the constellation was moved, the
        cascade would take the constellation, and null the solar systems'
        constellation, which aren't reloaded as their file didn't change.
        """
        def move(sde):
            del sde["mapRegions"][10000001]
            sde["mapConstellations"][20000001]["regionID"] = 10000003

        self.assertEqual(self.next_build(move), ["Region", "Constellation"])

        self.assertFalse(Region.objects.filter(pk=10000001).exists())
        self.assertEqual(Constellation.objects.get(pk=20000001).region_id, 10000003)
        self.assertEqual(SolarSystem.objects.get(pk=TANOO).constellation_id, 20000001)
        self.assertMatchesFullLoad()

    def test_rows_that_cannot_be_deleted_do_not_stop_the_update(self):
        with mock.patch.object(Landmark, "delete_removed", side_effect=RuntimeError("protected")), \
                self.assertLogs("eve_sde.sde_tasks", "ERROR"):
            self.next_build(remove_rows)

        self.assertTrue(Landmark.objects.filter(pk=3).exists())
        self.assertFalse(ItemType.objects.filter(pk=2502).exists())
        self.assertEqual(EveSDE.get_solo().build_number, self.build)


class NaturalKeyModelTests(SDEUpdateTestCase):
    """Child rows matched by their data, they keep their pks when unchanged."""

    def test_type_dogma(self):
        before = _pks(TypeDogma)

        loaded = self.next_build(change_type_dogma)

        self.assertEqual(loaded, ["DogmaAttribute", "TypeDogma", "TypeEffect"])
        after = _pks(TypeDogma)
        self.assertNotIn((RIFTER, 14), after)
        self.assertEqual(TypeDogma.objects.get(item_type_id=RIFTER, dogma_attribute_id=9).value, 400.0)
        self.assertEqual(TypeDogma.objects.get(item_type_id=RIFTER, dogma_attribute_id=99).value, 7.0)
        for key in ((RIFTER, 3), (RIFTER, 9), (RIFTER, 11)):
            self.assertEqual(after[key], before[key])
        self.assertMatchesFullLoad()

    def test_type_lists(self):
        before = _pks(TypeListType)

        loaded = self.next_build(change_type_lists)

        self.assertEqual(loaded, ["TypeList", "TypeListType", "TypeListGroup", "TypeListCategory"])
        after = _pks(TypeListType)
        self.assertIn((93, 3300, True), after)
        self.assertNotIn((93, 3300, False), after)
        self.assertNotIn((93, 3302, False), after)
        self.assertEqual(after[(93, 3327, False)], before[(93, 3327, False)])
        self.assertMatchesFullLoad()

    def test_blueprints(self):
        before = _pks(BlueprintActivityMaterial)

        self.assertEqual(
            self.next_build(change_blueprints),
            ["BlueprintActivity", "BlueprintActivityProduct", "BlueprintActivityMaterial"],
        )

        after = _pks(BlueprintActivityMaterial)
        manufacturing = f"{RIFTER_BLUEPRINT}:manufacturing"
        self.assertNotIn((manufacturing, 37), after)
        self.assertEqual(after[(manufacturing, 35)], before[(manufacturing, 35)])
        self.assertEqual(BlueprintActivityMaterial.objects.get(pk=after[(manufacturing, 34)]).quantity, 1)
        self.assertEqual(BlueprintActivityProduct.objects.filter(blueprint_activity__activity="invention").count(), 1)
        self.assertMatchesFullLoad()

    def test_parent_removed(self):
        def remove(sde):
            del sde["certificates"][89]
            for level in sde["masteries"][RIFTER]["_value"]:
                level["_value"] = [_c for _c in level["_value"] if _c != 89]

        self.next_build(remove)

        self.assertFalse(Certificate.objects.filter(pk=89).exists())
        self.assertFalse(CertificateSkill.objects.filter(certificate_id=89).exists())
        self.assertFalse(Mastery.objects.filter(certificate_id=89).exists())
        self.assertMatchesFullLoad()

    def test_certificates_and_masteries(self):
        before = _pks(Mastery)

        loaded = self.next_build(change_certificates)

        self.assertEqual(loaded, ["Certificate", "CertificateSkill", "CertificateRecommendedType", "Mastery"])
        self.assertEqual(CertificateSkill.objects.filter(certificate_id=71).count(), 1)
        after = _pks(Mastery)
        self.assertNotIn((RIFTER, 4, 89), after)
        self.assertEqual(after[(RIFTER, 4, 71)], before[(RIFTER, 4, 71)])
        self.assertMatchesFullLoad()

    def test_misc(self):
        loaded = self.next_build(change_misc)

        self.assertEqual(loaded, [
            "ItemTypeMaterials",
            "FreelanceJobSchema", "FreelanceJobSchemaParameter", "AccountingEntryType", "NotificationType",
            "CorporationRole", "CorporationRoleGroupMembership",
            "SkillPlan", "SkillPlanMilestone", "SkillPlanSkillRequirement",
        ])
        self.assertEqual(
            set(CorporationRoleGroupMembership.objects.filter(
                corporation_role_id=1).values_list("role_group_id", flat=True)),
            {4, 9},
        )
        self.assertEqual(SkillPlanMilestone.objects.count(), 2)
        self.assertEqual(FreelanceJobSchemaParameter.objects.count(), 5)
        self.assertMatchesFullLoad()


class DependencyTests(SDEUpdateTestCase):
    """Models built from other files reload when those files change."""

    def test_solar_system_renamed(self):
        loaded = self.next_build(rename_tanoo)

        self.assertEqual(loaded, ["SolarSystem", "Stargate", "Planet", "Moon"])
        self.assertEqual(Planet.objects.get(pk=TANOO_I).name, "Tanoo Prime I")
        self.assertEqual(Planet.objects.get(pk=TANOO_I).name_de, "Tanoo Prim I")
        self.assertEqual(Moon.objects.get(pk=TANOO_I_MOON).name, "Tanoo Prime I - Moon 1")
        self.assertIn("Tanoo Prime", Stargate.objects.get(solar_system_id=TANOO).name)
        self.assertMatchesFullLoad()

    def test_planet_renumbered(self):
        self.assertEqual(self.next_build(renumber_tanoo_i), ["Planet", "Moon"])
        self.assertEqual(Moon.objects.get(pk=TANOO_I_MOON).name, "Tanoo III - Moon 1")
        self.assertMatchesFullLoad()

    def test_moon_type_renamed(self):
        loaded = self.next_build(rename_moon_type)

        self.assertEqual(loaded, ["ItemType", "Moon"])
        self.assertEqual(Moon.objects.get(pk=TANOO_I_MOON).name, "Tanoo I - Moonlet 1")
        self.assertEqual(Moon.objects.get(pk=TANOO_I_MOON).name_de, "Tanoo I - Mondchen 1")
        self.assertMatchesFullLoad()

    def test_other_type_changed_does_not_reload_moons_or_blueprints(self):
        def other(sde):
            sde["types"][RIFTER]["mass"] = 1.0

        self.assertEqual(self.next_build(other), ["ItemType"])

    def test_resources_appear_when_their_planet_and_star_are_added(self):
        # resources for a planet and a star that aren't in the SDE yet are filtered out
        def resources_first(sde):
            sde["planetResources"][40099991] = {"_key": 40099991, "workforce": 11}
            sde["planetResources"][40099990] = {"_key": 40099990, "power": 22}

        self.next_build(resources_first)
        self.assertFalse(PlanetResource.objects.filter(planet_id=40099991).exists())

        def celestials_added(sde):
            sde["mapPlanets"][40099991] = copy.deepcopy(sde["mapPlanets"][40013181]) | {
                "_key": 40099991, "celestialIndex": 9, "moonIDs": [],
            }
            # one star per system, so the new star needs a new system
            sde["mapSolarSystems"][30099999] = copy.deepcopy(sde["mapSolarSystems"][NULL_SYSTEM]) | {
                "_key": 30099999, "name": _names(en="NEW-1", de="NEW-1"), "starID": 40099990, "planetIDs": [],
                "stargateIDs": [],
            }
            sde["mapStars"][40099990] = copy.deepcopy(sde["mapStars"][NULL_STAR]) | {
                "_key": 40099990, "solarSystemID": 30099999,
            }

        loaded = self.next_build(celestials_added)

        self.assertEqual(loaded, [
            "SolarSystem", "Star", "Stargate", "Planet", "PlanetResource", "StarResource", "Moon",
        ])
        self.assertEqual(PlanetResource.objects.get(planet_id=40099991).workforce, 11)
        self.assertEqual(StarResource.objects.get(star_id=40099990).power, 22)
        self.assertMatchesFullLoad()

    def test_blueprint_product_type_added_later(self):
        def unknown_product(sde):
            sde["blueprints"][RIFTER_BLUEPRINT]["activities"]["manufacturing"]["products"].append(
                {"quantity": 1, "typeID": 99002}
            )

        self.next_build(unknown_product)
        manufacturing = f"{RIFTER_BLUEPRINT}:manufacturing"
        self.assertTrue(BlueprintActivityProduct.objects.filter(
            blueprint_activity_id=manufacturing, item_type__isnull=True).exists())

        def type_added(sde):
            sde["types"][99002] = copy.deepcopy(sde["types"][RIFTER]) | {"_key": 99002}

        loaded = self.next_build(type_added)

        self.assertIn("BlueprintActivityProduct", loaded)
        self.assertTrue(BlueprintActivityProduct.objects.filter(
            blueprint_activity_id=manufacturing, item_type_id=99002).exists())
        self.assertFalse(BlueprintActivityProduct.objects.filter(item_type__isnull=True).exists())
        self.assertMatchesFullLoad()


class CatchUpTests(SDEUpdateTestCase):
    """Getting back in step after missed builds, failures and code changes."""

    def test_several_builds_behind(self):
        for mutation in (rename_tanoo, change_blueprints, change_types):
            sde = copy.deepcopy(self.releases[self.build])
            mutation(sde)
            self.release(sde)

        loaded = self.update()

        self.assertEqual(set(loaded), {
            "SolarSystem", "Stargate", "Planet", "Moon", "ItemType",
            "BlueprintActivity", "BlueprintActivityProduct", "BlueprintActivityMaterial",
        })
        self.assertMatchesFullLoad()

    def test_no_change_history_loads_everything(self):
        sde = copy.deepcopy(self.releases[self.build])
        change_types(sde)
        self.release(sde)
        self.feed[self.build] = 403

        loaded = self.update()

        self.assertEqual(loaded, ALL_MODELS)
        self.assertEqual(set(self.plans[-1].values()), {"no SDE change history"})
        self.assertMatchesFullLoad()

    def test_failure_partway_is_caught_up_by_the_next_run(self):
        sde = copy.deepcopy(self.releases[self.build])
        for mutation in MUTATIONS:
            mutation(sde)
        self.release(sde)
        failing_build = self.build

        real_load = Planet.load_from_sde
        with mock.patch.object(Planet, "load_from_sde", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.update()

        # loaded before the failure: new build, the rest still on the old one
        sections = dict(EveSDESection.objects.values_list("sde_section", "build_number"))
        self.assertEqual(sections["SolarSystem"], failing_build)
        self.assertEqual(sections["Planet"], failing_build - 1)
        self.assertEqual(sections["Mastery"], failing_build - 1)
        self.assertEqual(EveSDE.get_solo().build_number, failing_build - 1)
        self.assertIsNotNone(real_load)
        # ItemType loaded and found the removed type, the failed run didn't delete it
        self.assertTrue(ItemType.objects.filter(pk=2502).exists())
        self.assertEqual(EveSDESection.objects.get(sde_section="ItemType").removed_pks, [2502])

        loaded = self.update()

        # ItemType is current so it isn't reloaded, but its removed row is still deleted
        self.assertNotIn("ItemType", loaded)
        self.assertFalse(ItemType.objects.filter(pk=2502).exists())
        self.assertNotIn("SolarSystem", loaded)
        self.assertIn("Planet", loaded)
        self.assertIn("Moon", loaded)
        self.assertIn("Mastery", loaded)
        self.assertMatchesFullLoad()

    def test_import_code_changed(self):
        with mock.patch.object(Moon.Import, "version", 2, create=True):
            loaded = self.next_build()
            self.assertEqual(loaded, ["Moon"])
            self.assertEqual(self.plans[-1]["Moon"], "import code changed")
            # and it's now current, the next build doesn't reload it
            self.assertEqual(self.next_build(), [])

    def test_language_added_to_the_site(self):
        langs = [("en", "English"), ("de", "German")]
        with self.settings(LANGUAGES=langs):
            self.assertEqual(self.next_build(), ALL_MODELS)

    def test_model_not_loaded_for_a_while(self):
        EveSDESection.objects.filter(sde_section="Star").update(last_update=timezone.now() - timedelta(days=60))

        self.assertEqual(self.next_build(), ["Star"])

    def test_full_update(self):
        sde = copy.deepcopy(self.releases[self.build])
        self.release(sde)
        self.assertEqual(self.update(full=True), ALL_MODELS)


class EverythingAtOnceTests(SDEUpdateTestCase):

    def test_everything_at_once(self):
        loaded = self.next_build(*MUTATIONS)

        self.assertNotIn("Region", loaded)
        self.assertNotIn("Constellation", loaded)
        self.assertConstraintsHold()
        self.assertMatchesFullLoad()

    def test_split_celery_tasks(self):
        """ESDE_TASK_SPLIT runs the same plan as a chain of tasks."""
        sde = copy.deepcopy(self.releases[self.build])
        for mutation in MUTATIONS:
            mutation(sde)
        self.release(sde)

        class EagerChain:
            def __init__(self, queue):
                self.queue = queue

            def apply_async(self, **kwargs):
                for signature in self.queue:
                    signature()

        with mock.patch.object(celery_tasks, "ESDE_TASK_SPLIT", True), \
                mock.patch.object(celery_tasks, "chain", EagerChain), \
                mock.patch.multiple(
                    celery_tasks,
                    get_latest_sde=sde_tasks.get_latest_sde,
                    plan_sde_update=sde_tasks.plan_sde_update,
                    download_extract_sde=sde_tasks.download_extract_sde,
                    process_section_of_sde=sde_tasks.process_section_of_sde,
        ):
            celery_tasks.update_models_from_sde()

        self.assertIn("Moon", self.loaded[-1])
        self.assertFalse(ItemType.objects.filter(pk=2502).exists())
        self.assertEqual(EveSDE.get_solo().build_number, self.build)
        self.assertEqual(set(EveSDESection.objects.values_list("build_number", flat=True)), {self.build})
        self.assertMatchesFullLoad()


class HarnessSanityTests(SDEUpdateTestCase):
    """The comparison would catch a model that wasn't reloaded."""

    def test_skipping_a_needed_model_is_caught(self):
        sde = copy.deepcopy(self.releases[self.build])
        rename_tanoo(sde)
        self.release(sde)
        planet = sde_tasks.SDE_PARTS_TO_UPDATE.index(Planet)
        self.plan_hook = lambda plan: {_i: _r for _i, _r in plan.items() if _i != planet}
        self.update()
        self.plan_hook = None

        with self.assertRaises(AssertionError):
            self.assertMatchesFullLoad()

    def test_fixture_has_rows_in_every_table(self):
        counts = {_m.__name__: _m.objects.count() for _m in sde_tasks.SDE_PARTS_TO_UPDATE}
        self.assertEqual([_n for _n, _c in counts.items() if not _c], [])
        self.assertEqual(SolarSystem.objects.get(pk=NULL_SYSTEM).planets.count(), 2)
        self.assertTrue(Star.objects.filter(pk=NULL_STAR).exists())
        self.assertTrue(Certificate.objects.exists())
