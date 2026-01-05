# Django
from django.db import models


class EveSDESection(models.Model):
    sde_section = models.CharField(max_length=250)
    build_number = models.IntegerField()
    last_update = models.DateTimeField()
    total_lines = models.IntegerField()
    total_rows = models.IntegerField()
