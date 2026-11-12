"""
CCP's SDE REST API (https://sde.evetech.net/), the source the loader reads
by default. Its JSONL is the zip's data with `_key` / `_value` renamed to
real names, named by `x-sde-key` in each table's schema.
"""
# Standard Library
import json
import logging
import os

logger = logging.getLogger(__name__)


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
