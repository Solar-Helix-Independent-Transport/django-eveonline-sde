"""
    Eve type models
"""
# Django
from django.db import models
from django.db.models import Model


class TypeBase(Model):
    id = models.BigIntegerField(
        primary_key=True
    )

    name = models.CharField(
        max_length=250
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.name} ({self.id})"


class EveType(TypeBase):
    pass


class typeDogma(TypeBase):
    pass


class typeBonus(TypeBase):
    pass


class typeMaterials(TypeBase):
    pass
