"""App Tasks"""

# Standard Library
import logging

# Third Party
from celery import chain, shared_task

# Alliance Auth
from allianceauth.services.tasks import QueueOnce

# AA Example App
from eve_sde.models import EveSDE
from eve_sde.sde_tasks import (
    SDE_PARTS_TO_UPDATE,
    check_sde_version,
    cleanup_sde_po_files,
    delete_sde_folder,
    download_extract_sde,
    process_section_of_sde,
    set_sde_version,
    update_sde_mo_files,
)

logger = logging.getLogger(__name__)

# What models and the order to load them


@shared_task(
    bind=True,
    base=QueueOnce,
)
def check_for_sde_updates(self):
    if not check_sde_version():
        update_models_from_sde.delay()
    EveSDE.get_solo().save()


@shared_task(
    bind=True,
    base=QueueOnce,
)
def update_models_from_sde(self, start_id: int = 0):
    queue = [
        fetch_sde.si(),
    ]
    for id in range(start_id, len(SDE_PARTS_TO_UPDATE)):
        queue.append(
            process_sde_section.si(id)
        )
    queue.append(
        cleanup_sde.si()
    )
    queue
    chain(queue).apply_async()


@shared_task(
    bind=True,
    base=QueueOnce,
)
def process_sde_section(self, id: int = 0):
    process_section_of_sde(id)


@shared_task(
    bind=True,
    base=QueueOnce,
)
def fetch_sde(self):
    download_extract_sde()


@shared_task(
    bind=True,
    base=QueueOnce,
)
def cleanup_sde(self):
    cleanup_sde_po_files()
    update_sde_mo_files()
    set_sde_version()
    delete_sde_folder()
