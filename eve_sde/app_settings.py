"""App Settings"""

# Django
from django.conf import settings

# # put your app settings here

# Chunks for the update tasks
# Reduce for memory constrained systems
ESDE_CHUNK_SIZE = getattr(settings, "ESDE_CHUNK_SIZE", 5000)
ESDE_BATCH_SIZE = getattr(settings, "ESDE_BATCH_SIZE", 500)

# Fix for Docker environments
# if persistent storage is used for `myauth` set to True for smaller update tasks.
ESDE_TASK_SPLIT = getattr(settings, "ESDE_TASK_SPLIT", False)

# Models a Freelance job parameter's "character"/"corporation"/"alliance"/
# "faction" accepted_value_types resolve to - these represent AllianceAuth's
# ESI-synced character/corp/alliance data, not SDE data, so they're the one
# place this app reaches outside the SDE. Each is a "package.module.ClassName"
# import path, resolved lazily (not at import time) so a project without
# AllianceAuth installed doesn't crash just importing eve_sde.models - set
# any of these to None to disable that value type entirely instead.
ESDE_FREELANCE_FACTION_MODEL = getattr(
    settings, "ESDE_FREELANCE_FACTION_MODEL", "allianceauth.eveonline.models.EveFactionInfo"
)
ESDE_FREELANCE_CHARACTER_MODEL = getattr(
    settings, "ESDE_FREELANCE_CHARACTER_MODEL", "allianceauth.eveonline.models.EveCharacter"
)
ESDE_FREELANCE_CORPORATION_MODEL = getattr(
    settings, "ESDE_FREELANCE_CORPORATION_MODEL", "allianceauth.eveonline.models.EveCorporationInfo"
)
ESDE_FREELANCE_ALLIANCE_MODEL = getattr(
    settings, "ESDE_FREELANCE_ALLIANCE_MODEL", "allianceauth.eveonline.models.EveAllianceInfo"
)

# Celery task base class used for single-flight locking (skip re-queuing an
# update task while one is already running/queued). Defaults to
# AllianceAuth's thin wrapper around celery_once.QueueOnce (just sets
# once['graceful']=True); a "package.module.ClassName" import path, resolved
# lazily. If it can't be imported (e.g. AllianceAuth isn't installed), tasks.py
# falls back to celery_once.QueueOnce directly with the same graceful=True
# behavior, rather than requiring AllianceAuth specifically.
ESDE_CELERY_TASK_BASE = getattr(
    settings, "ESDE_CELERY_TASK_BASE", "allianceauth.services.tasks.QueueOnce"
)
