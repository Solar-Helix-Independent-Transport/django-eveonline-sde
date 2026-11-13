"""
CCP's SDE REST API (https://sde.evetech.net/), the source the loader reads
by default. Its JSONL is the zip's data with `_key` / `_value` renamed to
real names, named by `x-sde-key` in each table's schema.
"""
# Standard Library
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

# Third Party
import httpx2

logger = logging.getLogger(__name__)

SDE_REST_URL = "https://sde.evetech.net/tranquility/{release}/"
SDE_INFO_FILE = "_sde.jsonl"
# Files downloaded at once. Each one is a redirect to its blob on the CDN,
# which is most of the time a small table takes, so a shared client and
# several at a time make a full fetch over 10x faster (166s -> 14s), close
# to the time the largest table (mapMoons) takes on its own.
SDE_FETCH_THREADS = 16
# CCP serves the API gzipped. Ask for only that: offered brotli, the CDN
# sends it, and httpx2's brotli decoder breaks on Brotli < 1.2.
SDE_HEADERS = {"Accept-Encoding": "gzip"}


def download_file(url, local_filename, client=None):
    """
    Downloads a file from a given URL using httpx2 and saves it locally.

    Args:
        url (str): The URL of the file to download.
        local_filename (str): The path and name to save the downloaded file.
        client (httpx2.Client): Reuse this client's connections, a new
            connection is opened otherwise.

    Raises:
        Exception: Re-raises any download failure after logging it, and removes
            any partially written file so callers never see a truncated/corrupt
            local file mistaken for a good one.
    """
    try:
        stream = client.stream if client else httpx2.stream
        with stream("GET", url, headers=SDE_HEADERS, follow_redirects=True) as response:
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            with open(local_filename, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        logger.info(f"File downloaded successfully to: {local_filename}")
    except Exception:
        logger.exception(f"Failed to download {url}")
        if os.path.exists(local_filename):
            os.remove(local_filename)
        raise


def get_sde_release(release: str = "latest") -> dict:
    """
    The index of a release (`latest` follows the redirect to the current one).

    {"release": "20261111T160425Z", "buildNumber": 3687575, "releaseDate": "...", "tables": {
        "types": {"version": "...", "jsonl": {"url": ..., "recordSchemaUrl": ...}}, ...}}
    """
    url = SDE_REST_URL.format(release=release)
    try:
        response = httpx2.get(url, headers=SDE_HEADERS, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception(f"Failed to read the SDE release index from {url}")
        raise


def fetch_sde_release(index: dict, tables, folder: str):
    """
    Download `tables` and their schemas from the release `index` describes
    into `folder`, plus an _sde.jsonl recording the release and the version
    of each table fetched. URLs come from the index, so they're pinned to
    that release even if a newer one lands meanwhile.
    """
    os.makedirs(folder, exist_ok=True)
    versions = {}
    files = []
    for table in tables:
        info = index["tables"][table]
        files.append((info["jsonl"]["url"], os.path.join(folder, f"{table}.jsonl")))
        files.append((info["jsonl"]["recordSchemaUrl"], os.path.join(folder, f"{table}.schema.json")))
        versions[table] = info["version"]
    with httpx2.Client() as client, ThreadPoolExecutor(SDE_FETCH_THREADS) as pool:
        # list() raises the first failed download, after the rest finish
        list(pool.map(lambda _f: download_file(*_f, client=client), files))
    with open(os.path.join(folder, SDE_INFO_FILE), "w") as f:
        f.write(json.dumps({
            "release": index["release"],
            "buildNumber": index["buildNumber"],
            "releaseDate": index["releaseDate"],
            "versions": versions,
        }))


def _resolve(node: dict, schema: dict) -> dict:
    """Follow a local `#/$defs/Name` reference."""
    ref = node.get("$ref")
    if ref and ref.startswith("#/$defs/"):
        return schema.get("$defs", {}).get(ref.removeprefix("#/$defs/"), {})
    return node


def _alias(value, node: dict, schema: dict):
    node = _resolve(node, schema)
    if isinstance(value, list):
        items = node.get("items")
        if items:
            for _v in value:
                _alias(_v, items, schema)
        return
    if not isinstance(value, dict):
        return

    props = node.get("properties", {})
    key = node.get("x-sde-key")
    if key and key not in value and "_key" not in value:
        logger.warning(f"SDE row has no {key} key the schema names, left without _key: {list(value)[:5]}")
    elif key and key in value:
        value.setdefault("_key", value[key])
        # a zip {_key, _value} pair: the one other property was its _value
        others = [_p for _p in props if _p != key]
        if len(others) == 1 and others[0] in value:
            value.setdefault("_value", value[others[0]])

    for name, sub in props.items():
        if name in value:
            _alias(value[name], sub, schema)


def sde_tables_for(models) -> list:
    """
    Every SDE table `models` read: each one's own and its depends_on
    tables, once each, in order.
    """
    tables = {}
    for mdl in models:
        tables[mdl.sde_file_key()] = None
        for dep in getattr(mdl.Import, "depends_on", ()):
            tables[dep if isinstance(dep, str) else dep[0]] = None
    return list(tables)


def read_sde_schema(folder: str, filename: str):
    """
    The schema saved next to `filename` (`types.jsonl` -> `types.schema.json`)
    when the folder came from the REST API, None for an extracted zip.
    """
    path = os.path.join(folder, f"{filename.removesuffix('.jsonl')}.schema.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def alias_sde_record(record: dict, schema: dict) -> dict:
    """
    `record` with `_key` / `_value` added next to the real names the schema
    says replaced them, at every depth, so Import configs written against
    the zip read it unchanged. Nothing is renamed or removed, and a zip row
    that already has them is left as it is.
    """
    _alias(record, schema, schema)
    return record
