"""App Tasks"""

# Third Party
import httpx
from celery import chain, shared_task

# Django
from django.utils import timezone

# Alliance Auth
from allianceauth.services.hooks import get_extension_logger
from allianceauth.services.tasks import QueueOnce

# Django EVE SDE
from eve_sde.app_settings import ESDE_TASK_SPLIT
from eve_sde.models import EveSDE
from eve_sde.sde_tasks import (
    SDE_PARTS_TO_UPDATE,
    check_sde_version,
    delete_sde_folder,
    download_extract_sde,
    process_from_sde,
    process_section_of_sde,
    set_sde_version,
)

logger = get_extension_logger(__name__)

# What models and the order to load them

# Network calls to CCP's SDE endpoints are the only genuinely transient
# failure mode here - retry those with backoff rather than waiting for the
# next scheduled check. Bad/malformed SDE data is not retried: it will fail
# the same way every time and should surface immediately.
NETWORK_RETRY_KWARGS = dict(
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=60,
    retry_backoff_max=600,
    max_retries=5,
)


@shared_task(
    bind=True,
    base=QueueOnce,
    **NETWORK_RETRY_KWARGS,
)
def check_for_sde_updates(self):
    if not check_sde_version():
        update_models_from_sde.delay()

    _o = EveSDE.get_solo()
    _o.last_check_date = timezone.now()
    _o.save()


@shared_task(
    bind=True,
    base=QueueOnce,
    **NETWORK_RETRY_KWARGS,
)
def update_models_from_sde(self, start_id: int = 0):
    if ESDE_TASK_SPLIT:
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
        chain(queue).apply_async(link_error=cleanup_sde_after_failure.s())
    else:
        process_from_sde()


@shared_task(
    bind=True,
    base=QueueOnce,
)
def process_sde_section(self, id: int = 0):
    process_section_of_sde(id)


@shared_task(
    bind=True,
    base=QueueOnce,
    **NETWORK_RETRY_KWARGS,
)
def fetch_sde(self):
    download_extract_sde()


@shared_task(
    bind=True,
    base=QueueOnce,
)
def cleanup_sde(self):
    set_sde_version()
    delete_sde_folder()


@shared_task(bind=True)
def cleanup_sde_after_failure(self, *args, **kwargs):
    """
    Error callback for the split-task chain. If any section fails partway
    through, the chain aborts and `cleanup_sde` never runs - this removes the
    partially-extracted SDE folder so the next attempt starts clean, without
    marking the failed build as installed.
    """
    logger.error("SDE update chain failed - cleaning up partial download")
    delete_sde_folder()
