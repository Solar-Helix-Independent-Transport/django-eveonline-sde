# Standard Library
import glob
import json
import logging
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# Third Party
import httpx
import polib

# Django
from django.conf import settings
from django.core.management import call_command
from django.utils.translation import activate

# AA Example App
from eve_sde.models import EveSDE
from eve_sde.models.utils import chunked_queryset, get_langs, update_po_file

from .models.map import Constellation, Moon, Planet, Region, SolarSystem, Stargate
from .models.types import ItemCategory, ItemGroup, ItemType, ItemTypeMaterials

logger = logging.getLogger(__name__)

# What models and the order to load them
SDE_PARTS_TO_UPDATE = [
    # # Types
    ItemCategory,
    ItemGroup,
    ItemType,
    ItemTypeMaterials,
    # # Map
    Region,
    Constellation,
    SolarSystem,
    # # System stuffs
    Stargate,
    Planet,
    Moon,
    # EveItemDogmaAttribute,
    # # Type Materials
    # InvTypeMaterials,
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
        print(f"File downloaded successfully to: {local_filename}")
    except httpx.HTTPStatusError as e:
        print(f"HTTP error during download: {e}")
    except httpx.RequestError as e:
        print(f"Network error during download: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


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
    generate_sde_po_files()


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

    cleanup_sde_po_files()
    update_sde_mo_files()
    set_sde_version()
    delete_sde_folder()


def generate_sde_po_files():
    base = settings.LOCALE_PATHS[0]
    langs = get_langs()
    for l in langs:
        file_path = Path(f"{base}{l}/LC_MESSAGES/django.po")
        if file_path.exists():
            file_path.unlink()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        po = polib.POFile()
        po.metadata = {
            'MIME-Version': '1.0',
            'Content-Type': 'text/plain; charset=utf-8',
            'Content-Transfer-Encoding': '8bit',
        }
        po.fpath = str(file_path)
        po.save()


def cleanup_sde_po_files():
    base = settings.LOCALE_PATHS[0]
    langs = get_langs()
    for l in langs:
        file_path = Path(f"{base}{l}/LC_MESSAGES/django.po")
        logger.info(f"CLEANUP {file_path}")
        subprocess.run(["msguniq", "--use-first", f"{file_path}", "-o", f"{file_path}"])


def update_sde_mo_files():
    call_command("compilemessages")


def set_sde_version():
    """
    {"_key": "sde", "buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}
    """
    build = 0
    release = datetime.now(tz=timezone.utc)

    with open(f"{SDE_FOLDER}/_sde.jsonl") as json_file:
        sde_data = json.loads(json_file.read())
        build = sde_data.get("buildNumber", 0)
        release = datetime.fromisoformat(sde_data.get("releaseDate"))

    _o = EveSDE.get_solo()
    _o.build_number = build
    _o.release_date = release
    _o.save()
    logger.info(f"SDE Updated to Build:{build} from:{release}")


def generate_sde_celestial_names():
    """TODO Investigate doing this on the fly vs compiling it.
    """
    models = [
        Planet,
        Moon
    ]
    base = settings.LOCALE_PATHS[0]
    langs = get_langs()
    for cls in models:
        logger.info(f"{cls.__name__} - Starting")
        total = cls.objects.all().count()
        updates = {}
        count = 0
        processed = 0
        for m in chunked_queryset(cls.objects.all()):
            for l in langs:
                activate(l)
                if l not in updates:
                    updates[l] = []
                k = m.name
                v = m.localized_name
                if k != v:
                    updates[l].append({"k": k, "v": v, "l": 0})
            if count >= 5000:
                update_po_file(updates, cls.__name__)
                updates = {}
                count = 0
                logger.info(f"{cls.__name__} - {processed}/{total}")
            count += 1
            processed += 1
        update_po_file(updates, cls.__name__)
        logger.info(f"{cls.__name__} - Done")
