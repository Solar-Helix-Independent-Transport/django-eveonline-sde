"""
Harness for end to end SDE update tests against the mini SDE fixture
(test_jsons/mini_sde, built by test_jsons/make_mini_sde.py).

Each test releases SDE builds: a copy of the fixture, mutated however the
test likes. The harness serves them the way CCP does - latest.jsonl, a
changes/<build>.jsonl diffed from the previous release, and the pinned
build zip (written straight to the SDE folder) - and runs the real
process_from_sde. Only the network is faked.
"""
# Standard Library
import copy
import json
import os
import shutil
import tempfile
from unittest import mock

# Django
from django.db import connection, models

# Django EVE SDE
from eve_sde import sde_tasks
from eve_sde.models import EveSDE, EveSDESection

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_jsons", "mini_sde")
FIRST_BUILD = 1000


def load_fixture():
    """{file key: {_key: record}}"""
    sde = {}
    for filename in sorted(os.listdir(FIXTURE)):
        if filename.endswith(".jsonl") and not filename.startswith("_"):
            with open(os.path.join(FIXTURE, filename)) as f:
                sde[filename.removesuffix(".jsonl")] = {
                    (_r := json.loads(_l))["_key"]: _r for _l in f if _l.strip()
                }
    return sde


def write_sde(folder, sde, build):
    os.makedirs(folder, exist_ok=True)
    for key, rows in sde.items():
        with open(os.path.join(folder, f"{key}.jsonl"), "w") as f:
            for row in rows.values():
                f.write(json.dumps(row) + "\n")
    with open(os.path.join(folder, "_sde.jsonl"), "w") as f:
        f.write(json.dumps({"_key": "sde", "buildNumber": build, "releaseDate": "2026-10-06T11:08:26Z"}))


def _without_localization(value):
    """The record with every {"en": ..., "de": ...} dict blanked out."""
    if isinstance(value, dict):
        if "en" in value and all(isinstance(_v, str) for _v in value.values()):
            return None
        return {_k: _without_localization(_v) for _k, _v in value.items()}
    if isinstance(value, list):
        return [_without_localization(_v) for _v in value]
    return value


def diff_sde(old, new):
    """
    {file key: change record} the way CCP's changes feed describes going
    from `old` to `new`. A row whose only differences are translations is
    changedLocalization, like CCP's.
    """
    changes = {}
    for key in sorted(set(old) | set(new)):
        before = old.get(key)
        after = new.get(key)
        if before is None:
            changes[key] = {"fileAdded": True, "added": sorted(after)}
            continue
        if after is None:
            changes[key] = {"fileRemoved": True}
            continue
        record = {
            "added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": [],
            "changedLocalization": [],
        }
        for _k in sorted(set(before) & set(after)):
            if before[_k] != after[_k]:
                if _without_localization(before[_k]) == _without_localization(after[_k]):
                    record["changedLocalization"].append(_k)
                else:
                    record["changed"].append(_k)
        record = {_op: _ids for _op, _ids in record.items() if _ids}
        if record:
            changes[key] = record
    return changes


def snapshot():
    """
    {model name: sorted rows} of every SDE table. Auto pks are left out, so a
    natural key model compares by its data, whatever pks its rows were given.
    """
    out = {}
    for mdl in sde_tasks.SDE_PARTS_TO_UPDATE:
        fields = [
            _f.attname for _f in mdl._meta.concrete_fields
            if not isinstance(_f, models.AutoField)
        ]
        rows = mdl._base_manager.all()
        if hasattr(rows, "rewrite"):
            rows = rows.rewrite(False)
        out[mdl.__name__] = sorted(rows.values_list(*fields), key=repr)
    return out


def wipe():
    for mdl in reversed(sde_tasks.SDE_PARTS_TO_UPDATE):
        mdl._base_manager.all().delete()
    EveSDESection.objects.all().delete()
    EveSDE.objects.all().delete()


class SDEUpdateHarness:
    """TestCase mixin, see the module docstring."""

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.releases = {}  # build: sde
        self.feed = {}  # build: changes text, or an int status code
        self.build = None
        self.plans = []  # {model name: reason} per update run
        self.loaded = []  # model names per update run
        self.plan_hook = None  # optional fn(plan) -> plan, lets a test break the planner

        for target, value in (
            ("SDE_FOLDER", os.path.join(self.tmpdir, "eve-sde")),
            ("SDE_FILE_NAME", os.path.join(self.tmpdir, "sde.zip")),
        ):
            patcher = mock.patch.object(sde_tasks, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

        real_plan = sde_tasks.plan_sde_update
        real_process = sde_tasks.process_section_of_sde

        def plan(target_build, full=False):
            _plan = real_plan(target_build, full=full)
            if self.plan_hook:
                _plan = self.plan_hook(_plan)
            self.plans.append({sde_tasks.SDE_PARTS_TO_UPDATE[_i].__name__: _r for _i, _r in _plan.items()})
            self.loaded.append([])
            return _plan

        def process(idx):
            self.loaded[-1].append(sde_tasks.SDE_PARTS_TO_UPDATE[idx].__name__)
            real_process(idx)

        for target, side_effect in (
            ("plan_sde_update", plan),
            ("process_section_of_sde", process),
            ("download_extract_sde", self._download),
            ("get_latest_sde", self._latest),
        ):
            patcher = mock.patch.object(sde_tasks, target, side_effect=side_effect)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(sde_tasks.httpx2, "get", side_effect=self._get)
        patcher.start()
        self.addCleanup(patcher.stop)

    # fake CCP
    def _latest(self):
        return {"_key": "sde", "buildNumber": self.build, "releaseDate": "2026-10-06T11:08:26Z"}

    def _download(self, build=None):
        write_sde(sde_tasks.SDE_FOLDER, self.releases[build or self.build], build or self.build)

    def _get(self, url, **kwargs):
        build = int(url.rsplit("/", 1)[1].removesuffix(".jsonl"))
        response = mock.MagicMock()
        body = self.feed.get(build, 404)
        if isinstance(body, int):
            response.raise_for_status.side_effect = sde_tasks.httpx2.HTTPStatusError(
                str(body), request=mock.MagicMock(), response=mock.MagicMock(status_code=body)
            )
        else:
            response.text = body
        return response

    # test API
    def release(self, sde):
        """Publish `sde` as the next build, with a changes file from the previous one."""
        sde = copy.deepcopy(sde)
        previous = self.build
        self.build = FIRST_BUILD if previous is None else previous + 1
        self.releases[self.build] = sde
        if previous is not None:
            lines = [{"_key": "_meta", "buildNumber": self.build, "lastBuildNumber": previous}]
            lines += [{"_key": _k} | _c for _k, _c in diff_sde(self.releases[previous], sde).items()]
            self.feed[self.build] = "\n".join(json.dumps(_l) for _l in lines)
        return self.build

    def update(self, full=False):
        """Run the real update, returns the models it loaded."""
        sde_tasks.process_from_sde(full=full)
        return self.loaded[-1]

    def full_load_snapshot(self, sde):
        """What a fresh full load of `sde` gives, then puts the DB back to that."""
        wipe()
        build = self.build
        self.release(sde)
        self.update(full=True)
        self.build = build
        return snapshot()

    def assertMatchesFullLoad(self, sde=None):
        """The DB is exactly what a fresh full load of `sde` (default: the latest build) gives."""
        sde = self.releases[self.build] if sde is None else sde
        selective = snapshot()
        full = self.full_load_snapshot(sde)
        for name in full:
            self.assertEqual(selective[name], full[name], f"{name} differs from a full load")

    def assertConstraintsHold(self):
        connection.check_constraints()
