"""
Tests for selective updates: walking CCP's SDE changes feed and planning
which models need loading.
"""
# Standard Library
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from unittest import mock

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde import sde_tasks
from eve_sde.models import (
    BlueprintActivityProduct,
    EveSDESection,
    ItemType,
    Moon,
    Planet,
    SolarSystem,
)


def _changes(build, last_build, **files):
    lines = [{"_key": "_meta", "buildNumber": build, "lastBuildNumber": last_build}]
    lines += [{"_key": key} | record for key, record in files.items()]
    return "\n".join(json.dumps(_l) for _l in lines)


def _response(text=None, status=200):
    response = mock.MagicMock()
    response.text = text
    if status != 200:
        response.raise_for_status.side_effect = sde_tasks.httpx2.HTTPStatusError(
            str(status), request=mock.MagicMock(), response=mock.MagicMock(status_code=status)
        )
    return response


class FeedMixin:
    """httpx2.get serves `self.feed` {build: changes text or status code}."""

    def setUp(self):
        super().setUp()
        self.feed = {}
        self.requested = []

        def fake_get(url, **kwargs):
            build = int(url.rsplit("/", 1)[1].removesuffix(".jsonl"))
            self.requested.append(build)
            _r = self.feed.get(build, 404)
            return _response(status=_r) if isinstance(_r, int) else _response(_r)

        patcher = mock.patch.object(sde_tasks.httpx2, "get", side_effect=fake_get)
        patcher.start()
        self.addCleanup(patcher.stop)


class FetchSdeChangesTests(FeedMixin, TestCase):

    def test_walks_back_to_the_local_build(self):
        self.feed = {
            30: _changes(30, 20, types={"changed": [1]}),
            20: _changes(20, 10, groups={"added": [2]}),
            10: 403,
        }
        builds = sde_tasks.fetch_sde_changes(30, 10)

        self.assertEqual([_b for _b, _ in builds], [30, 20])
        self.assertEqual(builds[1][1], {"groups": {"_key": "groups", "added": [2]}})
        self.assertEqual(self.requested, [30, 20])

    def test_local_build_not_on_the_chain_stops_at_the_build_spanning_it(self):
        self.feed = {30: _changes(30, 20), 20: _changes(20, 10)}
        builds = sde_tasks.fetch_sde_changes(30, 15)

        self.assertEqual([_b for _b, _ in builds], [30, 20])

    def test_expired_history_returns_none(self):
        self.feed = {30: _changes(30, 20), 20: 403}
        self.assertIsNone(sde_tasks.fetch_sde_changes(30, 10))

    def test_missing_meta_returns_none(self):
        self.feed = {30: json.dumps({"_key": "types", "changed": [1]})}
        self.assertIsNone(sde_tasks.fetch_sde_changes(30, 10))

    def test_meta_for_another_build_returns_none(self):
        self.feed = {30: _changes(31, 20)}
        self.assertIsNone(sde_tasks.fetch_sde_changes(30, 10))

    def test_chain_that_does_not_go_backwards_returns_none(self):
        self.feed = {30: _changes(30, 30)}
        self.assertIsNone(sde_tasks.fetch_sde_changes(30, 10))

    def test_too_many_builds_returns_none(self):
        self.feed = {_b: _changes(_b, _b - 1) for _b in range(1, 101)}
        with mock.patch.object(sde_tasks, "SDE_MAX_CHANGE_BUILDS", 5):
            self.assertIsNone(sde_tasks.fetch_sde_changes(100, 1))
        self.assertEqual(len(self.requested), 5)

    def test_already_current_requests_nothing(self):
        self.assertEqual(sde_tasks.fetch_sde_changes(30, 30), [])
        self.assertEqual(self.requested, [])


class MergeSdeChangesTests(TestCase):

    def test_merges_builds_newer_than_since(self):
        builds = [
            (30, {"types": {"_key": "types", "changed": [1], "removed": [], "schemaChanged": True}}),
            (20, {"types": {"_key": "types", "added": [2]}, "groups": {"_key": "groups", "changed": [3]}}),
            (10, {"regions": {"_key": "regions", "changed": [4]}}),
        ]
        self.assertEqual(
            sde_tasks.merge_sde_changes(builds, 10),
            {
                "types": {"ops": {"changed", "schemaChanged", "added"}, "ids": {1, 2}},
                "groups": {"ops": {"changed"}, "ids": {3}},
            }
        )
        self.assertEqual(sde_tasks.merge_sde_changes(builds, 20), {
            "types": {"ops": {"changed", "schemaChanged"}, "ids": {1}},
        })

    def test_record_with_no_operations_is_not_a_change(self):
        builds = [(30, {"types": {"_key": "types", "changed": []}})]
        self.assertEqual(sde_tasks.merge_sde_changes(builds, 10), {})


