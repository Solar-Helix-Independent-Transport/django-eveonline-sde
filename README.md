# Django Models from EVE SDE

[![PyPI](https://img.shields.io/pypi/v/django-eveonline-sde?style=for-the-badge)](https://pypi.org/project/django-eveonline-sde/) [![Discord](https://img.shields.io/discord/399006117012832262?style=for-the-badge&label=Support%20Server)](https://discord.com/invite/fjnHAmk)

Base models from SDE, with an experiment in in-database translations pulled from the SDE and minor helpers for common functions.

A plain Django app - it works standalone, without [AllianceAuth](https://gitlab.com/allianceauth/allianceauth) installed. AllianceAuth is used opportunistically where it makes sense (see [Optional Settings](#optional-settings)) but is never a hard requirement.

[EVE SDE Docs](https://developers.eveonline.com/docs/services/static-data/)

[EVE SDE](https://developers.eveonline.com/static-data)

[EVE SDE API](https://sde.evetech.net/) (Early Access) - where the SDE is loaded from by default, see [Where the SDE comes from](#where-the-sde-comes-from)

See `eve_sde/sde_types.txt` for an idea of the top level fields that are available in the SDE, note that some fields have sub fields that are imported differently.

## Compatibility

- Python 3.10 - 3.14
- Django 5.2+
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
- Landmark
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
- Notification Types
- Corporation Role Groups
- Corporation Roles
- Metenox Moon Drill
- Skill Plans
  - Milestones
  - Skill Requirements
- Type Lists
  - Types
  - Groups
  - Categories
- Certificates
  - Skills
  - Recommended Types
- Masteries

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

- If you're **not** running [AllianceAuth](https://gitlab.com/allianceauth/allianceauth), set `LANGUAGES` yourself. `modeltranslation` adds one DB column per entry in `LANGUAGES` (e.g. `name_de`, `name_fr_fr`), and this package's migrations were generated against the exact set below, so it must match - AllianceAuth already ships this same `LANGUAGES` setting, which is why this step is only needed standalone.

  ```python
  LANGUAGES = (
      ("en", "English"),
      ("de", "German"),
      ("es", "Spanish"),
      ("it-it", "Italian"),
      ("ja", "Japanese"),
      ("ko-kr", "Korean"),
      ("fr-fr", "French"),
      ("nl-nl", "Dutch"),
      ("pl-pl", "Polish"),
      ("ru", "Russian"),
      ("uk", "Ukrainian"),
      ("zh-hans", "Simplified Chinese"),
  )

  USE_I18N = True
  ```

- Add `"eve_sde",` to your `INSTALLED_APPS`

- migrate etc

- `python manage.py esde_load_sde`

- Add a periodic task to check for SDE updates. They usually land after downtime, but CCP can release one at any time. The check is cheap: it sends the ETag of the last SDE API response (kept in Django's cache), so an unchanged SDE costs one small `304 Not Modified` request.

  ```python
  if "eve_sde" in INSTALLED_APPS:
      # Run at half past every hour
      CELERYBEAT_SCHEDULE["EVE SDE :: Check for SDE Updates"] = {
          "task": "eve_sde.tasks.check_for_sde_updates",
          "schedule": crontab(minute="30"),
      }
  ```

## Where the SDE comes from

By default the SDE is loaded from CCP's [SDE API](https://sde.evetech.net/), which serves each SDE table on its own. An update only downloads the tables it needs:

- Each loaded model remembers the release it was loaded from and the `version` of every table it reads (its own, plus any it looks things up in).
- On a new release, a model whose tables all still have the same `version` is skipped without downloading anything.
- When a `version` has changed, the release's `_changes` says which rows changed, and the model is only reloaded if they matter to it. A release that re-publishes the same data in a new format reloads nothing.
- `_changes` only compares a release with the one before it, and CCP only keeps the current and previous release. If a model was loaded from an older release than that, it's reloaded whenever any table it reads has a new `version`.

The SDE zip is still supported as a fallback, set [`ESDE_SOURCE`](#esde_source) to `"zip"`. It downloads the whole SDE and uses the zip's build changes feed to pick what to reload.

> [!NOTE]
> The first update after upgrading to a version with the SDE API reloads every model once, as nothing has been loaded from the API yet. Every update after that is selective. Switching `ESDE_SOURCE` from `"zip"` back to `"rest"` does the same for the models the zip loaded.

## Admin

Every SDE model is registered in the Django admin as read-only (browse/search only, no add/change/delete) under `/admin/eve_sde/`. Two extra pages aren't SDE data themselves, but report on the import process:

- **Django EvE SDE** (the app's own settings-style page) shows the currently-loaded build number, SDE API release (empty when loaded from the zip), release date, and last check time. The build number is also shown directly in the app's name in the admin sidebar/index, e.g. `Django EvE SDE v0.0.1 (SDE Build 3142455)`.
- **Sde sections** shows one row per model with its last update time and a row-count health indicator (green when the imported row count matches the source file's line count, red otherwise). Each row also holds the release and table versions the model was last loaded from, which decide whether the next update reloads it.

## Optional Settings

### `ESDE_SOURCE`

Where the SDE is loaded from. Defaults to `"rest"`, CCP's [SDE API](https://sde.evetech.net/), downloading only the tables that changed. Set to `"zip"` to download the whole SDE zip instead, a fallback while the SDE API is in Early Access. See [Where the SDE comes from](#where-the-sde-comes-from).

### `ESDE_SELECTIVE_UPDATES`

Defaults to `True`, only reloading the models whose SDE data changed since they were last loaded. Set to `False` to reload every model on every new SDE release.

### `ESDE_FULL_UPDATE_DAYS`

Defaults to `30`. A safety net for selective updates: any model that hasn't been reloaded for this many days is reloaded on the next update whatever the SDE says changed. `0` disables it.

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
