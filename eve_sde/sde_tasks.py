# Standard Library
import json
import logging
import os
import shutil
import zipfile
from datetime import datetime, timedelta, timezone

# Third Party
import httpx2

# Django EVE SDE
from eve_sde.app_settings import (
    ESDE_FULL_UPDATE_DAYS,
    ESDE_SELECTIVE_UPDATES,
    ESDE_SOURCE,
)
from eve_sde.models import EveSDE, EveSDESection
from eve_sde.models.certificates import (
    Certificate,
    CertificateRecommendedType,
    CertificateSkill,
    Mastery,
)
from eve_sde.models.freelance import FreelanceJobSchema, FreelanceJobSchemaParameter
from eve_sde.models.industry import (
    BlueprintActivity,
    BlueprintActivityMaterial,
    BlueprintActivityProduct,
)
from eve_sde.models.lore import Archetype
from eve_sde.models.map import (
    Constellation,
    Landmark,
    Moon,
    NPCStation,
    Planet,
    PlanetResource,
    Region,
    SolarSystem,
    Star,
    Stargate,
    StarResource,
)
from eve_sde.models.misc import (
    AccountingEntryType,
    CorporationRole,
    CorporationRoleGroup,
    CorporationRoleGroupMembership,
    MetenoxMoonDrill,
    NotificationType,
    SkillPlan,
    SkillPlanMilestone,
    SkillPlanSkillRequirement,
)
from eve_sde.models.sovereignty import SovereigntyUpgrade
from eve_sde.models.types import (
    DogmaAttribute,
    DogmaAttributeCategory,
    DogmaEffect,
    DogmaUnit,
    ItemCategory,
    ItemGroup,
    ItemMarketGroup,
    ItemType,
    ItemTypeMaterials,
    TypeDogma,
    TypeEffect,
    TypeList,
    TypeListCategory,
    TypeListGroup,
    TypeListType,
)
from eve_sde.sde_rest import (
    SDE_REST_URL,
    download_file,
    fetch_sde_release,
    get_sde_release,
    sde_file_urls,
    sde_tables_for,
    section_versions,
)

logger = logging.getLogger(__name__)

# What models and the order to load them
SDE_PARTS_TO_UPDATE = [
    # Types
    ItemCategory,
    ItemGroup,
    ItemMarketGroup,
    ItemType,  # Requires: ItemGroup and ItemMarketGroup
    ItemTypeMaterials,
    TypeList,
    TypeListType,  # Requires: TypeList, ItemType
    TypeListGroup,  # Requires: TypeList, ItemGroup
    TypeListCategory,  # Requires: TypeList, ItemCategory
    BlueprintActivity,
    BlueprintActivityProduct,
    BlueprintActivityMaterial,
    DogmaUnit,
    DogmaAttributeCategory,
    DogmaAttribute,
    DogmaEffect,
    TypeDogma,
    TypeEffect,
    # Map
    Region,
    Constellation,
    SolarSystem,
    Star,  # Requires: SolarSystem, ItemType
    #  System stuffs
    NPCStation,  # Requires: SolarSystem, ItemType
    SovereigntyUpgrade,  # Requires: ItemType
    Stargate,
    Planet,
    PlanetResource,  # Requires: Planet, ItemType
    StarResource,  # Requires: Star, ItemType
    Moon,
    Landmark,  # Requires: SolarSystem
    # Lore / reference
    Archetype,
    # Freelance Jobs
    FreelanceJobSchema,
    FreelanceJobSchemaParameter,  # Requires: FreelanceJobSchema
    # Misc
    AccountingEntryType,
    NotificationType,
    CorporationRoleGroup,
    CorporationRole,
    CorporationRoleGroupMembership,  # Requires: CorporationRole, CorporationRoleGroup
    MetenoxMoonDrill,  # Requires: ItemType
    SkillPlan,
    SkillPlanMilestone,  # Requires: SkillPlan, ItemType
    SkillPlanSkillRequirement,  # Requires: SkillPlan, ItemType
    # Certificates
    Certificate,  # Requires: ItemGroup
    CertificateSkill,  # Requires: Certificate, ItemType
    CertificateRecommendedType,  # Requires: Certificate, ItemType
    Mastery,  # Requires: Certificate, ItemType
]

