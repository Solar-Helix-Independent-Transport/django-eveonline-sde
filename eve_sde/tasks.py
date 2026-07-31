"""App Tasks"""

# Standard Library
import logging

# Third Party
import httpx
from celery import chain, shared_task

# Django
from django.utils import timezone
from django.utils.module_loading import import_string

# Django EVE SDE
from eve_sde.app_settings import ESDE_CELERY_TASK_BASE, ESDE_TASK_SPLIT
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

logger = logging.getLogger(__name__)


def _resolve_task_lock_base():
    """
    Resolve the single-flight task-locking base class (skip re-queuing a task
    while one is already running/queued) from ESDE_CELERY_TASK_BASE, which
    defaults to AllianceAuth's QueueOnce.

    The actual locking behavior comes from celery_once either way -
    AllianceAuth's version is just a thin subclass that sets
    once['graceful']=True. If the configured class can't be imported (e.g.
    AllianceAuth isn't installed), fall back to celery_once.QueueOnce
    directly with that same graceful=True behavior, rather than requiring
    AllianceAuth specifically.
    """
    try:
        return import_string(ESDE_CELERY_TASK_BASE)
    except ImportError:
        # Third Party
        from celery_once import QueueOnce as _CeleryOnceQueueOnce

        class _FallbackQueueOnce(_CeleryOnceQueueOnce):
            once = {**_CeleryOnceQueueOnce.once, "graceful": True}

        return _FallbackQueueOnce


TaskLockBase = _resolve_task_lock_base()

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
    base=TaskLockBase,
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
    base=TaskLockBase,
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
    base=TaskLockBase,
)
def process_sde_section(self, id: int = 0):
    process_section_of_sde(id)


@shared_task(
    bind=True,
    base=TaskLockBase,
    **NETWORK_RETRY_KWARGS,
)
def fetch_sde(self):
    download_extract_sde()


@shared_task(
    bind=True,
    base=TaskLockBase,
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
