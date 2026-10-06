"""
Tests for the certificate/mastery models in certificates.py:
- Certificate: translated name/description plus a group FK to ItemGroup.
- CertificateSkill/CertificateRecommendedType: skillTypes and recommendedFor
    are two independent lists on the same certificates.jsonl row, each
    flattened into its own join model.
- Mastery: masteries.jsonl is a nested {_key, _value} list of
    level -> certificate IDs per ship, flattened to one row per
    (ship, level, certificate).
- All three join models use Import.natural_key instead of wipe-and-reload:
    rows are matched to existing ones by their data, so pks stay stable
    across imports, changed rows are updated in place, and rows that drop
    out of the SDE are deleted.
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.certificates import (
    Certificate,
    CertificateRecommendedType,
    CertificateSkill,
    Mastery,
)
from eve_sde.models.types import ItemGroup, ItemType


class CertificateTestBase(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        ItemGroup.objects.create(id=255, name="Gunnery")
        ItemType.objects.create(id=3300, name="Gunnery")
        ItemType.objects.create(id=3303, name="Small Energy Turret")
        ItemType.objects.create(id=589, name="Executioner")
        ItemType.objects.create(id=597, name="Punisher")

    def _write(self, filename, rows):
        with open(os.path.join(self.tmpdir, filename), "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    def _write_certificate(self):
        self._write("certificates.jsonl", [{
            "_key": 50,
            "groupID": 255,
            "name": {"en": "Small Energy Turret", "de": "Kleine Energiegeschütztürme"},
            "description": {"en": "Small lasers."},
            "recommendedFor": [589, 597],
            "skillTypes": [
                {"_key": 3300, "basic": 3, "standard": 4, "improved": 4, "advanced": 5, "elite": 5},
                {"_key": 3303, "basic": 1, "standard": 3, "improved": 4, "advanced": 5, "elite": 5},
            ],
        }])


class CertificateLoadTests(CertificateTestBase):

    def test_loads_name_description_and_group(self):
        self._write_certificate()

        Certificate.load_from_sde(self.tmpdir)

        certificate = Certificate.objects.get(pk=50)
        self.assertEqual(certificate.name, "Small Energy Turret")
        self.assertEqual(certificate.name_de, "Kleine Energiegeschütztürme")
        self.assertEqual(certificate.description, "Small lasers.")
        self.assertEqual(certificate.group_id, 255)


class CertificateSkillAndRecommendedTypeLoadTests(CertificateTestBase):

    def setUp(self):
        super().setUp()
        self._write_certificate()
        Certificate.load_from_sde(self.tmpdir)

    def test_flattens_skill_types_with_tier_levels(self):
        CertificateSkill.load_from_sde(self.tmpdir)

        self.assertEqual(CertificateSkill.objects.count(), 2)
        skill = CertificateSkill.objects.get(item_type_id=3303)
        self.assertEqual(skill.certificate_id, 50)
        self.assertEqual(
            (skill.basic, skill.standard, skill.improved, skill.advanced, skill.elite),
            (1, 3, 4, 5, 5),
        )
        self.assertEqual(str(skill), "Small Energy Turret (Small Energy Turret)")

    def test_flattens_recommended_for(self):
        CertificateRecommendedType.load_from_sde(self.tmpdir)

        self.assertEqual(
            set(CertificateRecommendedType.objects.values_list("certificate_id", "item_type_id")),
            {(50, 589), (50, 597)},
        )

    def test_rerun_keeps_pks_instead_of_duplicating(self):
        CertificateSkill.load_from_sde(self.tmpdir)
        CertificateRecommendedType.load_from_sde(self.tmpdir)
        skill_pks = set(CertificateSkill.objects.values_list("pk", flat=True))
        recommended_pks = set(CertificateRecommendedType.objects.values_list("pk", flat=True))

        CertificateSkill.load_from_sde(self.tmpdir)
        CertificateRecommendedType.load_from_sde(self.tmpdir)

        self.assertEqual(set(CertificateSkill.objects.values_list("pk", flat=True)), skill_pks)
        self.assertEqual(set(CertificateRecommendedType.objects.values_list("pk", flat=True)), recommended_pks)

    def test_rerun_updates_changed_rows_in_place(self):
        CertificateSkill.load_from_sde(self.tmpdir)
        pk = CertificateSkill.objects.get(item_type_id=3303).pk

        self._write("certificates.jsonl", [{
            "_key": 50,
            "skillTypes": [
                {"_key": 3300, "basic": 3, "standard": 4, "improved": 4, "advanced": 5, "elite": 5},
                {"_key": 3303, "basic": 2, "standard": 3, "improved": 4, "advanced": 5, "elite": 5},
            ],
        }])
        CertificateSkill.load_from_sde(self.tmpdir)

        skill = CertificateSkill.objects.get(item_type_id=3303)
        self.assertEqual(skill.pk, pk)
        self.assertEqual(skill.basic, 2)
        self.assertEqual(CertificateSkill.objects.count(), 2)

    def test_rerun_deletes_rows_no_longer_in_the_sde(self):
        CertificateRecommendedType.load_from_sde(self.tmpdir)
        kept_pk = CertificateRecommendedType.objects.get(item_type_id=589).pk

        self._write("certificates.jsonl", [{"_key": 50, "recommendedFor": [589]}])
        CertificateRecommendedType.load_from_sde(self.tmpdir)

        self.assertEqual(list(CertificateRecommendedType.objects.values_list("pk", flat=True)), [kept_pk])

    def test_duplicate_natural_key_in_file_is_skipped(self):
        self._write("certificates.jsonl", [{"_key": 50, "recommendedFor": [589, 589, 597]}])

        with self.assertLogs("eve_sde.models.base", level="WARNING"):
            CertificateRecommendedType.load_from_sde(self.tmpdir)

        self.assertEqual(CertificateRecommendedType.objects.count(), 2)


class MasteryLoadTests(CertificateTestBase):

    def setUp(self):
        super().setUp()
        Certificate.objects.create(id=50, name="Small Energy Turret")
        Certificate.objects.create(id=51, name="Navigation")
        self._write("masteries.jsonl", [{
            "_key": 589,
            "_value": [
                {"_key": 0, "_value": [50]},
                {"_key": 4, "_value": [50, 51]},
            ],
        }])

    def test_flattens_levels_to_one_row_per_certificate(self):
        Mastery.load_from_sde(self.tmpdir)

        self.assertEqual(
            set(Mastery.objects.values_list("item_type_id", "level", "certificate_id")),
            {(589, 0, 50), (589, 4, 50), (589, 4, 51)},
        )
        self.assertEqual(
            str(Mastery.objects.get(level=0)),
            "Executioner (Mastery 1: Small Energy Turret)",
        )

    def test_rerun_syncs_by_ship_level_and_certificate(self):
        Mastery.load_from_sde(self.tmpdir)
        level_0_pk = Mastery.objects.get(level=0).pk

        # Navigation moves from level 4 to level 3
        self._write("masteries.jsonl", [{
            "_key": 589,
            "_value": [
                {"_key": 0, "_value": [50]},
                {"_key": 3, "_value": [51]},
                {"_key": 4, "_value": [50]},
            ],
        }])
        Mastery.load_from_sde(self.tmpdir)

        self.assertEqual(
            set(Mastery.objects.values_list("item_type_id", "level", "certificate_id")),
            {(589, 0, 50), (589, 3, 51), (589, 4, 50)},
        )
        self.assertEqual(Mastery.objects.get(level=0).pk, level_0_pk)
