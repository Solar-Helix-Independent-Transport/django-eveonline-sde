# Standard Library
import logging
import operator
from functools import reduce

# Third Party
import polib

# Django
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


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


def val_from_dict(key, dict):
    _k = key
    _d = None
    if isinstance(key, tuple):
        _k = key[0]
        _d = key[1]
    try:
        return reduce(operator.getitem, _k.split("."), dict)
    except KeyError:
        return _d


def update_po_file(data: dict, file: str):
    base = settings.LOCALE_PATHS[0]
    try:
        for lang, trans in data.items():
            file_name = f"{base}{lang}/LC_MESSAGES/django.po"
            with open(file_name, "a") as f:
                for d in trans:
                    try:
                        entry = polib.POEntry(
                            msgid=d["k"],
                            msgstr=d["v"],
                            occurrences=[(file, d["l"])]
                        )
                        f.write(entry.__unicode__())
                    except Exception as e:
                        logger.exception(e)
    except Exception as e:
        logger.exception(e)


def chunked_queryset(qs, batch_size=1000, index='id'):
    """
    Yields a queryset that will be evaluated in batches
    """
    qs = qs.order_by()  # clear ordering
    min_max = qs.aggregate(min=models.Min(index), max=models.Max(index))
    min_id, max_id = min_max['min'], min_max['max']
    for i in range(min_id, max_id + 1, batch_size):
        filter_args = {f'{index}__range': (i, i + batch_size - 1)}
        yield from qs.filter(**filter_args)