class ChangeReasonTests(TestCase):

    @staticmethod
    def _c(ops, ids=()):
        return {"ops": set(ops), "ids": set(ids)}

    def test_own_file_change(self):
        self.assertEqual(ItemType.change_reason({"types": self._c(["changed"], [1])}), "types changed")
        self.assertIsNone(ItemType.change_reason({"groups": self._c(["changed"], [1])}))

    def test_own_file_removed_is_not_reloaded(self):
        with self.assertLogs("eve_sde.models.base", "ERROR"):
            self.assertIsNone(ItemType.change_reason({"types": self._c(["fileRemoved"])}))

    def test_own_schema_change_reloads_with_a_warning(self):
        with self.assertLogs("eve_sde.models.base", "WARNING"):
            self.assertEqual(ItemType.change_reason({"types": self._c(["schemaChanged"])}), "types schemaChanged")

    def test_depends_on_any_change(self):
        self.assertEqual(
            Planet.change_reason({"mapSolarSystems": self._c(["changedLocalization"], [30000142])}),
            "depends on mapSolarSystems",
        )

    def test_depends_on_ids(self):
        self.assertIsNone(Moon.change_reason({"types": self._c(["changed"], [587, 588])}))
        self.assertEqual(Moon.change_reason({"types": self._c(["changed"], [587, 14])}), "depends on types")
        # a file level change could touch any row
        self.assertEqual(Moon.change_reason({"types": self._c(["schemaChanged"])}), "depends on types")

    def test_depends_on_ops(self):
        self.assertIsNone(BlueprintActivityProduct.change_reason({"types": self._c(["changed"], [1])}))
        self.assertEqual(
            BlueprintActivityProduct.change_reason({"types": self._c(["changed", "removed"], [1])}),
            "depends on types",
        )


class ImportFingerprintTests(TestCase):

    def test_stable(self):
        self.assertEqual(Moon.import_fingerprint(), Moon.import_fingerprint())
        self.assertNotEqual(Moon.import_fingerprint(), Planet.import_fingerprint())

    def test_changes_with_the_import_config(self):
        before = SolarSystem.import_fingerprint()
        with mock.patch.object(SolarSystem.Import, "version", 99, create=True):
            self.assertNotEqual(SolarSystem.import_fingerprint(), before)
        with mock.patch.object(SolarSystem.Import, "data_map", SolarSystem.Import.data_map[:-1]):
            self.assertNotEqual(SolarSystem.import_fingerprint(), before)

    def test_changes_with_languages(self):
        before = SolarSystem.import_fingerprint()
        with self.settings(LANGUAGES=[("en", "English")]):
            self.assertNotEqual(SolarSystem.import_fingerprint(), before)


class PlanSdeUpdateTests(FeedMixin, TestCase):

    def setUp(self):
        super().setUp()
        self.models = sde_tasks.SDE_PARTS_TO_UPDATE
        self.now = datetime.now(tz=timezone.utc)
        for mdl in self.models:
            EveSDESection.objects.create(
                sde_section=mdl.__name__,
                build_number=20,
                last_update=self.now,
                total_lines=0,
                total_rows=0,
                import_fingerprint=mdl.import_fingerprint(),
            )

    def _names(self, plan):
        return {self.models[_i].__name__: _r for _i, _r in plan.items()}

    def test_up_to_date_loads_nothing(self):
        self.assertEqual(sde_tasks.plan_sde_update(20), {})
        self.assertEqual(self.requested, [])

    def test_only_changed_and_dependent_models(self):
        self.feed = {
            40: _changes(40, 30, mapSolarSystems={"changedLocalization": [1]}),
            30: _changes(30, 20, types={"changed": [14]}, typeDogma={"added": [5]}),
        }
        self.assertEqual(self._names(sde_tasks.plan_sde_update(40)), {
            "ItemType": "types changed",
            "TypeDogma": "typeDogma added",
            "TypeEffect": "typeDogma added",
            "SolarSystem": "mapSolarSystems changedLocalization",
            "Stargate": "depends on mapSolarSystems",
            "Planet": "depends on mapSolarSystems",
            "Moon": "depends on mapSolarSystems",
        })

    def test_each_model_only_sees_changes_since_it_was_loaded(self):
        # a run failed after ItemType loaded build 30
        EveSDESection.objects.filter(sde_section="ItemType").update(build_number=30)
        self.feed = {
            40: _changes(40, 30, mapRegions={"changed": [1]}),
            30: _changes(30, 20, types={"changed": [1]}, groups={"changed": [1]}),
        }
        self.assertEqual(set(self._names(sde_tasks.plan_sde_update(40))), {"ItemGroup", "Region"})

    def test_no_history_loads_every_model_behind(self):
        EveSDESection.objects.filter(sde_section="Region").update(build_number=40)
        self.feed = {40: 403}
        plan = self._names(sde_tasks.plan_sde_update(40))
        self.assertEqual(len(plan), len(self.models) - 1)
        self.assertNotIn("Region", plan)
        self.assertEqual(plan["ItemType"], "no SDE change history")

    def test_new_model_and_changed_import_code(self):
        EveSDESection.objects.filter(sde_section="Mastery").delete()
        EveSDESection.objects.filter(sde_section="Region").update(import_fingerprint="old")
        self.assertEqual(self._names(sde_tasks.plan_sde_update(20)), {
            "Region": "import code changed",
            "Mastery": "never loaded",
        })

    def test_models_not_loaded_for_a_while(self):
        EveSDESection.objects.filter(sde_section="Region").update(last_update=self.now - timedelta(days=31))
        with mock.patch.object(sde_tasks, "ESDE_FULL_UPDATE_DAYS", 30):
            self.assertEqual(set(self._names(sde_tasks.plan_sde_update(20))), {"Region"})
        with mock.patch.object(sde_tasks, "ESDE_FULL_UPDATE_DAYS", 0):
            self.assertEqual(sde_tasks.plan_sde_update(20), {})

    def test_full_and_disabled_load_everything(self):
        self.assertEqual(len(sde_tasks.plan_sde_update(20, full=True)), len(self.models))
        with mock.patch.object(sde_tasks, "ESDE_SELECTIVE_UPDATES", False):
            self.assertEqual(len(sde_tasks.plan_sde_update(20)), len(self.models))
        self.assertEqual(self.requested, [])


