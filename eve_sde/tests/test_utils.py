"""Tests for the small standalone helpers in models/utils.py."""
# Standard Library
import importlib
from unittest import mock

# Django
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings

# Django EVE SDE
from eve_sde import app_settings
from eve_sde.models.utils import get_langs, key_to_lang, lang_key


class KeyToLangTests(TestCase):

    def test_maps_known_suffixed_codes_back_to_their_short_form(self):
        self.assertEqual(key_to_lang("fr_fr"), "fr")
        self.assertEqual(key_to_lang("ko_kr"), "ko")
        self.assertEqual(key_to_lang("zh_hans"), "zh")

    def test_passes_through_unmapped_codes_unchanged(self):
        self.assertEqual(key_to_lang("de"), "de")


class LangKeyTests(TestCase):

    def test_maps_known_short_codes_to_their_suffixed_form(self):
        self.assertEqual(lang_key("fr"), "fr_fr")
        self.assertEqual(lang_key("ko"), "ko_kr")
        self.assertEqual(lang_key("zh"), "zh_hans")

    def test_passes_through_unmapped_codes_unchanged(self):
        self.assertEqual(lang_key("de"), "de")


class GetLangsTests(TestCase):

    def test_returns_empty_list_when_languages_setting_is_absent(self):
        with mock.patch("eve_sde.models.utils.settings", new=object()):
            self.assertEqual(get_langs(), [])


class EsdeSourceSettingTests(SimpleTestCase):

    def tearDown(self):
        importlib.reload(app_settings)

    def test_is_case_insensitive(self):
        with override_settings(ESDE_SOURCE="REST"):
            importlib.reload(app_settings)

        self.assertEqual(app_settings.ESDE_SOURCE, "rest")

    def test_unknown_source_is_refused(self):
        with override_settings(ESDE_SOURCE="api"), self.assertRaises(ImproperlyConfigured):
            importlib.reload(app_settings)
