# Django
from django.db import models


class EveSDESection(models.Model):
    sde_section = models.CharField(max_length=250)
    build_number = models.IntegerField()
    last_update = models.DateTimeField()
    total_lines = models.IntegerField()
    total_rows = models.IntegerField()
    # JSONModel.import_fingerprint() of the code that last loaded this section
    import_fingerprint = models.CharField(max_length=64, blank=True, default="")
    # pks the last load found missing from the SDE, deleted at the end of the update
    removed_pks = models.JSONField(default=list, blank=True)
    # REST release this section was last brought up to, None when the last load came from the zip
    release = models.CharField(max_length=32, null=True, blank=True, default=None)
    # {table: version hash} for this section's own table and its depends_on tables, from that release
    versions = models.JSONField(default=dict, blank=True)