class FinishSdeUpdateTests(TestCase):

    def test_records_the_build_and_bumps_models_not_planned(self):
        now = datetime.now(tz=timezone.utc)
        for name, build in (("ItemType", 30), ("Region", 20)):
            EveSDESection.objects.create(
                sde_section=name, build_number=build, last_update=now, total_lines=0, total_rows=0
            )
        item_type = sde_tasks.SDE_PARTS_TO_UPDATE.index(ItemType)

        sde_tasks.finish_sde_update(
            {item_type: "types changed"},
            {"buildNumber": 30, "releaseDate": "2026-10-06T11:08:26Z"},
        )

        self.assertEqual(sde_tasks.EveSDE.get_solo().build_number, 30)
        self.assertEqual(EveSDESection.objects.get(sde_section="Region").build_number, 30)
        self.assertEqual(EveSDESection.objects.get(sde_section="Region").last_update, now)


class ProcessFromSdeSelectiveTests(TestCase):

    def test_nothing_to_load_downloads_nothing(self):
        latest = {"buildNumber": 30, "releaseDate": "2026-10-06T11:08:26Z"}
        with mock.patch.object(sde_tasks, "get_latest_sde", return_value=latest), \
                mock.patch.object(sde_tasks, "plan_sde_update", return_value={}), \
                mock.patch.object(sde_tasks, "download_extract_sde") as mock_download, \
                mock.patch.object(sde_tasks, "finish_sde_update") as mock_finish:
            sde_tasks.process_from_sde()

        mock_download.assert_not_called()
        mock_finish.assert_called_once_with({}, latest)

    def test_loads_only_planned_models_from_the_pinned_build(self):
        models = [mock.MagicMock(), mock.MagicMock(), mock.MagicMock()]
        with mock.patch.object(sde_tasks, "SDE_PARTS_TO_UPDATE", models), \
                mock.patch.object(sde_tasks, "get_latest_sde", return_value={"buildNumber": 30}), \
                mock.patch.object(sde_tasks, "plan_sde_update", return_value={1: "test"}), \
                mock.patch.object(sde_tasks, "log_sde_plan"), \
                mock.patch.object(sde_tasks, "download_extract_sde") as mock_download, \
                mock.patch.object(sde_tasks, "finish_sde_update") as mock_finish, \
                mock.patch.object(sde_tasks, "delete_sde_folder"):
            sde_tasks.process_from_sde()

        mock_download.assert_called_once_with(30)
        models[0].load_from_sde.assert_not_called()
        models[1].load_from_sde.assert_called_once()
        models[2].load_from_sde.assert_not_called()
        mock_finish.assert_called_once_with({1: "test"})


class DownloadPinnedBuildTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.zip_path = os.path.join(self.tmpdir, "sde.zip")
        self.extract_path = os.path.join(self.tmpdir, "sde-folder")
        for target, value in (("SDE_FILE_NAME", self.zip_path), ("SDE_FOLDER", self.extract_path)):
            patcher = mock.patch.object(sde_tasks, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with zipfile.ZipFile(self.zip_path, "w") as zf:
            zf.writestr("_sde.jsonl", '{"buildNumber": 30}')

    def test_downloads_the_build_url(self):
        with mock.patch.object(sde_tasks, "download_file") as mock_download:
            sde_tasks.download_extract_sde(30)

        self.assertEqual(mock_download.call_args.args[0], sde_tasks.SDE_BUILD_URL.format(build=30))
        self.assertTrue(os.path.exists(self.extract_path))

    def test_wrong_build_raises_and_cleans_up(self):
        with mock.patch.object(sde_tasks, "download_file"):
            with self.assertRaises(ValueError):
                sde_tasks.download_extract_sde(31)

        self.assertFalse(os.path.exists(self.extract_path))