SDE_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"
SDE_BUILD_URL = "https://developers.eveonline.com/static-data/tranquility/eve-online-static-data-{build}-jsonl.zip"
SDE_LATEST_URL = "https://developers.eveonline.com/static-data/tranquility/latest.jsonl"
SDE_CHANGES_URL = "https://developers.eveonline.com/static-data/tranquility/changes/{build}.jsonl"
# Builds walked back through the changes feed before giving up and loading everything
SDE_MAX_CHANGE_BUILDS = 50
SDE_FILE_NAME = "eve-online-static-data-latest-jsonl.zip"
SDE_FOLDER = "eve-sde"


def delete_sde_zip():
    if os.path.exists(SDE_FILE_NAME):
        os.remove(SDE_FILE_NAME)


def delete_sde_folder():
    if os.path.exists(SDE_FOLDER):
        shutil.rmtree(SDE_FOLDER)


def get_latest_sde():
    """
    {"_key": "sde", "buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}
    """
    try:
        response = httpx2.get(SDE_LATEST_URL)
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception(f"Failed to check SDE version from {SDE_LATEST_URL}")
        raise


def check_sde_version():
    """True when the loaded SDE is the latest: the same REST release, or zip build."""
    current = EveSDE.get_solo()
    if ESDE_SOURCE == "rest":
        return current.release == get_sde_release().get("release")
    return current.build_number == get_latest_sde().get("buildNumber")


def fetch_sde_changes(target_build: int, since_build: int):
    """
    Walk CCP's changes feed back from target_build until it reaches
    since_build. Returns [(build, {file key: change record})] newest first,
    or None when the chain can't be followed (missing/expired build, bad
    data, too far back), meaning everything has to be loaded.

    {"_key":"_meta","buildNumber":3579973,"lastBuildNumber":3569502,...}
    {"_key":"blueprints","added":[95742,...],"changed":[88267]}
    """
    builds = []
    build = target_build
    while build > since_build:
        if len(builds) >= SDE_MAX_CHANGE_BUILDS:
            logger.warning(f"SDE changes - more than {SDE_MAX_CHANGE_BUILDS} builds since {since_build}")
            return None
        url = SDE_CHANGES_URL.format(build=build)
        try:
            response = httpx2.get(url, follow_redirects=True)
            response.raise_for_status()
            records = [json.loads(_l) for _l in response.text.splitlines() if _l.strip()]
        except Exception:
            logger.warning(f"SDE changes - failed to read {url}", exc_info=True)
            return None
        files = {_r["_key"]: _r for _r in records if isinstance(_r, dict) and "_key" in _r}
        meta = files.pop("_meta", {})
        last_build = meta.get("lastBuildNumber")
        if meta.get("buildNumber") != build or not isinstance(last_build, int) or last_build >= build:
            logger.warning(f"SDE changes - no usable _meta in {url}: {meta}")
            return None
        builds.append((build, files))
        build = last_build
    return builds


def merge_sde_changes(builds, since_build: int):
    """
    {file key: {"ops": {operation, ...}, "ids": {_key, ...}}} over every build
    in `builds` newer than since_build.
    """
    out = {}
    for build, files in builds:
        if build <= since_build:
            continue
        for key, record in files.items():
            ops = set()
            ids = set()
            for op, val in record.items():
                if op == "_key" or not val:
                    continue
                ops.add(op)
                if isinstance(val, list):
                    ids.update(val)
            if ops:
                _c = out.setdefault(key, {"ops": set(), "ids": set()})
                _c["ops"] |= ops
                _c["ids"] |= ids
    return out


def _plan_reason(mdl, section, full: bool, stale_before):
    """Why `mdl` reloads whatever the SDE says changed, or None."""
    if full:
        return "full update"
    if not ESDE_SELECTIVE_UPDATES:
        return "selective updates disabled"
    if section is None:
        return "never loaded"
    if section.import_fingerprint != mdl.import_fingerprint():
        return "import code changed"
    if stale_before and section.last_update < stale_before:
        return f"not loaded in {ESDE_FULL_UPDATE_DAYS} days"
    return None


