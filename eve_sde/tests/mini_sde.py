"""
Harness for end to end SDE update tests against the mini SDE fixture
(test_jsons/mini_sde, built by test_jsons/make_mini_sde.py).

Each test releases SDE builds: a copy of the fixture, mutated however the
test likes. The harness serves them the way CCP does, from both sources:

zip: latest.jsonl, a changes/<build>.jsonl diffed from the previous
release, and the pinned build zip (written straight to the SDE folder).

REST: a release index with content-hash table versions, each table in REST
shape (real schemas from test_jsons/rest_schemas), and _changes against the
previous release. Only the last two releases are kept.

`source` picks which one the update reads, and the real process_from_sde
runs. Only the network is faked.
"""
# Standard Library
import copy
import hashlib
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
from eve_sde.sde_rest import sde_file_urls
from eve_sde.tests.rest_fakes import BASE, install_fake_http, schema, to_rest

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_jsons", "mini_sde")
FIRST_BUILD = 1000
REST_RETAINED = 2  # CCP keeps the current and previous release


def rest_release_name(build, republish=0):
    return f"2026{build:08d}T{republish:06d}Z"


def diff_to_rest_changes(changes):
    """diff_sde's {table: record} as the tables list of a REST _changes record."""
    out = []
    for table, record in changes.items():
        entry = {"table": table}
        for op, val in record.items():
            if isinstance(val, list):
                entry[op] = {
                    "ints": [_i for _i in val if isinstance(_i, int)],
                    "strings": [_i for _i in val if not isinstance(_i, int)],
                }
            else:
                entry[op] = val
        out.append(entry)
    return out


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

    source = "zip"

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
        self.rest_files = {}  # url: body
        self.rest_blobs = {}  # blob url: the release url it's the file of
        self._rest_sde = {}  # release name: sde
        self._republished = 0
        self.rest_releases = []  # release names, oldest first
        self.requested = []  # every URL asked for

        for target, value in (
            ("SDE_FOLDER", os.path.join(self.tmpdir, "eve-sde")),
            ("SDE_FILE_NAME", os.path.join(self.tmpdir, "sde.zip")),
            ("ESDE_SOURCE", self.source),
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
        install_fake_http(self, self._get, self._stream)

    # fake CCP
    def _latest(self):
        return {"_key": "sde", "buildNumber": self.build, "releaseDate": "2026-10-06T11:08:26Z"}

    def _download(self, build=None):
        write_sde(sde_tasks.SDE_FOLDER, self.releases[build or self.build], build or self.build)

    def _get(self, url, **kwargs):
        self.requested.append(url)
        url = self.rest_blobs.get(url, url)
        if url.startswith(BASE):
            body = self.rest_files.get(url, 404)
        else:
            build = int(url.rsplit("/", 1)[1].removesuffix(".jsonl"))
            body = self.feed.get(build, 404)
        response = mock.MagicMock()
        if isinstance(body, int):
            response.raise_for_status.side_effect = sde_tasks.httpx2.HTTPStatusError(
                str(body), request=mock.MagicMock(), response=mock.MagicMock(status_code=body)
            )
        else:
            response.text = body
            response.json.side_effect = lambda: json.loads(body)
            response.iter_bytes.side_effect = lambda: iter([body.encode()])
        return response

    def _stream(self, method, url, **kwargs):
        cm = mock.MagicMock()
        cm.__enter__.return_value = self._get(url)
        return cm

    def rest_tables_downloaded(self):
        """Table names whose .jsonl was downloaded from a REST release."""
        return sorted({
            _u.rsplit("/", 1)[1].removesuffix(".jsonl")
            for _u in map(lambda _u: self.rest_blobs.get(_u, _u), self.requested)
            if _u.startswith(BASE) and _u.endswith(".jsonl") and not _u.endswith("/_changes.jsonl")
        })

    def _publish_rest(self, sde, republish=0):
        """sde as a REST release of self.build, retiring all but the newest REST_RETAINED."""
        name = rest_release_name(self.build, republish)
        root = f"{BASE}/{name}/"
        index = {"release": name, "buildNumber": self.build, "releaseDate": "2026-10-06T11:08:26Z", "tables": {}}
        for table, rows in sde.items():
            body = "".join(json.dumps(to_rest(_r, schema(table))) + "\n" for _r in rows.values())
            index["tables"][table] = {
                # a re-publish changes every version, like CCP's
                "version": hashlib.sha256(f"{republish}:{body}".encode()).hexdigest(),
                "jsonl": {"url": f"{root}{table}.jsonl", "recordSchemaUrl": f"{root}{table}.schema.json"},
            }
            self.rest_files[f"{root}{table}.jsonl"] = body
            self.rest_files[f"{root}{table}.schema.json"] = json.dumps(schema(table))
            self.rest_blobs[sde_file_urls(index["tables"][table])[0]] = f"{root}{table}.jsonl"
            self.rest_blobs[sde_file_urls(index["tables"][table], schema=True)[0]] = f"{root}{table}.schema.json"
        previous = self.rest_releases[-1] if self.rest_releases else None
        changes = diff_sde(self._rest_sde[previous], sde) if previous else {}
        index["tables"]["_changes"] = {"version": name, "jsonl": {"url": f"{root}_changes.jsonl"}}
        self.rest_blobs[sde_file_urls(index["tables"]["_changes"])[0]] = f"{root}_changes.jsonl"
        self.rest_files[f"{root}_changes.jsonl"] = json.dumps({
            "comparedWith": f"tranquility@{previous}", "tables": diff_to_rest_changes(changes),
        }) + "\n"
        self.rest_files[root] = self.rest_files[f"{BASE}/latest/"] = json.dumps(index)
        self._rest_sde[name] = sde
        self.rest_releases.append(name)
        for old in self.rest_releases[:-REST_RETAINED]:
            for url in [_u for _u in self.rest_files if _u.startswith(f"{BASE}/{old}/")]:
                del self.rest_files[url]
        return name

    # test API
    def release(self, sde):
        """Publish `sde` as the next build, with a changes file from the previous one."""
        sde = copy.deepcopy(sde)
        previous = self.build
        self.build = FIRST_BUILD if previous is None else previous + 1
        self.releases[self.build] = sde
        self._publish_rest(sde)
        if previous is not None:
            lines = [{"_key": "_meta", "buildNumber": self.build, "lastBuildNumber": previous}]
            lines += [{"_key": _k} | _c for _k, _c in diff_sde(self.releases[previous], sde).items()]
            self.feed[self.build] = "\n".join(json.dumps(_l) for _l in lines)
        return self.build

    def republish(self):
        """CCP re-publishing the current build: the same data, but every table version changes."""
        self._republished += 1
        return self._publish_rest(copy.deepcopy(self.releases[self.build]), republish=self._republished)

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
