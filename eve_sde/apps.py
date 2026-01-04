"""App Configuration"""

# Django
from django.apps import AppConfig

# AA Example App
from eve_sde import __version__


class EveSDEConfig(AppConfig):
    """App Config"""

    name = "eve_sde"
    label = "eve_sde"
    verbose_name = f"Django EvE SDE v{__version__}"
