# Django
from django.conf import settings


def lang_key(key):
    keys = {
        "fr": "fr_fr",
        "ko": "ko_kr",
        "zh": "zh_hans",
    }
    return keys[key] if key in keys else key


def key_to_lang(lang):
    langs = {
        "fr_fr": "fr",
        "ko_kr": "ko",
        "zh_hans": "zh",
    }
    return langs[lang] if lang in langs else lang


def to_roman_numeral(num):
    lookup = [
        (50, 'L'),
        (40, 'XL'),
        (10, 'X'),
        (9, 'IX'),
        (5, 'V'),
        (4, 'IV'),
        (1, 'I'),
    ]
    res = ''
    for (n, roman) in lookup:
        (d, num) = divmod(num, n)
        res += roman * d
    return res


def get_langs():
    try:
        return [i[0].replace("-", "_") for i in settings.LANGUAGES]
    except AttributeError:
        return []


def get_langs_for_field(field_name):
    out = []
    for _l in get_langs():
        out.append(f"{field_name}_{_l}")
    return out
