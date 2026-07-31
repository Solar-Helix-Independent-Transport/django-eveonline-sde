"""
Tests for the Celery task wiring in tasks.py: retry/backoff configuration on
the network-touching tasks, and the split-chain error callback that cleans up
a partial SDE folder if any section in the chain fails.

Tasks are invoked directly (not via .delay()/.apply_async()) so these run
without a broker - QueueOnce's locking only engages through apply_async, so
calling a bound task directly just executes its body synchronously.
"""
# Standard Library
from unittest import mock

# Third Party
import httpx

# Django
from django.test import TestCase

# Django EVE SDE
from eve_sde import tasks as celery_tasks


class RetryConfigTests(TestCase):

    def test_network_touching_tasks_retry_on_http_errors_with_backoff(self):
        for task in (
            celery_tasks.check_for_sde_updates,
            celery_tasks.update_models_from_sde,
            celery_tasks.fetch_sde,
        ):
            self.assertIn(httpx.HTTPError, task.autoretry_for)
            self.assertEqual(task.max_retries, 5)
            self.assertTrue(task.retry_backoff)

    def test_non_network_tasks_do_not_autoretry(self):
        # process_sde_section/cleanup_sde touch the DB/filesystem, not the
        # network - a bad row shouldn't be silently retried.
        for task in (celery_tasks.process_sde_section, celery_tasks.cleanup_sde):
            self.assertFalse(getattr(task, "autoretry_for", ()))


class CheckForSdeUpdatesTests(TestCase):

    def test_queues_update_when_out_of_date(self):
        with mock.patch.object(celery_tasks, "check_sde_version", return_value=False), \
                mock.patch.object(celery_tasks, "update_models_from_sde") as mock_update:
            celery_tasks.check_for_sde_updates()

        mock_update.delay.assert_called_once()

    def test_does_not_queue_update_when_already_current(self):
        with mock.patch.object(celery_tasks, "check_sde_version", return_value=True), \
                mock.patch.object(celery_tasks, "update_models_from_sde") as mock_update:
            celery_tasks.check_for_sde_updates()

        mock_update.delay.assert_not_called()


class UpdateModelsFromSdeTests(TestCase):

    def test_non_split_mode_calls_process_from_sde_directly(self):
        with mock.patch.object(celery_tasks, "ESDE_TASK_SPLIT", False), \
                mock.patch.object(celery_tasks, "process_from_sde") as mock_process, \
                mock.patch.object(celery_tasks, "chain") as mock_chain:
            celery_tasks.update_models_from_sde()

        mock_process.assert_called_once()
        mock_chain.assert_not_called()

    def test_split_mode_builds_chain_wired_to_the_error_callback(self):
        fake_chain_instance = mock.MagicMock()

        with mock.patch.object(celery_tasks, "ESDE_TASK_SPLIT", True), \
                mock.patch.object(celery_tasks, "chain", return_value=fake_chain_instance) as mock_chain:
            celery_tasks.update_models_from_sde()

        mock_chain.assert_called_once()
        (queue_arg,), _ = mock_chain.call_args
        # fetch_sde + one process_sde_section per model + cleanup_sde
        self.assertEqual(len(queue_arg), len(celery_tasks.SDE_PARTS_TO_UPDATE) + 2)

        fake_chain_instance.apply_async.assert_called_once()
        _, apply_kwargs = fake_chain_instance.apply_async.call_args
        self.assertIn("link_error", apply_kwargs)
        self.assertEqual(apply_kwargs["link_error"].task, celery_tasks.cleanup_sde_after_failure.name)


class TaskDelegationTests(TestCase):
    """The remaining tasks are thin wrappers - confirm each delegates to the
    right underlying function rather than duplicating its logic."""

    def test_process_sde_section_delegates_with_id(self):
        with mock.patch.object(celery_tasks, "process_section_of_sde") as mock_process:
            celery_tasks.process_sde_section(3)

        mock_process.assert_called_once_with(3)

    def test_fetch_sde_delegates_to_download_extract_sde(self):
        with mock.patch.object(celery_tasks, "download_extract_sde") as mock_download:
            celery_tasks.fetch_sde()

        mock_download.assert_called_once()

    def test_cleanup_sde_sets_version_then_deletes_folder(self):
        with mock.patch.object(celery_tasks, "set_sde_version") as mock_set_version, \
                mock.patch.object(celery_tasks, "delete_sde_folder") as mock_delete_folder:
            celery_tasks.cleanup_sde()

        mock_set_version.assert_called_once()
        mock_delete_folder.assert_called_once()


class CleanupSdeAfterFailureTests(TestCase):

    def test_deletes_folder_regardless_of_the_args_celery_passes_in(self):
        # Celery invokes link_error callbacks with the failed task's id, not
        # the exception - the callback must tolerate arbitrary positional
        # arguments rather than assuming a specific signature.
        with mock.patch.object(celery_tasks, "delete_sde_folder") as mock_delete:
            celery_tasks.cleanup_sde_after_failure("some-failed-task-id")

        mock_delete.assert_called_once()


class ResolveTaskLockBaseTests(TestCase):
    """
    _resolve_task_lock_base is what keeps QueueOnce from being a hard
    AllianceAuth dependency: the default setting points at AllianceAuth's
    thin wrapper, but if that can't be imported (AllianceAuth not
    installed), it must fall back to celery_once.QueueOnce directly with
    the same graceful=True behavior rather than crashing.
    """

    def test_resolves_the_configured_default(self):
        # Alliance Auth
        from allianceauth.services.tasks import QueueOnce as AllianceAuthQueueOnce

        self.assertIs(celery_tasks._resolve_task_lock_base(), AllianceAuthQueueOnce)

    def test_falls_back_to_celery_once_when_the_configured_path_is_unimportable(self):
        # Third Party
        from celery_once import QueueOnce as UpstreamQueueOnce

        with mock.patch.object(
            celery_tasks, "ESDE_CELERY_TASK_BASE", "not_an_installed_package.services.tasks.QueueOnce",
        ):
            fallback_base = celery_tasks._resolve_task_lock_base()

        self.assertTrue(issubclass(fallback_base, UpstreamQueueOnce))
        self.assertEqual(fallback_base.once["graceful"], True)
