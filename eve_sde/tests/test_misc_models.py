"""
Tests for the standalone lookup models in misc.py:
- AccountingEntryType: journalMessage/description are optional per-row in the
    SDE source, so a row lacking them should still load cleanly.
- NotificationType: displayName is missing on a handful of rows in the SDE
    source, so name has to tolerate that (unlike TypeBase's non-null name).
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models.misc import AccountingEntryType, NotificationType


class AccountingEntryTypeLoadTests(TestCase):

    def test_loads_internal_name_and_lang_fields(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 1,
            "internalName": "player_trading",
            "name": {"en": "Player Trading", "de": "Spieler-Handel"},
            "journalMessage": {"en": "Direct trade between {name1} and {name2}"},
            "description": {"en": "Player to player trading"},
        }
        with open(os.path.join(tmpdir, "accountingEntryTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        AccountingEntryType.load_from_sde(tmpdir)

        entry = AccountingEntryType.objects.get(pk=1)
        self.assertEqual(entry.internal_name, "player_trading")
        self.assertEqual(entry.name, "Player Trading")
        self.assertEqual(entry.name_de, "Spieler-Handel")
        self.assertEqual(entry.journal_message, "Direct trade between {name1} and {name2}")
        self.assertEqual(entry.description, "Player to player trading")

    def test_journal_message_and_description_are_optional(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {"_key": 0, "internalName": "undefined", "name": {"en": "Undefined"}}
        with open(os.path.join(tmpdir, "accountingEntryTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        AccountingEntryType.load_from_sde(tmpdir)

        entry = AccountingEntryType.objects.get(pk=0)
        self.assertIsNone(entry.journal_message)
        self.assertIsNone(entry.description)


class NotificationTypeLoadTests(TestCase):

    def test_loads_internal_name_and_lang_name(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {
            "_key": 1,
            "internalName": "CharMedalMsg",
            "displayName": {"en": "Medal Awarded", "de": "Orden erhalten"},
        }
        with open(os.path.join(tmpdir, "notificationTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        NotificationType.load_from_sde(tmpdir)

        entry = NotificationType.objects.get(pk=1)
        self.assertEqual(entry.internal_name, "CharMedalMsg")
        self.assertEqual(entry.name, "Medal Awarded")
        self.assertEqual(entry.name_de, "Orden erhalten")

    def test_missing_display_name_loads_with_null_name(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 1, "releaseDate": "2024-01-01T00:00:00Z"}))

        row = {"_key": 297, "internalName": "FreelanceProjectACLDeleted"}
        with open(os.path.join(tmpdir, "notificationTypes.jsonl"), "w") as f:
            f.write(json.dumps(row) + "\n")

        NotificationType.load_from_sde(tmpdir)

        entry = NotificationType.objects.get(pk=297)
        self.assertIsNone(entry.name)
        self.assertEqual(entry.internal_name, "FreelanceProjectACLDeleted")

    def test_str_includes_name_and_id(self):
        notification_type = NotificationType(id=3, name="Medal Awarded")
        self.assertEqual(str(notification_type), "Medal Awarded (3)")
