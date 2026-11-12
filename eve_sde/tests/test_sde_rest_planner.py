"""
Selective updates from the SDE REST API: plan_sde_update with
ESDE_SOURCE="rest" checks each section's stored table versions first, and
only asks _changes (one release deep) what changed when one has moved.
Without usable _changes, every section whose versions moved reloads.

Worked examples follow .scratch/sde-rest/spec.md §4.2.
"""
# Standard Library
import os
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

# Django
from django.test import TestCase
from django.utils import timezone

# Django EVE SDE
from eve_sde import sde_tasks
from eve_sde.models import EveSDE, EveSDESection, Region
from eve_sde.sde_rest import sde_tables_for
from eve_sde.tests.rest_fakes import ALL_TABLES, BASE, PREVIOUS, RELEASE, FakeCCP


def changed(table, ints=(), op="changed", **flags):
    """One table's record in _changes, CCP's shape."""
    return {"table": table, op: {"ints": list(ints), "strings": []}} | flags


class RestPlannerTestCase(TestCase):

    def setUp(self):
        patcher = mock.patch.object(sde_tasks, "ESDE_SOURCE", "rest")
        patcher.start()
        self.addCleanup(patcher.stop)

    def settle(self, release=PREVIOUS, **overrides):
        """
        Every section loaded from `release`, with the v-<table> versions the
        fake serves unless moved, so nothing needs loading until a test moves
        something.
        """
        for mdl in sde_tasks.SDE_PARTS_TO_UPDATE:
            EveSDESection.objects.create(**{
                "sde_section": mdl.__name__,
                "build_number": 3682781,
                "last_update": timezone.now(),
                "total_lines": 1,
                "total_rows": 1,
                "import_fingerprint": mdl.import_fingerprint(),
                "release": release,
                "versions": {_t: f"v-{_t}" for _t in sde_tables_for([mdl])},
            } | overrides.get(mdl.__name__, {}))

    def serve(self, moved=(), changes=None, compared_with=PREVIOUS):
        """Publish RELEASE with the tables in `moved` at new versions."""
        self.ccp = FakeCCP(
            {_t: [] for _t in ALL_TABLES},
            versions={_t: f"v2-{_t}" for _t in moved},
            changes=changes,
            compared_with=compared_with,
        )
        self.ccp.install(self)
        return self.ccp.index

    def plan(self, full=False):
        index = sde_tasks.get_sde_release()
        plan = sde_tasks.plan_sde_update(index, full=full)
        return {sde_tasks.SDE_PARTS_TO_UPDATE[_i].__name__: _r for _i, _r in plan.items()}


class VersionCheckTests(RestPlannerTestCase):

    def test_nothing_moved_plans_nothing_and_never_asks_for_changes(self):
        self.settle()
        self.serve()

        self.assertEqual(self.plan(), {})
        self.assertNotIn(f"{BASE}/{RELEASE}/_changes.jsonl", self.ccp.requested)

    def test_a_section_missing_a_stored_version_is_checked(self):
        self.settle(Region={"versions": {}})
        self.serve(changes=[changed("mapRegions", [10000002])])

        self.assertEqual(self.plan(), {"Region": "mapRegions changed"})


class ChangesTests(RestPlannerTestCase):
    """One release behind: _changes decides."""

    def test_only_the_models_whose_rows_changed_reload(self):
        # 083900Z -> 110708Z: types changed, but not the moon type (14), nothing added or removed
        self.settle()
        self.serve(moved=["types", "groups"], changes=[
            changed("types", [587, 2652]),
            changed("groups", [5270], op="changedLocalization"),
        ])

        self.assertEqual(self.plan(), {
            "ItemGroup": "groups changedLocalization",
            "ItemType": "types changed",
        })

    def test_dependency_rows_that_matter_reload_the_dependent(self):
        self.settle()
        self.serve(moved=["types"], changes=[changed("types", [14])])

        plan = self.plan()

        self.assertEqual(plan["Moon"], "depends on types")
        self.assertNotIn("BlueprintActivityProduct", plan)  # only cares about added / removed types

    def test_republish_with_no_row_changes_plans_nothing(self):
        # 110708Z -> 160425Z: every version moved, _changes is empty
        self.settle()
        self.serve(moved=ALL_TABLES, changes=[])

        self.assertEqual(self.plan(), {})