def plan_sde_update(target, full: bool = False):
    """
    {index in SDE_PARTS_TO_UPDATE: reason} for every model that needs loading
    to bring it to `target`: a REST release index (ESDE_SOURCE "rest") or a
    zip build number. Models left out are already up to date.
    """
    sections = {_s.sde_section: _s for _s in EveSDESection.objects.all()}
    stale_before = None
    if ESDE_FULL_UPDATE_DAYS:
        stale_before = datetime.now(tz=timezone.utc) - timedelta(days=ESDE_FULL_UPDATE_DAYS)
    if ESDE_SOURCE == "rest":
        return _plan_rest_update(target, sections, full, stale_before)
    return _plan_zip_update(target, sections, full, stale_before)


def fetch_rest_changes(index: dict):
    """
    (release compared with, {table: {"ops": {...}, "ids": {...}}}) from the
    release's _changes, or (None, None) when it can't be read.

    {"comparedWith": "tranquility@20261111T110708Z", "tables": [
        {"table": "types", "added": {"ints": [98700], "strings": []}, "schemaChanged": true}, ...]}
    """
    try:
        blob_url, url = sde_file_urls(index["tables"]["_changes"])
        response = httpx2.get(blob_url, follow_redirects=True)
        try:
            response.raise_for_status()
        except httpx2.HTTPStatusError:
            logger.warning(f"SDE changes - failed to read {blob_url}, trying {url}")
            response = httpx2.get(url, follow_redirects=True)
            response.raise_for_status()
        record = json.loads(next(_l for _l in response.text.splitlines() if _l.strip()))
        compared = record["comparedWith"].split("@", 1)[1]
    except Exception:
        logger.warning("SDE changes - failed to read _changes", exc_info=True)
        return None, None
    changes = {}
    for table in record.get("tables", []):
        ops = set()
        ids = set()
        for op, val in table.items():
            if op == "table" or not val:
                continue
            if isinstance(val, dict):
                _ids = val.get("ints", []) + val.get("strings", [])
                if not _ids:
                    continue
                ids.update(_ids)
            ops.add(op)
        if ops:
            changes[table["table"]] = {"ops": ops, "ids": ids}
    return compared, changes


def rest_changes_since(index: dict, releases) -> dict:
    """
    {release: changes from it up to `index`'s release} for each of `releases`
    still in CCP's history. Each release's _changes only reaches back one
    release, so this follows comparedWith back, merging as it goes, until
    every one is found or the next release back is gone (CCP keeps two).
    """
    wanted = set(releases)
    found = {}
    merged = {}
    current = index
    while wanted - found.keys():
        compared, changes = fetch_rest_changes(current)
        if changes is None:
            break
        for table, change in changes.items():
            _c = merged.setdefault(table, {"ops": set(), "ids": set()})
            _c["ops"] |= change["ops"]
            _c["ids"] |= change["ids"]
        found[compared] = {_t: {"ops": set(_c["ops"]), "ids": set(_c["ids"])} for _t, _c in merged.items()}
        if not wanted - found.keys():
            break
        try:
            response = httpx2.get(SDE_REST_URL.format(release=compared), follow_redirects=True)
            if response.status_code == 404:
                # retired, anything older reloads without row-level history
                break
            response.raise_for_status()
            current = response.json()
        except Exception:
            logger.warning(f"SDE changes - failed to read release {compared}", exc_info=True)
            break
    return {_r: _c for _r, _c in found.items() if _r in wanted}


