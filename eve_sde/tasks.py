"""App Tasks"""

# Standard Library
import logging

# Third Party
from celery import chain, shared_task

# Alliance Auth
from allianceauth.services.tasks import QueueOnce

# AA Example App
from eve_sde.sde_tasks import (
    SDE_PARTS_TO_UPDATE,
    delete_sde_folder,
    download_extract_sde,
    process_section_of_sde,
)

logger = logging.getLogger(__name__)

# What models and the order to load them


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
    delete_sde_folder()
