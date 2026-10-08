"""
Builds the mini SDE fixture (mini_sde/) used by test_sde_updates.py from a
real extracted SDE folder.

    python -I eve_sde/tests/test_jsons/make_mini_sde.py <extracted sde folder>

Takes a small, self-consistent slice: a few solar systems and everything in
them, a handful of types plus every type, group, category, market group,
attribute, effect and certificate they reference. Lists are trimmed to the
slice, so every FK the loader writes points at a row that exists, except
the deliberate dangling blueprint product the tests rely on.
"""
# Standard Library
import json
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mini_sde")

# three linked high sec systems, and a null sec one with planet and star resources
SYSTEMS = [30000001, 30000002, 30000003, 30000208]
PLANETS_PER_SYSTEM = 2
MOONS_PER_PLANET = 2
# Rifter, its blueprint, a skill, Moon
SEED_TYPES = [587, 691, 3300, 14]
DOGMA_ATTRIBUTES_PER_TYPE = 6
DOGMA_EFFECTS_PER_TYPE = 3
FIRST_ROWS = {
    "accountingEntryTypes": 3,
    "archetypes": 2,
    "corporationRoles": 3,
    "notificationTypes": 3,
    "freelanceJobSchemas": 1,
    "sovereigntyUpgrades": 2,
    "metenoxMoonDrill": 1,
    "skillPlans": 1,
}


def read(src, name):
    with open(os.path.join(src, f"{name}.jsonl")) as f:
        return {(_r := json.loads(_l))["_key"]: _r for _l in f}


def first(rows, count):
    return dict(list(rows.items())[:count])