def _plan_rest_update(index: dict, sections: dict, full: bool, stale_before):
    plan = {}
    pending = []  # a table the model reads has a new version
    for idx, mdl in enumerate(SDE_PARTS_TO_UPDATE):
        if mdl.sde_file_key() not in index["tables"]:
            # loading would fail on the missing table, this needs a code change
            logger.error(f"{mdl.__name__} - {mdl.Import.filename} is not in the SDE release, not reloading")
            continue
        section = sections.get(mdl.__name__)
        reason = _plan_reason(mdl, section, full, stale_before)
        if reason:
            plan[idx] = reason
            continue
        if getattr(mdl.Import, "extra_data", False) and section.release != index["release"]:
            # its outside data may have changed whatever the SDE tables did
            plan[idx] = "loads extra data from outside the SDE"
            continue
        versions = section.versions or {}
        for table in sde_tables_for([mdl]):
            if versions.get(table) != index["tables"].get(table, {}).get("version"):
                pending.append(idx)
                break

    if pending:
        # sections loaded from a release CCP no longer keeps (or from the zip) reload
        since = {sections[SDE_PARTS_TO_UPDATE[_i].__name__].release for _i in pending}
        history = rest_changes_since(index, since - {None, index["release"]})
        for idx in pending:
            mdl = SDE_PARTS_TO_UPDATE[idx]
            changes = history.get(sections[mdl.__name__].release)
            if changes is None:
                plan[idx] = "no row-level history"
                continue
            reason = mdl.change_reason(changes)
            if reason:
                plan[idx] = reason

    return dict(sorted(plan.items()))


def _plan_zip_update(target_build: int, sections: dict, full: bool, stale_before):
    plan = {}
    pending = {}  # index: build the model was last loaded from
    for idx, mdl in enumerate(SDE_PARTS_TO_UPDATE):
        section = sections.get(mdl.__name__)
        reason = _plan_reason(mdl, section, full, stale_before)
        if reason:
            plan[idx] = reason
        elif section.build_number > target_build:
            plan[idx] = f"loaded from newer build {section.build_number}"
        elif section.build_number < target_build:
            pending[idx] = section.build_number

    if pending:
        builds = fetch_sde_changes(target_build, min(pending.values()))
        for idx, since in pending.items():
            if builds is None:
                plan[idx] = "no SDE change history"
                continue
            reason = SDE_PARTS_TO_UPDATE[idx].change_reason(merge_sde_changes(builds, since))
            if reason:
                plan[idx] = reason

    return dict(sorted(plan.items()))


def log_sde_plan(target_build: int, plan: dict):
    logger.info(f"SDE Build:{target_build} - loading {len(plan)}/{len(SDE_PARTS_TO_UPDATE)} models")
    for idx, reason in plan.items():
        logger.info(f"SDE Build:{target_build} - {SDE_PARTS_TO_UPDATE[idx].__name__}: {reason}")


def download_extract_sde(build: int = None):
    """
    Download and extract the SDE, pinned to `build` when given, so a release
    landing mid-update can't mix builds. Defaults to the latest.
    """
    download_file(
        SDE_BUILD_URL.format(build=build) if build else SDE_URL,
        SDE_FILE_NAME
    )
    try:
        with zipfile.ZipFile(SDE_FILE_NAME, mode="r") as zf:
            zf.extractall(path=SDE_FOLDER)
    except Exception:
        logger.exception(f"Failed to extract {SDE_FILE_NAME}")
        delete_sde_folder()
        raise
    finally:
        # the zip is either fully extracted or unusable - either way it has no further use
        delete_sde_zip()

    if build:
        extracted = read_sde_version().get("buildNumber")
        if extracted != build:
            delete_sde_folder()
            raise ValueError(f"Downloaded SDE build {extracted}, expected {build}")


def process_section_of_sde(id: int = 0):
    """
        Update a SDE model.
    """
    SDE_PARTS_TO_UPDATE[id].load_from_sde(SDE_FOLDER)


def fetch_sde_for_plan(target, plan: dict):
    """
    Put what `plan` loads in SDE_FOLDER: each planned model's own table from
    the REST release `target` is the index of, or the whole zip of build
    `target`.
    """
    if ESDE_SOURCE == "rest":
        tables = dict.fromkeys(SDE_PARTS_TO_UPDATE[_i].sde_file_key() for _i in plan)
        fetch_sde_release(target, list(tables), SDE_FOLDER)
    else:
        download_extract_sde(target)


def fetch_whole_sde():
    """Every table of the latest SDE into SDE_FOLDER, for inspecting it."""
    if ESDE_SOURCE == "rest":
        index = get_sde_release()
        fetch_sde_release(index, [_t for _t in index["tables"] if not _t.startswith("_")], SDE_FOLDER)
    else:
        download_extract_sde()


