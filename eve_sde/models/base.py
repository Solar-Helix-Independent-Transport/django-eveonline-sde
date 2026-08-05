# Standard Library
import json
import logging
from datetime import datetime, timezone
from functools import reduce

# Third Party
import httpx

# Django
from django.db import models
from django.utils.translation import gettext as _

# Django EVE SDE
from eve_sde.app_settings import ESDE_BATCH_SIZE, ESDE_CHUNK_SIZE
from eve_sde.models.admin import EveSDESection
from eve_sde.models.utils import get_langs, get_langs_for_field, lang_key, val_from_dict

logger = logging.getLogger(__name__)


class JSONModel(models.Model):
    class Import:
        filename = "not_set.jsonl"
        data_map = False
        lang_fields = False
        custom_names = False
        update_fields = False
        extra_data = False

    @classmethod
    def map_to_model(cls, json_data, name_lookup=False, pk=True):
        _model = cls()
        if pk:
            _model.pk = val_from_dict("_key", json_data)
        for f, k in cls.Import.data_map:
            setattr(_model, f, val_from_dict(k, json_data))
        if cls.Import.lang_fields:
            for _f in cls.Import.lang_fields:
                _fld = _f
                _key = _f
                if isinstance(_f, tuple):
                    _fld, _key = _f
                for lang, _val in json_data.get(_key, {}).items():
                    setattr(_model, f"{_fld}_{lang_key(lang)}", _val)
        if cls.Import.custom_names:
            setattr(_model, "name", cls.format_name(json_data, name_lookup, "en"))
            for lang in get_langs():
                _nme = cls.format_name(json_data, name_lookup, lang=lang_key(lang))
                if _model.name != _nme:
                    setattr(_model, f"name_{lang_key(lang)}", _nme)

        return _model

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        if cls.Import.data_map:
            return cls.map_to_model(json_data, name_lookup=name_lookup, pk=True)
        else:
            raise AttributeError("Not Implemented")

    @property
    def localized_name(self):
        return f"{_(self.name)}"

    @classmethod
    def name_lookup(cls):
        return False

    @classmethod
    def load_extra(cls):
        if hasattr(cls.Import, "extra_data") and cls.Import.extra_data:
            output = {}
            for url, parser, fields in cls.Import.extra_data:
                logger.info(f"Loading extra data from {url} for {cls.__name__}")
                try:
                    r = httpx.get(url)
                    if r.status_code == 200:
                        data = r.json()
                        if parser == "id_dict":
                            for item_id, value in data.items():
                                id = int(item_id)
                                if id not in output:
                                    output[id] = {}
                                for f in fields:
                                    output[id][f] = value
                    else:
                        logger.error(
                            f"Failed to load extra data from {url} for {cls.__name__}. Status code: {r.status_code}")
                except Exception as e:
                    logger.error(f"Error loading extra data from {url} for {cls.__name__}: {e}")
            return output
        return False

    @classmethod
    def format_name(cls, data, name_lookup, lang: str = False):
        if not lang:
            return data.get("name")
        else:
            return data.get(f"name_{lang}")

    @classmethod
    def get_data_fields(cls):
        _fields = [_f[0] for _f in cls.Import.data_map]
        if cls.Import.lang_fields:
            for _f in cls.Import.lang_fields:
                _fld = _f
                if isinstance(_f, tuple):
                    _fld, _key = _f
                _fields += get_langs_for_field(_fld)
        if cls.Import.custom_names:
            _fields += get_langs_for_field("name")
        return _fields

    @classmethod
    def create_update(cls, create_model_list: list["JSONModel"], update_model_list: list["JSONModel"]):
        # logger.debug(f"{cls} - Creates ({len(create_model_list)})")
        cls.objects.bulk_create(
            create_model_list,
            # ignore_conflicts=True,
            batch_size=ESDE_BATCH_SIZE
        )

        if len(update_model_list):
            _e = cls.objects.filter(pk__in=[_i.pk for _i in update_model_list])
            _checks = {}
            for _i in _e:
                _checks[_i.pk] = _i
            update_model_list = [_s for _s in update_model_list if not cls.is_equal(_s, _checks[_s.pk])]
            if len(update_model_list) > 0:
                if cls.Import.update_fields:
                    # logger.debug(f"{cls} - updates ({len(update_model_list)})")
                    cls.objects.bulk_update(
                        update_model_list,
                        cls.Import.update_fields,
                        batch_size=ESDE_BATCH_SIZE
                    )
                elif cls.Import.data_map:
                    # logger.debug(f"{cls} - data_map updates ({len(update_model_list)})")
                    _fields = cls.get_data_fields()
                    cls.objects.bulk_update(
                        update_model_list,
                        _fields,
                        batch_size=ESDE_BATCH_SIZE
                    )
        # logger.debug(f"{cls} - Done")

    @classmethod
    def is_equal(cls, new, old):
        if cls.Import.update_fields:
            for f in cls.Import.update_fields:
                if getattr(new, f) != getattr(old, f):
                    return False
        elif cls.Import.data_map:
            # logger.debug(f"{cls} - data_map updates ({len(update_model_list)})")
            _fields = cls.get_data_fields()
            for f in _fields:
                if getattr(new, f) != getattr(old, f):
                    return False
        return True

    @classmethod
    def load_from_sde(cls, folder_name):
        _creates = []
        _updates = []

        name_lookup = cls.name_lookup()
        extra_fields = cls.load_extra()

        pks = set(
            cls.objects.all().values_list("pk", flat=True)
        )  # if cls.Import.update_fields else False

        file_path = f"{folder_name}/{cls.Import.filename}"

        total_lines = 0
        with open(file_path) as json_file:
            while _ := json_file.readline():
                total_lines += 1

        total_read = 0
        with open(file_path) as json_file:
            row = 0
            while line := json_file.readline():
                row += 1
                try:
                    rg = json.loads(line)
                    if extra_fields:
                        if rg.get("_key") in extra_fields:
                            for f, v in extra_fields[rg.get("_key")].items():
                                rg[f] = v
                    _new = cls.from_jsonl(rg, name_lookup)
                except Exception:
                    logger.exception(f"{file_path} - Skipping malformed row {row}")
                    continue

                if isinstance(_new, list):
                    if pks:
                        for _i in _new:
                            if _i.pk in pks:
                                _updates.append(_i)
                            else:
                                _creates.append(_i)
                            total_read += 1
                    else:
                        _creates += _new
                        total_read += len(_new)
                else:
                    if pks:
                        if _new.pk in pks:
                            _updates.append(_new)
                        else:
                            _creates.append(_new)
                    else:
                        _creates.append(_new)
                    total_read += 1

                if (len(_creates) + len(_updates)) >= ESDE_CHUNK_SIZE:
                    # lets batch these to reduce memory overhead
                    logger.info(
                        f"{file_path} - "
                        f"{total_read} Models from {row}/{total_lines} Lines - "
                        f"New: {len(_creates)} - Updates: {len(_updates)}"
                    )
                    cls.create_update(_creates, _updates)
                    _creates = []
                    _updates = []
            # create/update any that are left.
            logger.info(
                f"{file_path} - "
                f"{total_read} Models from {row}/{total_lines} Lines - "
                f"New: {len(_creates)} - Updates: {len(_updates)}"
            )
            cls.create_update(_creates, _updates)

        _complete = cls.objects.all().count()
        if _complete != total_lines and _complete != total_read:
            logger.warning(
                f"{file_path} - Found {_complete}/{total_lines if _complete == total_lines else total_read} items after completing import."
            )

        cls.update_sde_section_state(
            folder_name,
            cls.__name__,
            total_lines if _complete == total_lines else total_read, _complete
        )

    @classmethod
    def update_sde_section_state(cls, folder_name: str, section: str, total_lines: int, total_rows: int):
        build = 0
        last_update = datetime.now(tz=timezone.utc)
        try:
            with open(f"{folder_name}/_sde.jsonl") as json_file:
                sde_data = json.loads(json_file.read())
                build = sde_data.get("buildNumber", 0)
        except Exception:
            logger.exception(f"Failed to read SDE version from {folder_name}/_sde.jsonl")
            raise

        EveSDESection.objects.update_or_create(
            sde_section=section,
            defaults={
                "build_number": build,
                "last_update": last_update,
                "total_lines": total_lines,
                "total_rows": total_rows
            }
        )

    class Meta:
        abstract = True
        default_permissions = ()
