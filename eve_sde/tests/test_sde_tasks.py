"""
Tests for the plain-python SDE download/extract/import pipeline in sde_tasks.py.

These cover the failure paths that used to be silently swallowed or left
partial state on disk: failed downloads, corrupt zips, malformed rows, and
partway-through import failures.
"""
# Standard Library
import os
import shutil
import tempfile
import zipfile
from unittest import mock

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde import sde_tasks


class DownloadFileTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.target = os.path.join(self.tmpdir, "out.bin")

    @staticmethod
    def _stream_context(fake_response):
        cm = mock.MagicMock()
        cm.__enter__.return_value = fake_response
        cm.__exit__.return_value = False
        return cm

    def test_success_writes_full_file(self):
        fake_response = mock.MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.iter_bytes.return_value = [b"abc", b"def"]

        with mock.patch.object(sde_tasks.httpx, "stream", return_value=self._stream_context(fake_response)):
            sde_tasks.download_file("http://example.test/file", self.target)

        with open(self.target, "rb") as f:
            self.assertEqual(f.read(), b"abcdef")

    def test_failure_mid_stream_removes_partial_file_and_raises(self):
        fake_response = mock.MagicMock()
        fake_response.raise_for_status.return_value = None

        def bad_iter():
            yield b"partial-data"
            raise RuntimeError("connection dropped")

        fake_response.iter_bytes.return_value = bad_iter()

        with mock.patch.object(sde_tasks.httpx, "stream", return_value=self._stream_context(fake_response)):
            with self.assertRaises(RuntimeError):
                sde_tasks.download_file("http://example.test/file", self.target)

        self.assertFalse(os.path.exists(self.target))

    def test_http_status_error_removes_partial_file_and_raises(self):
        fake_response = mock.MagicMock()
        fake_response.raise_for_status.side_effect = sde_tasks.httpx.HTTPStatusError(
            "not found", request=mock.MagicMock(), response=mock.MagicMock(status_code=404)
        )

        with mock.patch.object(sde_tasks.httpx, "stream", return_value=self._stream_context(fake_response)):
            with self.assertRaises(sde_tasks.httpx.HTTPStatusError):
                sde_tasks.download_file("http://example.test/file", self.target)

        self.assertFalse(os.path.exists(self.target))


class CheckSdeVersionTests(TestCase):

    def test_raises_when_upstream_check_fails(self):
        with mock.patch.object(sde_tasks.httpx, "get", side_effect=RuntimeError("network down")):
            with self.assertRaises(RuntimeError):
                sde_tasks.check_sde_version()

    def test_returns_false_when_build_number_differs(self):
        current = sde_tasks.EveSDE.get_solo()
        current.build_number = 111
        current.save()

        fake_response = mock.MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {"buildNumber": 222}

        with mock.patch.object(sde_tasks.httpx, "get", return_value=fake_response):
            self.assertFalse(sde_tasks.check_sde_version())

    def test_returns_true_when_build_number_matches(self):
        current = sde_tasks.EveSDE.get_solo()
        current.build_number = 333
        current.save()

        fake_response = mock.MagicMock()
        fake_response.raise_for_status.return_value = None
        fake_response.json.return_value = {"buildNumber": 333}

        with mock.patch.object(sde_tasks.httpx, "get", return_value=fake_response):
            self.assertTrue(sde_tasks.check_sde_version())


