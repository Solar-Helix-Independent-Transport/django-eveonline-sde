"""App Tasks"""

# Standard Library
import logging

# Third Party
import httpx2
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
    finish_sde_update,
    get_latest_sde,
    log_sde_plan,
    plan_sde_update,
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
    autoretry_for=(httpx2.HTTPError,),
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
def update_models_from_sde(self, start_id: int = 0, full: bool = False):
    if ESDE_TASK_SPLIT:
        latest = get_latest_sde()
        build = latest.get("buildNumber")
        plan = plan_sde_update(build, full=full)
        log_sde_plan(build, plan)
        if not plan:
            # nothing to load, don't download anything
            finish_sde_update(plan, latest)
            return
        queue = [
            fetch_sde.si(build),
        ]
        for id in plan:
            if id >= start_id:
                queue.append(
                    process_sde_section.si(id)
                )
        queue.append(
            cleanup_sde.si(list(plan))
        )
        chain(queue).apply_async(link_error=cleanup_sde_after_failure.s())
    else:
        process_from_sde(start_from=start_id, full=full)


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
def fetch_sde(self, build: int = None):
    download_extract_sde(build)


@shared_task(
    bind=True,
    base=TaskLockBase,
)
def cleanup_sde(self, plan: list = None):
    if plan is None:
        # queued before selective updates, every model was loaded
        set_sde_version()
    else:
        finish_sde_update(plan)
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
