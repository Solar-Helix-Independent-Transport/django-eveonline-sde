"""
A fake sde.evetech.net for tests: release indexes, table files, schemas and
_changes, served through httpx2.get / httpx2.stream by URL.

Schemas are the real ones in test_jsons/rest_schemas.
"""
# Standard Library
import json
import os
from unittest import mock

# Third Party
import httpx2

# Django EVE SDE
from eve_sde.sde_rest import sde_file_urls

SCHEMAS = os.path.join(os.path.dirname(__file__), "test_jsons", "rest_schemas")
RELEASE = "20261111T160425Z"
PREVIOUS = "20261111T110708Z"
BASE = "https://sde.evetech.net/tranquility"
ALL_TABLES = sorted(_f.removesuffix(".schema.json") for _f in os.listdir(SCHEMAS))


def schema(table):
    with open(os.path.join(SCHEMAS, f"{table}.schema.json")) as f:
        return json.load(f)


def install_fake_http(testcase, get, stream):
    """Route httpx2.get / httpx2.stream, and the same on any httpx2.Client, to `get` / `stream`."""
    client = mock.MagicMock()
    client.get.side_effect = get
    client.stream.side_effect = stream
    client.__enter__.return_value = client
    for name, value in (("get", get), ("stream", stream), ("Client", lambda *a, **k: client)):
        patcher = mock.patch.object(httpx2, name, side_effect=value)
        patcher.start()
        testcase.addCleanup(patcher.stop)


class FakeCCP:
    """
    sde.evetech.net with one release, RELEASE, serving `tables`
    ({table: [rows]}). Table versions are "v-<table>" unless given in
    `versions`. `changes` (a list of CCP's per-table change records) is
    served as _changes compared with `compared_with`. Each file is also
    served at its blob URL, like CCP's (`blobs` maps those to the release URL
    they stand for - clear it for a CDN without them). Any other URL is a
    404. Every URL asked for is recorded in `requested`.
    """

    def __init__(self, tables, versions=None, changes=None, compared_with=PREVIOUS):
        self.requested = []
        self.files = {}
        self.blobs = {}
        versions = versions or {}
        index = {"release": RELEASE, "buildNumber": 3687575, "releaseDate": "2026-11-11T16:04:25Z", "tables": {}}

        def publish(table, body, with_schema=True):
            url = f"{BASE}/{RELEASE}/{table}"
            index["tables"][table] = {
                "version": versions.get(table, f"v-{table}"),
                "jsonl": {"url": f"{url}.jsonl", "recordSchemaUrl": f"{url}.schema.json"},
            }
            self.files[f"{url}.jsonl"] = body
            self.blobs[sde_file_urls(index["tables"][table])[0]] = f"{url}.jsonl"
            if with_schema:
                self.files[f"{url}.schema.json"] = json.dumps(schema(table))
                self.blobs[sde_file_urls(index["tables"][table], schema=True)[0]] = f"{url}.schema.json"

        for table, rows in tables.items():
            publish(table, "".join(json.dumps(_r) + "\n" for _r in rows))
        publish("_changes", json.dumps({
            "comparedWith": f"tranquility@{compared_with}", "tables": changes or [],
        }) + "\n", with_schema=False)
        self.index = index
        self.files[f"{BASE}/latest/"] = self.files[f"{BASE}/{RELEASE}/"] = json.dumps(index)

    def _response(self, url):
        self.requested.append(url)
        response = mock.MagicMock()
        body = self.files.get(self.blobs.get(url, url))
        response.status_code = 200 if body is not None else 404
        if body is None:
            response.raise_for_status.side_effect = httpx2.HTTPStatusError(
                "404", request=mock.MagicMock(), response=mock.MagicMock(status_code=404)
            )
            body = ""
        response.text = body
        response.json.side_effect = lambda: json.loads(body)
        response.iter_bytes.side_effect = lambda: iter([body.encode()])
        return response

    def get(self, url, **kwargs):
        return self._response(url)

    def stream(self, method, url, **kwargs):
        cm = mock.MagicMock()
        cm.__enter__.return_value = self._response(url)
        return cm

    def install(self, testcase):
        install_fake_http(testcase, self.get, self.stream)

    def table_urls(self):
        """The table and schema URLs asked for, as table names."""
        prefix = f"{BASE}/{RELEASE}/"
        return sorted({
            _u.removeprefix(prefix).removesuffix(".jsonl").removesuffix(".schema.json")
            for _u in map(lambda _u: self.blobs.get(_u, _u), self.requested)
            if _u.startswith(prefix) and _u != prefix
        })


def _to_rest(value, node, root):
    if node.get("$ref", "").startswith("#/$defs/"):
        node = root.get("$defs", {}).get(node["$ref"].removeprefix("#/$defs/"), {})
    if isinstance(value, list):
        return [_to_rest(_v, node.get("items", {}), root) for _v in value]
    if not isinstance(value, dict):
        return value
    props = node.get("properties", {})
    key = node.get("x-sde-key")
    out = {}
    if key and "_key" in value:
        out[key] = value["_key"]
    others = [_p for _p in props if _p != key]
    for name, val in value.items():
        if name == "_key":
            continue
        if name == "_value" and key and len(others) == 1:
            name = others[0]
        out[name] = _to_rest(val, props.get(name, {}), root)
    return out


def _has_zip_keys(value):
    if isinstance(value, dict):
        return "_key" in value or "_value" in value or any(_has_zip_keys(_v) for _v in value.values())
    if isinstance(value, list):
        return any(_has_zip_keys(_v) for _v in value)
    return False


def to_rest(row: dict, table_schema: dict) -> dict:
    """
    A zip-shaped SDE row the way the REST API serves it: `_key` / `_value`
    renamed to what the schema names them, key first. Raises if any are
    left, CCP's REST rows never have them.
    """
    out = _to_rest(row, table_schema, table_schema)
    if _has_zip_keys(out):
        raise ValueError(f"_key / _value left after converting to REST: {out}")
    return out
