# Django
from django.db import models


class PlanetManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("solar_system")


class MoonManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("solar_system", "item_type", "planet")
