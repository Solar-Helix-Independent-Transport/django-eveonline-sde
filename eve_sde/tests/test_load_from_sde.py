"""
Tests for JSONModel.load_from_sde's per-row error handling (models/base.py).

A single malformed line in an SDE jsonl file used to abort the entire
model's import. These confirm bad rows are now skipped and logged instead,
while valid rows in the same file still get imported.
"""
# Standard Library
import json
import os
import shutil
import tempfile

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde.models import EveSDESection, ItemCategory


class LoadFromSdeMalformedRowTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 42, "releaseDate": "2024-01-01T00:00:00Z"}))

    def _write_categories(self, lines):
        with open(os.path.join(self.tmpdir, "categories.jsonl"), "w") as f:
            for line in lines:
                f.write(line + "\n")

    def test_malformed_json_line_is_skipped_not_fatal(self):
        good_one = json.dumps({"_key": 1, "name": {"en": "Good One"}, "published": True, "iconID": 1})
        good_two = json.dumps({"_key": 2, "name": {"en": "Good Two"}, "published": True, "iconID": 2})
        self._write_categories([good_one, "{not valid json", good_two])

        ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.objects.count(), 2)
        self.assertTrue(ItemCategory.objects.filter(pk=1).exists())
        self.assertTrue(ItemCategory.objects.filter(pk=2).exists())

        section = EveSDESection.objects.get(sde_section="ItemCategory")
        self.assertEqual(section.total_rows, 2)

    def test_all_valid_rows_still_import_cleanly(self):
        good_one = json.dumps({"_key": 1, "name": {"en": "Good One"}, "published": True, "iconID": 1})
        good_two = json.dumps({"_key": 2, "name": {"en": "Good Two"}, "published": True, "iconID": 2})
        self._write_categories([good_one, good_two])

        ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.objects.count(), 2)
        section = EveSDESection.objects.get(sde_section="ItemCategory")
        self.assertEqual(section.total_rows, 2)
        self.assertEqual(section.total_lines, 2)

    def test_only_malformed_rows_imports_nothing_but_does_not_raise(self):
        self._write_categories(["{not valid json", "also not valid"])

        ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.objects.count(), 0)
        section = EveSDESection.objects.get(sde_section="ItemCategory")
        self.assertEqual(section.total_rows, 0)


class LoadFromSdeRemovedRowTests(TestCase):
    """Rows missing from the file are noted on the section for delete_removed, not deleted while loading."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        with open(os.path.join(self.tmpdir, "_sde.jsonl"), "w") as f:
            f.write(json.dumps({"buildNumber": 42, "releaseDate": "2024-01-01T00:00:00Z"}))
        self._write_categories([self._row(1), self._row(2), self._row(3)])
        ItemCategory.load_from_sde(self.tmpdir)

    @staticmethod
    def _row(key):
        return json.dumps({"_key": key, "name": {"en": f"Category {key}"}, "published": True})

    def _write_categories(self, lines):
        with open(os.path.join(self.tmpdir, "categories.jsonl"), "w") as f:
            for line in lines:
                f.write(line + "\n")

    def test_removed_rows_are_deleted_by_delete_removed(self):
        self._write_categories([self._row(1)])
        ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.objects.count(), 3)
        self.assertEqual(ItemCategory.delete_removed(), 2)
        self.assertEqual(list(ItemCategory.objects.values_list("pk", flat=True)), [1])
        self.assertEqual(ItemCategory.delete_removed(), 0)

    def test_a_malformed_row_stops_removal(self):
        self._write_categories([self._row(1), "{not valid json"])
        with self.assertLogs("eve_sde.models.base", "WARNING"):
            ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.delete_removed(), 0)
        self.assertEqual(ItemCategory.objects.count(), 3)

    def test_a_later_load_with_nothing_removed_clears_the_note(self):
        self._write_categories([self._row(1)])
        ItemCategory.load_from_sde(self.tmpdir)
        self._write_categories([self._row(1), self._row(2), self._row(3)])
        ItemCategory.load_from_sde(self.tmpdir)

        self.assertEqual(ItemCategory.delete_removed(), 0)


class UpdateSdeSectionStateTests(TestCase):

    def test_missing_sde_file_raises(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        with self.assertRaises(FileNotFoundError):
            ItemCategory.update_sde_section_state(tmpdir, "ItemCategory", 1, 1)