class NoChangesTests(RestPlannerTestCase):
    """More than one release behind, or never loaded from REST: versions decide."""

    def test_sections_whose_versions_moved_reload(self):
        self.settle(release="20261110T000000Z")
        self.serve(moved=["mapRegions", "mapPlanets"], changes=[changed("mapRegions", [1])])

        plan = self.plan()

        self.assertEqual(plan["Region"], "no row-level history")
        self.assertEqual(plan["Planet"], "no row-level history")
        self.assertEqual(plan["Moon"], "no row-level history")  # depends on mapPlanets
        self.assertNotIn("ItemType", plan)

    def test_first_rest_run_after_the_zip_reloads_everything(self):
        self.settle(release=None)
        for _s in EveSDESection.objects.all():
            _s.versions = {}
            _s.save()
        self.serve()

        self.assertEqual(len(self.plan()), len(sde_tasks.SDE_PARTS_TO_UPDATE))


class ExistingReasonsTests(RestPlannerTestCase):

    def test_existing_reasons_still_apply(self):
        self.settle(
            Region={"import_fingerprint": "old"},
            Planet={"last_update": timezone.now() - timedelta(days=365)},
        )
        EveSDESection.objects.filter(sde_section="Moon").delete()
        self.serve()

        plan = self.plan()

        self.assertEqual(plan["Region"], "import code changed")
        self.assertIn("not loaded in", plan["Planet"])
        self.assertEqual(plan["Moon"], "never loaded")

    def test_full(self):
        self.settle()
        self.serve()

        self.assertEqual(set(self.plan(full=True).values()), {"full update"})


class CheckSdeVersionTests(RestPlannerTestCase):

    def test_compares_the_release(self):
        sde = EveSDE.get_solo()
        sde.build_number = 3687575
        sde.release = PREVIOUS  # same build, re-published
        sde.save()
        self.serve()

        self.assertFalse(sde_tasks.check_sde_version())

        sde.release = RELEASE
        sde.save()
        self.assertTrue(sde_tasks.check_sde_version())


class RestUpdateRunTests(RestPlannerTestCase):
    """process_from_sde in REST mode: fetch what the plan needs, load it, record the release."""

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        patcher = mock.patch.object(sde_tasks, "SDE_FOLDER", os.path.join(self.tmpdir, "eve-sde"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def serve_regions(self):
        self.ccp = FakeCCP(
            {_t: [] for _t in ALL_TABLES} | {"mapRegions": [{"regionID": 10000002, "name": {"en": "The Forge"}}]},
            versions={"mapRegions": "v2-mapRegions"},
            changes=[changed("mapRegions", [10000002], op="added")],
        )
        self.ccp.install(self)

    def test_fetches_and_loads_only_what_changed(self):
        self.settle()
        self.serve_regions()

        sde_tasks.process_from_sde()

        self.assertEqual(self.ccp.table_urls(), ["_changes", "mapRegions"])
        self.assertEqual(Region.objects.get(pk=10000002).name, "The Forge")
        section = EveSDESection.objects.get(sde_section="Region")
        self.assertEqual((section.release, section.versions), (RELEASE, {"mapRegions": "v2-mapRegions"}))

    def test_records_the_release_on_the_sde_and_every_skipped_section(self):
        self.settle()
        self.serve_regions()

        sde_tasks.process_from_sde()

        sde = EveSDE.get_solo()
        self.assertEqual((sde.release, sde.build_number), (RELEASE, 3687575))
        moon = EveSDESection.objects.get(sde_section="Moon")
        self.assertEqual(moon.release, RELEASE)
        self.assertEqual(moon.build_number, 3687575)
        self.assertEqual(moon.versions, {
            "mapMoons": "v-mapMoons", "mapPlanets": "v-mapPlanets",
            "mapSolarSystems": "v-mapSolarSystems", "types": "v-types",
        })

    def test_nothing_to_load_downloads_nothing(self):
        self.settle()
        self.serve()

        sde_tasks.process_from_sde()

        self.assertEqual(self.ccp.table_urls(), [])
        self.assertEqual(EveSDE.get_solo().release, RELEASE)
