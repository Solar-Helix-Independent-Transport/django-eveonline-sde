"""
Tests for the management commands under eve_sde/management/commands/.

Each command is a thin wrapper around functions already covered directly in
test_sde_tasks.py / test_json_model_engine.py - these tests confirm the
command wires its arguments through correctly, not the underlying logic.
"""
# Standard Library
import io
import json
import os
import shutil
import tempfile
from unittest import mock

# Django
from django.core.management import call_command
from django.test import TestCase

# Django EVE SDE
from eve_sde.management.commands import esde_generate_test_data, esde_get_all_fields
from eve_sde.models import ItemCategory


class EsdeLoadSdeCommandTests(TestCase):

    def test_calls_process_from_sde(self):
        with mock.patch("eve_sde.management.commands.esde_load_sde.process_from_sde") as mock_process:
            call_command("esde_load_sde")

        mock_process.assert_called_once()


class EsdeLoadSdeSectionCommandTests(TestCase):

    def test_downloads_then_processes_section_seven(self):
        with mock.patch("eve_sde.management.commands.esde_load_sde_section.download_extract_sde") as mock_download, \
                mock.patch("eve_sde.management.commands.esde_load_sde_section.process_section_of_sde") as mock_process:
            call_command("esde_load_sde_section")

        mock_download.assert_called_once()
        mock_process.assert_called_once_with(7)


class EsdeModelStatsCommandTests(TestCase):

    def test_prints_a_count_for_a_real_concrete_model(self):
        ItemCategory.objects.create(id=1, name="Tritanium", published=True)

        out = io.StringIO()
        call_command("esde_model_stats", stdout=out)

        self.assertIn("ItemCategory - 1", out.getvalue())


class EsdeGetAllFieldsCommandTests(TestCase):

    def test_walks_extracted_files_and_reports_fields(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        with open(os.path.join(tmpdir, "categories.jsonl"), "w") as f:
            f.write(json.dumps({"_key": 1, "name": {"en": "Tritanium"}, "published": True}) + "\n")

        out = io.StringIO()
        with mock.patch.object(esde_get_all_fields, "SDE_FOLDER", tmpdir), \
                mock.patch.object(esde_get_all_fields, "download_extract_sde") as mock_download, \
                mock.patch.object(esde_get_all_fields, "delete_sde_folder") as mock_delete:
            call_command("esde_get_all_fields", stdout=out)

        mock_download.assert_called_once()
        mock_delete.assert_called_once()
        output = out.getvalue()
        self.assertIn("categories.jsonl", output)
        self.assertIn("_key", output)
        self.assertIn("name", output)
        # nested dict fields are reported as "<field>.<subfield>"
        self.assertIn("name.en", output)


class EsdeGenerateTestDataCommandTests(TestCase):

    def test_raises_when_sde_version_is_out_of_date(self):
        with mock.patch.object(esde_generate_test_data.Command, "_validate_application") as mock_validate, \
                mock.patch("eve_sde.management.commands.esde_generate_test_data.check_sde_version", return_value=False):
            with self.assertRaises(Exception):
                call_command("esde_generate_test_data", "eve_sde")

        mock_validate.assert_not_called()

    def test_ignore_version_flag_bypasses_the_version_check(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        ItemCategory.objects.create(id=1, name="Tritanium", published=True)

        fake_module = mock.MagicMock()
        fake_module.__path__ = [tmpdir]
        fake_module.testdata_spec = []

        with mock.patch("eve_sde.management.commands.esde_generate_test_data.check_sde_version", return_value=False), \
                mock.patch.object(
                    esde_generate_test_data.Command, "_validate_application", return_value=fake_module
        ) as mock_validate:
            call_command("esde_generate_test_data", "eve_sde", "--ignore_version", "true")

        mock_validate.assert_called_once()
        with open(os.path.join(tmpdir, "eve_sde_sde.json")) as f:
            # a valid, pretty-printed JSON array was written
            self.assertEqual(json.load(f), [])

    def test_validate_application_rejects_a_path_matching_the_site_packages_pattern(self):
        # re.match anchors at the start of the string, so only a path that
        # literally begins with "python3.<digits>/site-packages" trips this -
        # a normal venv path like "/home/user/.venv/lib/python3.12/site-packages/x"
        # does NOT match, since it doesn't start at position 0.
        command = esde_generate_test_data.Command()
        fake_app_config = mock.MagicMock()
        fake_app_config.path = "python3.12/site-packages/some_app"

        with mock.patch(
            "eve_sde.management.commands.esde_generate_test_data.apps.get_app_config",
            return_value=fake_app_config,
        ):
            with self.assertRaises(AssertionError):
                command._validate_application("some_app", force_editable=False)

    def test_validate_application_allows_an_editable_looking_path_by_default(self):
        command = esde_generate_test_data.Command()
        fake_app_config = mock.MagicMock()
        fake_app_config.path = "/home/user/dev/eve_sde"

        with mock.patch(
            "eve_sde.management.commands.esde_generate_test_data.apps.get_app_config",
            return_value=fake_app_config,
        ):
            module = command._validate_application("eve_sde", force_editable=False)

        self.assertEqual(module.__name__, "eve_sde.fixtures")
