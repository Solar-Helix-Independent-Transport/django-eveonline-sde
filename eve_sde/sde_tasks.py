# Standard Library
import json
import logging
import os
import shutil
import zipfile
from datetime import datetime, timezone

# Third Party
import httpx

# Django EVE SDE
from eve_sde.models import EveSDE
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
]

SDE_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"
SDE_FILE_NAME = "eve-online-static-data-latest-jsonl.zip"
SDE_FOLDER = "eve-sde"


def download_file(url, local_filename):
    """
    Downloads a file from a given URL using httpx and saves it locally.

    Args:
        url (str): The URL of the file to download.
        local_filename (str): The path and name to save the downloaded file.

    Raises:
        Exception: Re-raises any download failure after logging it, and removes
            any partially written file so callers never see a truncated/corrupt
            local file mistaken for a good one.
    """
    try:
        with httpx.stream("GET", url, follow_redirects=True) as response:
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


def check_sde_version():
    """
    {"_key": "sde", "buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}
    """
    url = "https://developers.eveonline.com/static-data/tranquility/latest.jsonl"
    try:
        response = httpx.get(url)
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.exception(f"Failed to check SDE version from {url}")
        raise

    build_number = data.get("buildNumber")

    current = EveSDE.get_solo()

    if current.build_number != build_number:
        return False

    return True


def download_extract_sde():
    download_file(
        SDE_URL,
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


def process_section_of_sde(id: int = 0):
    """
        Update a SDE model.
    """
    SDE_PARTS_TO_UPDATE[id].load_from_sde(SDE_FOLDER)


def process_from_sde(start_from: int = 0):
    """
        Update the SDE models in order.
    """
    download_extract_sde()

    try:
        count = 0
        for mdl in SDE_PARTS_TO_UPDATE:
            if count >= start_from:
                logger.info(f"Starting {mdl}")
                process_section_of_sde(count)
            else:
                logger.info(f"Skipping {mdl}")
            count += 1

        # only recorded as the current build if every section above completed
        set_sde_version()
    finally:
        delete_sde_folder()


def set_sde_version():
    """
    {"_key": "sde", "buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}
    """
    build = 0
    release = datetime.now(tz=timezone.utc)

    try:
        with open(f"{SDE_FOLDER}/_sde.jsonl") as json_file:
            sde_data = json.loads(json_file.read())
            build = sde_data.get("buildNumber", 0)
            release_date = sde_data.get("releaseDate")
            if release_date.endswith("Z"):
                release_date = release_date[:-1] + "+00:00"

            release = datetime.fromisoformat(release_date)
    except Exception:
        logger.exception(f"Failed to read SDE version from {SDE_FOLDER}/_sde.jsonl")
        raise

    _o = EveSDE.get_solo()
    _o.build_number = build
    _o.release_date = release
    _o.last_check_date = datetime.now(tz=timezone.utc)
    _o.save()
    logger.info(f"SDE Updated to Build:{build} from:{release}")
