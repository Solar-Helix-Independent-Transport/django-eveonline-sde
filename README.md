# Django Models from EVE SDE

[![PyPI](https://img.shields.io/pypi/v/django-eveonline-sde?style=for-the-badge)](https://pypi.org/project/django-eveonline-sde/) [![Discord](https://img.shields.io/discord/399006117012832262?style=for-the-badge&label=Support%20Server)](https://discord.com/invite/fjnHAmk)

Base models from SDE, with an experiment in in-database translations pulled from the SDE and minor helpers for common functions.

[EVE SDE Docs](https://developers.eveonline.com/docs/services/static-data/)

[EVE SDE](https://developers.eveonline.com/static-data)

See `eve_sde/sde_types.txt` for an idea of the top level fields that are available in the SDE, note that some fields have sub fields that are imported differently.

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

## Setup

- `pip install django-eveonline-sde`

- modify your `local.py` as `modeltranslation` needs to be first in the list.

  ```python
  INSTALLED_APPS = ["modeltranslation",] + INSTALLED_APPS

  INSTALLED_APPS += [
  ..... the rest of your apps
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

## Optional Settings

### `ESDE_BATCH_SIZE`

Defaults to `500` reduce for smaller DB inserts

### `ESDE_CHUNK_SIZE`

Defaults to `5000` reduce if heavily memory constrained

### `ESDE_TASK_SPLIT`

Defaults to `False` toggle if bare metal or you have a non standard persistent storage for your `myauth` folder in docker.
See [Issue #26](https://github.com/Solar-Helix-Independent-Transport/django-eveonline-sde/issues/26)

## Contributors

Thankyou to all our [contributors](https://github.com/Solar-Helix-Independent-Transport/django-eveonline-sde/graphs/contributors)!

![contributors](https://contrib.rocks/image?repo=Solar-Helix-Independent-Transport/django-eveonline-sde)

## Credits

Because i am lazy, Shamlessley built using [This Template](https://github.com/ppfeufer/aa-example-plugin) \<3 @ppfeufer
