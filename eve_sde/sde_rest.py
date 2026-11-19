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

# Django
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ETag + body of the last version check response, per URL
ETAG_CACHE_PREFIX = "eve_sde:etag:"
ETAG_CACHE_TIMEOUT = 60 * 60 * 24 * 7

SDE_REST_URL = "https://sde.evetech.net/tranquility/{release}/"
# Every table file URL in a release index 302s to its immutable blob, named
# by the table's version hash, e.g. tranquility/<release>/types.jsonl ->
# /blobs/<types version>.jsonl (and .schema.json for its schema). Going
# straight to the blob skips a round trip per file. Undocumented, so the
# index URL is the fallback if a blob URL ever stops working.
SDE_BLOB_URL = "https://sde.evetech.net/blobs/{version}{ext}"
SDE_INFO_FILE = "_sde.jsonl"
# Files downloaded at once. Most of the time a small table takes is the
# round trip, so a shared client and several at a time make a full fetch
# over 10x faster (166s -> 14s), close to the time the largest table
# (mapMoons) takes on its own.
SDE_FETCH_THREADS = 16


def sde_file_urls(info: dict, schema: bool = False) -> tuple:
    """
    (blob URL, index URL) of a table's JSONL, or its schema, from the
    table's entry in a release index.
    """
    if schema:
        return SDE_BLOB_URL.format(version=info["version"], ext=".schema.json"), info["jsonl"]["recordSchemaUrl"]
    return SDE_BLOB_URL.format(version=info["version"], ext=".jsonl"), info["jsonl"]["url"]


def _stream_to_file(url, local_filename, client=None):
    stream = client.stream if client else httpx2.stream
    with stream("GET", url, follow_redirects=True) as response:
        response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
        with open(local_filename, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)


def download_file(url, local_filename, client=None, fallback_url=None):
    """
    Downloads a file from a given URL using httpx2 and saves it locally.

    Args:
        url (str): The URL of the file to download.
        local_filename (str): The path and name to save the downloaded file.
        client (httpx2.Client): Reuse this client's connections, a new
            connection is opened otherwise.
        fallback_url (str): Tried, with a warning, if `url` answers with an
            HTTP error status.

    Raises:
        Exception: Re-raises any download failure after logging it, and removes
            any partially written file so callers never see a truncated/corrupt
            local file mistaken for a good one.
    """
    try:
        try:
            _stream_to_file(url, local_filename, client)
        except httpx2.HTTPStatusError as e:
            if not fallback_url:
                raise
            logger.warning(f"Failed to download {url} ({e.response.status_code}), trying {fallback_url}")
            url = fallback_url
            _stream_to_file(url, local_filename, client)
        logger.info(f"File downloaded successfully to: {local_filename}")
    except Exception:
        logger.exception(f"Failed to download {url}")
        if os.path.exists(local_filename):
            os.remove(local_filename)
        raise


def _cache_get(key):
    try:
        return cache.get(key)
    except Exception:
        logger.warning(f"Failed to read {key} from the cache", exc_info=True)
        return None


def _cache_set(key, value):
    try:
        cache.set(key, value, ETAG_CACHE_TIMEOUT)
    except Exception:
        logger.warning(f"Failed to write {key} to the cache", exc_info=True)


def get_json_conditional(url: str):
    """
    GET `url` as JSON, sending the ETag of the last response so an unchanged
    file comes back as a bodyless 304 and is served from the cache. Used for
    the `latest` release index, which the update check polls hourly, so an
    unchanged SDE doesn't re-download the ~90KB index each time. `latest`
    redirects to the current release, so its ETag changes exactly when the
    release does. The cache is only an optimisation: missing or broken, it's
    a normal GET.
    """
    key = f"{ETAG_CACHE_PREFIX}{url}"
    cached = _cache_get(key)
    headers = {"If-None-Match": cached["etag"]} if cached else {}
    response = httpx2.get(url, headers=headers, follow_redirects=True)
    if cached and response.status_code == 304:
        return cached["data"]
    response.raise_for_status()
    data = response.json()
    etag = response.headers.get("etag")
    if isinstance(etag, str) and etag:
        _cache_set(key, {"etag": etag, "data": data})
    return data


def get_sde_release(release: str = "latest") -> dict:
    """
    The index of a release (`latest` follows the redirect to the current one).

    {"release": "20261111T160425Z", "buildNumber": 3687575, "releaseDate": "...", "tables": {
        "types": {"version": "...", "jsonl": {"url": ..., "recordSchemaUrl": ...}}, ...}}
    """
    url = SDE_REST_URL.format(release=release)
    try:
        if release == "latest":
            # polled hourly by the update check, and unchanged most of the time
            return get_json_conditional(url)
        # a pinned release's index never changes
        response = httpx2.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception(f"Failed to read the SDE release index from {url}")
        raise


def fetch_sde_release(index: dict, tables, folder: str):
    """
    Download `tables` and their schemas from the release `index` describes
    into `folder`, plus an _sde.jsonl recording the release and the version
    of every table in it - a model's depends_on tables are only compared by
    version, so they're never downloaded. Files are fetched by the versions
    in the index, so they're pinned to that release even if a newer one
    lands meanwhile.
    """
    os.makedirs(folder, exist_ok=True)
    files = []
    for table in tables:
        info = index["tables"].get(table)
        if info is None:
            logger.error(f"SDE table {table} is not in release {index['release']}, skipping it")
            continue
        files.append((*sde_file_urls(info), os.path.join(folder, f"{table}.jsonl")))
        files.append((*sde_file_urls(info, schema=True), os.path.join(folder, f"{table}.schema.json")))
    versions = {_t: _i["version"] for _t, _i in index["tables"].items() if not _t.startswith("_")}
    with httpx2.Client() as client, ThreadPoolExecutor(SDE_FETCH_THREADS) as pool:
        # list() raises the first failed download, after the rest finish
        list(pool.map(
            lambda _f: download_file(_f[0], _f[2], client=client, fallback_url=_f[1]), files,
        ))
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


def section_versions(mdl, versions: dict) -> dict:
    """{table: version} from `versions` for each table `mdl` reads, the ones present."""
    return {_t: versions[_t] for _t in sde_tables_for([mdl]) if _t in versions}


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
    `record` with `_key` added next to the real name the schema's x-sde-key
    says replaced it, at every depth, so Import configs written against the
    zip read it unchanged. Nothing is renamed or removed, and a zip row that
    already has one is left as it is.

    The zip's `_value` isn't aliased: the schema doesn't say which property
    replaced it, so the few loaders that read one name both (e.g. Mastery's
    "levels" / "_value").
    """
    _alias(record, schema, schema)
    return record
