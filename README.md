# Django Models from EVE SDE

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

## Credits

Because i am lazy, Shamlessley built using [This Template](https://github.com/ppfeufer/aa-example-plugin) \<3 @ppfeufer
