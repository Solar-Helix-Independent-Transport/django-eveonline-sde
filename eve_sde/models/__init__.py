"""
App Models
Create your models in here
"""

# Third Party
from solo.models import SingletonModel

# Django EVE SDE
from eve_sde.models.admin import *
from eve_sde.models.freelance import *
from eve_sde.models.industry import *
from eve_sde.models.lore import *
from eve_sde.models.map import *
from eve_sde.models.misc import *
from eve_sde.models.sovereignty import *
from eve_sde.models.types import *


class EveSDE(SingletonModel):

    build_number = models.IntegerField(default=None, null=True, blank=True)
    release_date = models.DateTimeField(default=None, null=True, blank=True)
    last_check_date = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        permissions = (("admin_access", "Can access admin page."),)
