"""
App Models
Create your models in here
"""

# Django
from django.db import models

from .map import *


class EveSDE(models.Model):

    build_number = models.IntegerField(default=None, null=True, blank=True)
    release_Date = models.DateTimeField(default=None, null=True, blank=True)

    class Meta:
        default_permissions = ()
        permissions = (("admin_access", "Can access admin page."),)
