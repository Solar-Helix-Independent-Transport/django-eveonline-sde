# Standard Library
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone

# Third Party
import httpx

# Alliance Auth
from allianceauth.services.hooks import get_extension_logger

from .models import EveSDE
from .models.freelance import FreelanceJobSchema, FreelanceJobSchemaParameter
from .models.industry import (
    BlueprintActivity,
    BlueprintActivityMaterial,
    BlueprintActivityProduct,
)
from .models.lore import Archetype
from .models.map import (
    Constellation,
    Moon,
    NPCStation,
    Planet,
    Region,
    SolarSystem,
    Stargate,
)
from .models.types import (
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
)

logger = get_extension_logger(__name__)

# What models and the order to load them
SDE_PARTS_TO_UPDATE = [
    # Types
    ItemCategory,
    ItemGroup,
    ItemMarketGroup,
    ItemType,  # Requires: ItemGroup and ItemMarketGroup
    ItemTypeMaterials,
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
    #  System stuffs
    NPCStation,  # Requires: SolarSystem, ItemType
    Stargate,
    Planet,
    Moon,
    # Lore / reference
    Archetype,
    # Freelance Jobs
    FreelanceJobSchema,
    FreelanceJobSchemaParameter,  # Requires: FreelanceJobSchema
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
    """
    try:
        with httpx.stream("GET", url, follow_redirects=True) as response:
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)
            with open(local_filename, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        logger.info(f"File downloaded successfully to: {local_filename}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during download: {e}")
    except httpx.RequestError as e:
        logger.error(f"Network error during download: {e}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")


def delete_sde_zip():
    os.remove(SDE_FILE_NAME)


def delete_sde_folder():
    shutil.rmtree(SDE_FOLDER)


def check_sde_version():
    """
    {"_key": "sde", "buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}
    """
    url = "https://developers.eveonline.com/static-data/tranquility/latest.jsonl"
    data = httpx.get(url).json()

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
    with zipfile.ZipFile(SDE_FILE_NAME, mode="r") as zf:
        zf.extractall(path=SDE_FOLDER)
    # delete the zip
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

    count = 0
    for mdl in SDE_PARTS_TO_UPDATE:
        if count >= start_from:
            logger.info(f"Starting {mdl}")
            process_section_of_sde(count)
        else:
            logger.info(f"Skipping {mdl}")
        count += 1

    set_sde_version()
    delete_sde_folder()


def set_sde_version():
    """
    {"_key": "sde", "buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}
    """
    build = 0
    release = datetime.now(tz=timezone.utc)

    with open(f"{SDE_FOLDER}/_sde.jsonl") as json_file:
        sde_data = json.loads(json_file.read())
        build = sde_data.get("buildNumber", 0)
        release_date = sde_data.get("releaseDate")
        if release_date.endswith("Z"):
            release_date = release_date[:-1] + "+00:00"

        release = datetime.fromisoformat(release_date)

    _o = EveSDE.get_solo()
    _o.build_number = build
    _o.release_date = release
    _o.last_check_date = datetime.now(tz=timezone.utc)
    _o.save()
    logger.info(f"SDE Updated to Build:{build} from:{release}")