def get_sde_target():
    """
    (what to update to, the record finish_sde_update saves): the latest REST
    release's index for both, or the zip's build number and latest.jsonl.
    """
    if ESDE_SOURCE == "rest":
        index = get_sde_release()
        return index, index
    latest = get_latest_sde()
    return latest.get("buildNumber"), latest


def process_from_sde(start_from: int = 0, full: bool = False):
    """
        Update the SDE models in order, only those the SDE says changed since
        they were last loaded unless `full`.
    """
    target, latest = get_sde_target()
    build = latest.get("buildNumber")
    plan = plan_sde_update(target, full=full)
    log_sde_plan(build, plan)

    if not plan:
        # nothing to load, don't download anything
        finish_sde_update(plan, latest)
        return

    fetch_sde_for_plan(target, {_i: _r for _i, _r in plan.items() if _i >= start_from})

    try:
        for idx, mdl in enumerate(SDE_PARTS_TO_UPDATE):
            if idx in plan and idx >= start_from:
                logger.info(f"Starting {mdl}")
                process_section_of_sde(idx)
            else:
                logger.info(f"Skipping {mdl}")

        delete_removed_rows()
        # only recorded as the current build if every section above completed
        finish_sde_update(plan, latest)
    finally:
        delete_sde_folder()


def delete_removed_rows():
    """
    Delete the rows each model found missing from the SDE as it loaded,
    children first, once everything moved to a new parent has been moved.
    A model whose rows can't be deleted (e.g. another app PROTECTs them) is
    logged and left, it doesn't stop the update.
    """
    for mdl in reversed(SDE_PARTS_TO_UPDATE):
        try:
            mdl.delete_removed()
        except Exception:
            logger.exception(f"{mdl.__name__} - Failed to remove rows no longer in the SDE")


def finish_sde_update(plan, sde_data: dict = None):
    """
    Record the new build once every planned model has loaded. Models left out
    of the plan had no changes, so they are now current at this build too.
    """
    build = set_sde_version(sde_data)
    skipped = [_m for _i, _m in enumerate(SDE_PARTS_TO_UPDATE) if _i not in plan]
    if not skipped:
        return
    if sde_data and "tables" in sde_data:
        # a REST release index, the skipped models' tables are current at it
        versions = {_t: _i["version"] for _t, _i in sde_data["tables"].items()}
        models = {_m.__name__: _m for _m in skipped}
        sections = list(EveSDESection.objects.filter(sde_section__in=models))
        for section in sections:
            section.build_number = build
            section.release = sde_data["release"]
            section.versions = section_versions(models[section.sde_section], versions)
        EveSDESection.objects.bulk_update(sections, ["build_number", "release", "versions"])
    else:
        EveSDESection.objects.filter(sde_section__in=[_m.__name__ for _m in skipped]).update(build_number=build)


def read_sde_version():
    try:
        with open(f"{SDE_FOLDER}/_sde.jsonl") as json_file:
            return json.loads(json_file.read())
    except Exception:
        logger.exception(f"Failed to read SDE version from {SDE_FOLDER}/_sde.jsonl")
        raise


def set_sde_version(sde_data: dict = None):
    """
    {"_key": "sde", "buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}

    From the SDE folder unless given the same record from latest.jsonl, or a
    REST release index (which also has "release").
    """
    if sde_data is None:
        sde_data = read_sde_version()
    build = sde_data.get("buildNumber", 0)
    release = datetime.now(tz=timezone.utc)
    release_date = sde_data.get("releaseDate")
    if release_date:
        if release_date.endswith("Z"):
            release_date = release_date[:-1] + "+00:00"
        release = datetime.fromisoformat(release_date)

    _o = EveSDE.get_solo()
    _o.build_number = build
    # None from the zip
    _o.release = sde_data.get("release")
    _o.release_date = release
    _o.last_check_date = datetime.now(tz=timezone.utc)
    _o.save()
    logger.info(f"SDE Updated to Build:{build} from:{release}")
    return build
