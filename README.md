# Django Models from EVE SDE [![PyPI - Version](https://img.shields.io/pypi/v/django-eveonline-sde?style=for-the-badge)](https://pypi.org/project/django-eveonline-sde/)

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
- Stargate
- Item Groups
- Item Categories
- Item Types
- Item Dogma
- Dogma Categories
- Dogma Units
- Dogma Attributes

## Setup

1. `pip install `
1. modify your `local.py` as `modeltranslation` needs to be first in the list.

```
INSTALLED_APPS = ["modeltranslation",] + INSTALLED_APPS

INSTALLED_APPS += [
..... the rest of your apps
]
```

3. Add `"eve_sde",` to your `INSTALLED_APPS`
1. migrate etc
1. `python manage.py esde_laod_sde`
1. Add periodic task for `0 12 * * * check_for_sde_updates` SDE updates tend to happen at DT.

## Credits

Because i am lazy, Shamlessley built using [This Template](https://github.com/ppfeufer/aa-example-plugin) \<3 @ppfeufer
