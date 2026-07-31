"""Tests for the small standalone helpers in models/utils.py."""
# Standard Library
from unittest import mock

# Django
from django.test import TestCase

# Django EVE SDE
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