class DownloadExtractSdeTests(TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.zip_path = os.path.join(self.tmpdir, "sde.zip")
        self.extract_path = os.path.join(self.tmpdir, "sde-folder")

        for target in ("SDE_FILE_NAME", "SDE_FOLDER"):
            patcher = mock.patch.object(sde_tasks, target, self.zip_path if target
                                        == "SDE_FILE_NAME" else self.extract_path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_success_extracts_and_always_removes_zip(self):
        with zipfile.ZipFile(self.zip_path, "w") as zf:
            zf.writestr("_sde.jsonl", '{"buildNumber": 1}')

        with mock.patch.object(sde_tasks, "download_file"):
            sde_tasks.download_extract_sde()

        self.assertFalse(os.path.exists(self.zip_path))
        self.assertTrue(os.path.exists(os.path.join(self.extract_path, "_sde.jsonl")))

    def test_bad_zip_cleans_up_folder_and_zip_then_raises(self):
        with open(self.zip_path, "wb") as f:
            f.write(b"this is not a zip file")

        # simulate a leftover folder from a previous partial run
        os.makedirs(self.extract_path, exist_ok=True)
        with open(os.path.join(self.extract_path, "stale.txt"), "w") as f:
            f.write("leftover")

        with mock.patch.object(sde_tasks, "download_file"):
            with self.assertRaises(zipfile.BadZipFile):
                sde_tasks.download_extract_sde()

        self.assertFalse(os.path.exists(self.zip_path))
        self.assertFalse(os.path.exists(self.extract_path))

    def test_failed_download_never_reaches_zip_extraction(self):
        with mock.patch.object(sde_tasks, "download_file", side_effect=RuntimeError("download failed")):
            with self.assertRaises(RuntimeError):
                sde_tasks.download_extract_sde()

        # nothing was ever extracted, and there's nothing to clean up
        self.assertFalse(os.path.exists(self.extract_path))


class ProcessFromSdeTests(TestCase):

    def test_failure_partway_through_skips_version_but_still_cleans_up(self):
        model_a = mock.MagicMock()
        model_b = mock.MagicMock()
        model_b.load_from_sde.side_effect = RuntimeError("bad row")
        model_c = mock.MagicMock()

        with mock.patch.object(sde_tasks, "download_extract_sde"), \
                mock.patch.object(sde_tasks, "SDE_PARTS_TO_UPDATE", [model_a, model_b, model_c]), \
                mock.patch.object(sde_tasks, "set_sde_version") as mock_set_version, \
                mock.patch.object(sde_tasks, "delete_sde_folder") as mock_delete_folder:

            with self.assertRaises(RuntimeError):
                sde_tasks.process_from_sde()

            model_a.load_from_sde.assert_called_once()
            model_b.load_from_sde.assert_called_once()
            model_c.load_from_sde.assert_not_called()
            mock_set_version.assert_not_called()
            mock_delete_folder.assert_called_once()

    def test_success_sets_version_and_cleans_up(self):
        model_a = mock.MagicMock()
        model_b = mock.MagicMock()

        with mock.patch.object(sde_tasks, "download_extract_sde"), \
                mock.patch.object(sde_tasks, "SDE_PARTS_TO_UPDATE", [model_a, model_b]), \
                mock.patch.object(sde_tasks, "set_sde_version") as mock_set_version, \
                mock.patch.object(sde_tasks, "delete_sde_folder") as mock_delete_folder:

            sde_tasks.process_from_sde()

            model_a.load_from_sde.assert_called_once()
            model_b.load_from_sde.assert_called_once()
            mock_set_version.assert_called_once()
            mock_delete_folder.assert_called_once()

    def test_failed_download_extract_raises_without_touching_models(self):
        model_a = mock.MagicMock()

        with mock.patch.object(sde_tasks, "download_extract_sde", side_effect=RuntimeError("download failed")), \
                mock.patch.object(sde_tasks, "SDE_PARTS_TO_UPDATE", [model_a]), \
                mock.patch.object(sde_tasks, "set_sde_version") as mock_set_version, \
                mock.patch.object(sde_tasks, "delete_sde_folder") as mock_delete_folder:

            with self.assertRaises(RuntimeError):
                sde_tasks.process_from_sde()

            model_a.load_from_sde.assert_not_called()
            mock_set_version.assert_not_called()
            # download_extract_sde is responsible for its own cleanup on failure,
            # process_from_sde's finally block never runs because the exception
            # happens before entering the try.
            mock_delete_folder.assert_not_called()


class SetSdeVersionTests(TestCase):

    def test_missing_sde_file_raises(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)

        with mock.patch.object(sde_tasks, "SDE_FOLDER", tmpdir):
            with self.assertRaises(FileNotFoundError):
                sde_tasks.set_sde_version()

    def test_success_records_build_and_release_date(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        with open(os.path.join(tmpdir, "_sde.jsonl"), "w") as f:
            f.write('{"buildNumber": 3142455, "releaseDate": "2025-12-15T11:14:02Z"}')

        with mock.patch.object(sde_tasks, "SDE_FOLDER", tmpdir):
            sde_tasks.set_sde_version()

        current = sde_tasks.EveSDE.get_solo()
        self.assertEqual(current.build_number, 3142455)
        self.assertEqual(current.release_date.isoformat(), "2025-12-15T11:14:02+00:00")


class DeleteHelpersTests(TestCase):

    def test_delete_sde_zip_is_a_no_op_when_already_gone(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        missing = os.path.join(tmpdir, "does-not-exist.zip")

        with mock.patch.object(sde_tasks, "SDE_FILE_NAME", missing):
            sde_tasks.delete_sde_zip()  # must not raise

    def test_delete_sde_folder_is_a_no_op_when_already_gone(self):
        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        missing = os.path.join(tmpdir, "does-not-exist")

        with mock.patch.object(sde_tasks, "SDE_FOLDER", missing):
            sde_tasks.delete_sde_folder()  # must not raise


class ProcessFromSdeStartFromTests(TestCase):

    def test_start_from_skips_earlier_models(self):
        model_a = mock.MagicMock()
        model_b = mock.MagicMock()

        with mock.patch.object(sde_tasks, "download_extract_sde"), \
                mock.patch.object(sde_tasks, "SDE_PARTS_TO_UPDATE", [model_a, model_b]), \
                mock.patch.object(sde_tasks, "set_sde_version"), \
                mock.patch.object(sde_tasks, "delete_sde_folder"):

            sde_tasks.process_from_sde(start_from=1)

        model_a.load_from_sde.assert_not_called()
        model_b.load_from_sde.assert_called_once()
