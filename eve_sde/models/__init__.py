"""
App Models
Create your models in here
"""

# Third Party
from solo.models import SingletonModel

# Django
from django.db import models

from .admin import *
from .map import *
from .types import *


class EveSDE(SingletonModel):

    build_number = models.IntegerField(default=None, null=True, blank=True)
    release_date = models.DateTimeField(default=None, null=True, blank=True)
    last_check_date = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        permissions = (("admin_access", "Can access admin page."),)
