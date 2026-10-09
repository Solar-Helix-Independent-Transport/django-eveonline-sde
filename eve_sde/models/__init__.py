"""
App Models
Create your models in here
"""

# Third Party
from solo.models import SingletonModel

# Django
from django.db import models

# Django EVE SDE
from eve_sde.models.admin import *  # noqa: F401, F403
from eve_sde.models.freelance import *  # noqa: F401, F403
from eve_sde.models.industry import *  # noqa: F401, F403
from eve_sde.models.lore import *  # noqa: F401, F403
from eve_sde.models.map import *  # noqa: F401, F403
from eve_sde.models.misc import *  # noqa: F401, F403
from eve_sde.models.sovereignty import *  # noqa: F401, F403
from eve_sde.models.types import *  # noqa: F401, F403


class EveSDE(SingletonModel):

    build_number = models.IntegerField(default=None, null=True, blank=True)
    release_date = models.DateTimeField(default=None, null=True, blank=True)
    last_check_date = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        permissions = (("admin_access", "Can access admin page."),)
