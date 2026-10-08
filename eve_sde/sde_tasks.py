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
from eve_sde.app_settings import ESDE_FULL_UPDATE_DAYS, ESDE_SELECTIVE_UPDATES
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


def download_file(url, local_filename):
    """
    Downloads a file from a given URL using httpx2 and saves it locally.

    Args:
        url (str): The URL of the file to download.
        local_filename (str): The path and name to save the downloaded file.

    Raises:
        Exception: Re-raises any download failure after logging it, and removes
            any partially written file so callers never see a truncated/corrupt
            local file mistaken for a good one.
    """
    try:
        with httpx2.stream("GET", url, follow_redirects=True) as response:
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
    build_number = get_latest_sde().get("buildNumber")

    current = EveSDE.get_solo()

    if current.build_number != build_number:
        return False

    return True


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


def plan_sde_update(target_build: int, full: bool = False):
    """
    {index in SDE_PARTS_TO_UPDATE: reason} for every model that needs loading
    to bring it to target_build. Models left out are already up to date.
    """
    sections = {_s.sde_section: _s for _s in EveSDESection.objects.all()}
    stale_before = None
    if ESDE_FULL_UPDATE_DAYS:
        stale_before = datetime.now(tz=timezone.utc) - timedelta(days=ESDE_FULL_UPDATE_DAYS)

    plan = {}
    pending = {}  # index: build the model was last loaded from
    for idx, mdl in enumerate(SDE_PARTS_TO_UPDATE):
        section = sections.get(mdl.__name__)
        if full:
            plan[idx] = "full update"
        elif not ESDE_SELECTIVE_UPDATES:
            plan[idx] = "selective updates disabled"
        elif section is None:
            plan[idx] = "never loaded"
        elif section.import_fingerprint != mdl.import_fingerprint():
            plan[idx] = "import code changed"
        elif stale_before and section.last_update < stale_before:
            plan[idx] = f"not loaded in {ESDE_FULL_UPDATE_DAYS} days"
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


def process_from_sde(start_from: int = 0, full: bool = False):
    """
        Update the SDE models in order, only those the SDE changes feed says
        changed since they were last loaded unless `full`.
    """
    latest = get_latest_sde()
    build = latest.get("buildNumber")
    plan = plan_sde_update(build, full=full)
    log_sde_plan(build, plan)

    if not plan:
        # nothing to load, don't download anything
        finish_sde_update(plan, latest)
        return

    download_extract_sde(build)

    try:
        for idx, mdl in enumerate(SDE_PARTS_TO_UPDATE):
            if idx in plan and idx >= start_from:
                logger.info(f"Starting {mdl}")
                process_section_of_sde(idx)
            else:
                logger.info(f"Skipping {mdl}")

        delete_removed_rows()
        # only recorded as the current build if every section above completed
        finish_sde_update(plan)
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
    skipped = [_m.__name__ for _i, _m in enumerate(SDE_PARTS_TO_UPDATE) if _i not in plan]
    if skipped:
        EveSDESection.objects.filter(sde_section__in=skipped).update(build_number=build)


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

    From the extracted SDE unless given the same record from latest.jsonl.
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
    _o.release_date = release
    _o.last_check_date = datetime.now(tz=timezone.utc)
    _o.save()
    logger.info(f"SDE Updated to Build:{build} from:{release}")
    return build
