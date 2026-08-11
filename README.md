# Django Models from EVE SDE

[![PyPI](https://img.shields.io/pypi/v/django-eveonline-sde?style=for-the-badge)](https://pypi.org/project/django-eveonline-sde/) [![Discord](https://img.shields.io/discord/399006117012832262?style=for-the-badge&label=Support%20Server)](https://discord.com/invite/fjnHAmk)

Base models from SDE, with an experiment in in-database translations pulled from the SDE and minor helpers for common functions.

A plain Django app - it works standalone, without [AllianceAuth](https://gitlab.com/allianceauth/allianceauth) installed. AllianceAuth is used opportunistically where it makes sense (see [Optional Settings](#optional-settings)) but is never a hard requirement.

[EVE SDE Docs](https://developers.eveonline.com/docs/services/static-data/)

[EVE SDE](https://developers.eveonline.com/static-data)

See `eve_sde/sde_types.txt` for an idea of the top level fields that are available in the SDE, note that some fields have sub fields that are imported differently.

## Compatibility

- Python 3.10 - 3.14
- Django 4.2+
- Redis (required by [`celery-once`](https://github.com/cameronmaske/celery-once) for task locking)
- [AllianceAuth](https://gitlab.com/allianceauth/allianceauth) - optional, see [Optional Settings](#optional-settings)

## Current list of imported models

- Map
- Region
- Constellation
- SolarSystem
- Planet
- Moon
- NPC Station
- Stargate
- Item Market Groups
- Item Groups
- Item Categories
- Item Types
- Item Dogma
- Dogma Categories
- Dogma Units
- Dogma Attributes
- Dogma Effects
- Blueprints
  - Activities
    - Products
    - Materials
- Archetypes
- Freelance Job Schemas
  - Parameters
- Sovereignty Upgrades
- Accounting Entry Types

## Setup

- `pip install django-eveonline-sde`

- modify your `local.py` as `modeltranslation` needs to be first in the list.

  ```python
  INSTALLED_APPS = [
      "modeltranslation",
  ] + INSTALLED_APPS

  INSTALLED_APPS += [
      # ..... the rest of your apps
  ]
  ```

- Add `"eve_sde",` to your `INSTALLED_APPS`

- migrate etc

- `python manage.py esde_load_sde`

- Add a periodic task to check for SDE updates, which tend to happen after downtime.

  ```python
  if "eve_sde" in INSTALLED_APPS:
      # Run at 12:00 UTC each day
      CELERYBEAT_SCHEDULE["EVE SDE :: Check for SDE Updates"] = {
          "task": "eve_sde.tasks.check_for_sde_updates",
          "schedule": crontab(minute="0", hour="12"),
      }
  ```

## Admin

Every SDE model is registered in the Django admin as read-only (browse/search only, no add/change/delete) under `/admin/eve_sde/`. Two extra pages aren't SDE data themselves, but report on the import process:

- **Django EvE SDE** (the app's own settings-style page) shows the currently-loaded build number, release date, and last check time. The build number is also shown directly in the app's name in the admin sidebar/index, e.g. `Django EvE SDE v0.0.1 (SDE Build 3142455)`.
- **Sde sections** shows one row per model with its last update time and a row-count health indicator (green when the imported row count matches the source file's line count, red otherwise).

## Optional Settings

### `ESDE_BATCH_SIZE`

Defaults to `500` reduce for smaller DB inserts

### `ESDE_CHUNK_SIZE`

Defaults to `5000` reduce if heavily memory constrained

### `ESDE_TASK_SPLIT`

Splits the update tasks into smaller sub tasks
Defaults to `False` toggle if bare metal or you have a non standard persistent storage for your `myauth` folder in docker.
See [Issue #26](https://github.com/Solar-Helix-Independent-Transport/django-eveonline-sde/issues/26)

### `ESDE_CELERY_TASK_BASE`

The Celery task base class used for single-flight locking (skip re-queuing an update task while one is already running/queued). Defaults to AllianceAuth's `"allianceauth.services.tasks.QueueOnce"`. Set to a different `"package.module.ClassName"` import path, or leave the default - if AllianceAuth isn't installed, this automatically falls back to [`celery_once.QueueOnce`](https://github.com/cameronmaske/celery-once) directly with the same locking behavior.

### `ESDE_FREELANCE_FACTION_MODEL` / `ESDE_FREELANCE_CHARACTER_MODEL` / `ESDE_FREELANCE_CORPORATION_MODEL` / `ESDE_FREELANCE_ALLIANCE_MODEL`

Freelance job parameters can require a character, corporation, alliance, or faction as their value - these settings say which model each resolves to. Each is a `"package.module.ClassName"` import path, defaulting to AllianceAuth's `eveonline` models (`EveCharacter`, `EveCorporationInfo`, `EveAllianceInfo`, `EveFactionInfo`). Point them at your own equivalent models, or set any of them to `None`/leave unset to disable that value type - if the AllianceAuth default can't be imported (AllianceAuth not installed) it degrades to `None` automatically rather than raising an error.

## License

[GNU GPLv3](LICENSE)

## Contributors

Thankyou to all our [contributors](https://github.com/Solar-Helix-Independent-Transport/django-eveonline-sde/graphs/contributors)!

![contributors](https://contrib.rocks/image?repo=Solar-Helix-Independent-Transport/django-eveonline-sde)

## Credits

Because i am lazy, Shamlessley built using [This Template](https://github.com/ppfeufer/aa-example-plugin) \<3 @ppfeufer