def main(src):
    sde = {}
    types = set(SEED_TYPES)

    # map
    systems = read(src, "mapSolarSystems")
    sde["mapSolarSystems"] = {_k: systems[_k] for _k in SYSTEMS}
    constellations = {_s["constellationID"] for _s in sde["mapSolarSystems"].values()}
    sde["mapConstellations"] = {_k: _v for _k, _v in read(src, "mapConstellations").items() if _k in constellations}
    regions = {_c["regionID"] for _c in sde["mapConstellations"].values()}
    sde["mapRegions"] = {_k: _v for _k, _v in read(src, "mapRegions").items() if _k in regions}
    sde["mapStars"] = {_k: _v for _k, _v in read(src, "mapStars").items() if _v["solarSystemID"] in SYSTEMS}
    sde["mapStargates"] = {
        _k: _v for _k, _v in read(src, "mapStargates").items()
        if _v["solarSystemID"] in SYSTEMS and _v["destination"]["solarSystemID"] in SYSTEMS
    }
    sde["mapPlanets"] = {}
    for _k, _v in read(src, "mapPlanets").items():
        if _v["solarSystemID"] in SYSTEMS and sum(
            _p["solarSystemID"] == _v["solarSystemID"] for _p in sde["mapPlanets"].values()
        ) < PLANETS_PER_SYSTEM:
            sde["mapPlanets"][_k] = _v
    sde["mapMoons"] = {}
    for _k, _v in read(src, "mapMoons").items():
        if _v["orbitID"] in sde["mapPlanets"] and sum(
            _m["orbitID"] == _v["orbitID"] for _m in sde["mapMoons"].values()
        ) < MOONS_PER_PLANET:
            sde["mapMoons"][_k] = _v
    sde["npcStations"] = first(
        {_k: _v for _k, _v in read(src, "npcStations").items() if _v["solarSystemID"] in SYSTEMS}, 2
    )
    landmarks = read(src, "landmarks")
    sde["landmarks"] = {_k: _v for _k, _v in landmarks.items() if _v.get("locationID") in SYSTEMS}
    sde["landmarks"] |= first({_k: _v for _k, _v in landmarks.items() if "locationID" not in _v}, 2)
    resources = read(src, "planetResources")
    celestials = set(sde["mapPlanets"]) | set(sde["mapStars"])
    sde["planetResources"] = {_k: _v for _k, _v in resources.items() if _k in celestials}
    for _r in sde["planetResources"].values():
        if "reagent" in _r:
            types.add(_r["reagent"]["type_id"])
    for name in ("mapStars", "mapStargates", "mapPlanets", "mapMoons", "npcStations"):
        types |= {_v["typeID"] for _v in sde[name].values()}

    # misc
    for name, count in FIRST_ROWS.items():
        sde[name] = first(read(src, name), count)
    for _f in sde["freelanceJobSchemas"].values():
        _f["_value"] = _f["_value"][:2]
    for _u in sde["sovereigntyUpgrades"].values():
        types.add(_u["_key"])
        if "fuel" in _u:
            types.add(_u["fuel"]["type_id"])
    types |= set(sde["metenoxMoonDrill"])
    for _p in sde["skillPlans"].values():
        _p["milestones"] = _p.get("milestones", [])[:3]
        _p["skillRequirements"] = _p.get("skillRequirements", [])[:4]
        types |= {_m["typeID"] for _m in _p["milestones"] + _p["skillRequirements"]}
    sde["corporationRoleGroups"] = read(src, "corporationRoleGroups")
    sde["dogmaAttributeCategories"] = {}

    # industry
    blueprints = read(src, "blueprints")
    sde["blueprints"] = {_k: _v for _k, _v in blueprints.items() if _k in types}
    for _b in sde["blueprints"].values():
        for activity in _b["activities"].values():
            for part in ("materials", "products"):
                types |= {_m["typeID"] for _m in activity.get(part, [])}
    type_materials = read(src, "typeMaterials")
    sde["typeMaterials"] = {_k: _v for _k, _v in type_materials.items() if _k in SEED_TYPES}
    for _m in sde["typeMaterials"].values():
        types |= {_x["materialTypeID"] for _x in _m["materials"]}

    # certificates and masteries of the seed ship
    masteries = read(src, "masteries")
    sde["masteries"] = {_k: _v for _k, _v in masteries.items() if _k == 587}
    certificate_ids = {_c for _m in sde["masteries"].values() for _l in _m["_value"] for _c in _l["_value"]}
    certificate_ids = set(sorted(certificate_ids)[:2])
    for _m in sde["masteries"].values():
        for _l in _m["_value"]:
            _l["_value"] = [_c for _c in _l["_value"] if _c in certificate_ids]
    sde["certificates"] = {_k: _v for _k, _v in read(src, "certificates").items() if _k in certificate_ids}
    for _c in sde["certificates"].values():
        _c["skillTypes"] = _c["skillTypes"][:2]
        types |= {_s["_key"] for _s in _c["skillTypes"]}
        _c["recommendedFor"] = [_t for _t in _c["recommendedFor"] if _t in SEED_TYPES]

    # dogma of the seed ship
    type_dogma = read(src, "typeDogma")
    sde["typeDogma"] = {_k: _v for _k, _v in type_dogma.items() if _k == 587}
    for _d in sde["typeDogma"].values():
        _d["dogmaAttributes"] = _d["dogmaAttributes"][:DOGMA_ATTRIBUTES_PER_TYPE]
        _d["dogmaEffects"] = _d["dogmaEffects"][:DOGMA_EFFECTS_PER_TYPE]
    attribute_ids = {_a["attributeID"] for _d in sde["typeDogma"].values() for _a in _d["dogmaAttributes"]}
    effect_ids = {_e["effectID"] for _d in sde["typeDogma"].values() for _e in _d["dogmaEffects"]}
    sde["dogmaAttributes"] = {_k: _v for _k, _v in read(src, "dogmaAttributes").items() if _k in attribute_ids}
    sde["dogmaEffects"] = {_k: _v for _k, _v in read(src, "dogmaEffects").items() if _k in effect_ids}
    units = {_a["unitID"] for _a in sde["dogmaAttributes"].values() if "unitID" in _a}
    sde["dogmaUnits"] = {_k: _v for _k, _v in read(src, "dogmaUnits").items() if _k in units}
    attr_categories = {
        _a["attributeCategoryID"]
        for _a in sde["dogmaAttributes"].values() if "attributeCategoryID" in _a}
    sde["dogmaAttributeCategories"] = {
        _k: _v for _k, _v in read(src, "dogmaAttributeCategories").items() if _k in attr_categories
    }

    all_types = read(src, "types")
    sde["types"] = {_k: all_types[_k] for _k in sorted(types) if _k in all_types}
    groups = {_t["groupID"] for _t in sde["types"].values()}
    groups |= {_c["groupID"] for _c in sde["certificates"].values()}
    sde["groups"] = {_k: _v for _k, _v in read(src, "groups").items() if _k in groups}
    categories = {_g["categoryID"] for _g in sde["groups"].values()}
    sde["categories"] = {_k: _v for _k, _v in read(src, "categories").items() if _k in categories}
    all_market_groups = read(src, "marketGroups")
    market_groups = set()
    for _t in sde["types"].values():
        _mg = _t.get("marketGroupID")
        while _mg and _mg not in market_groups:
            market_groups.add(_mg)
            _mg = all_market_groups[_mg].get("parentGroupID")
    sde["marketGroups"] = {_k: _v for _k, _v in all_market_groups.items() if _k in market_groups}

    sde["typeLists"] = {}
    for _k, _v in read(src, "typeLists").items():
        for field, keep in (
            ("includedTypeIDs", sde["types"]), ("excludedTypeIDs", sde["types"]),
            ("includedGroupIDs", sde["groups"]), ("excludedGroupIDs", sde["groups"]),
            ("includedCategoryIDs", sde["categories"]), ("excludedCategoryIDs", sde["categories"]),
        ):
            if field in _v:
                _v[field] = [_i for _i in _v[field] if _i in keep]
        if any(_v.get(_f) for _f in ("includedTypeIDs", "excludedTypeIDs", "includedGroupIDs", "excludedGroupIDs")):
            sde["typeLists"][_k] = _v
        if len(sde["typeLists"]) >= 4:
            break

    os.makedirs(OUT, exist_ok=True)
    for name, rows in sorted(sde.items()):
        with open(os.path.join(OUT, f"{name}.jsonl"), "w") as f:
            for row in rows.values():
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)}")
    with open(os.path.join(src, "_sde.jsonl")) as f:
        sde_meta = json.loads(f.readline())
    with open(os.path.join(OUT, "_sde.jsonl"), "w") as f:
        f.write(json.dumps(sde_meta) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
