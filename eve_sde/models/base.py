# Standard Library
import json
import logging
import time
from datetime import datetime, timezone

# Django
from django.db import models
from django.utils.translation import gettext as _

# AA Example App
from eve_sde.models.utils import get_langs

from .admin import EveSDESection
from .utils import lang_key, update_po_file, val_from_dict

logger = logging.getLogger(__name__)


class JSONModel(models.Model):
    class Import:
        filename = "not_set.jsonl"
        data_map = False
        lang_fields = False
        custom_names = False
        update_fields = False

    @classmethod
    def map_to_model(cls, json_data, name_lookup=False, pk=True, line: int = 0):
        _model = cls()
        _trans = []
        if pk:
            _model.pk = val_from_dict("_key", json_data)
        for f, k in cls.Import.data_map:
            setattr(_model, f, val_from_dict(k, json_data))
        if cls.Import.lang_fields:
            for _f in cls.Import.lang_fields:
                for lang, _val in json_data.get(_f, {}).items():
                    _trans.append(
                        {
                            "lang": lang_key(lang),
                            "k": val_from_dict(f"{_f}.en", json_data),
                            "v": _val,
                            "l": line
                        }
                    )
        if cls.Import.custom_names:
            setattr(_model, f"name", cls.format_name(json_data, name_lookup))

        return _model, _trans

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False, line: int = 0):
        if cls.Import.data_map:
            return cls.map_to_model(json_data, name_lookup=name_lookup, pk=True, line=line)
        else:
            raise AttributeError("Not Implemented")

    @property
    def localized_name(self):
        return f"{_(self.name)}"

    @classmethod
    def name_lookup(cls):
        return False

    @classmethod
    def format_name(cls, data, name_lookup):
        return data.get("name")

    @classmethod
    def create_update(cls, create_model_list: list["JSONModel"], update_model_list: list["JSONModel"], langs: list[dict]):
        start = time.perf_counter()
        cls.objects.bulk_create(
            create_model_list,
            # ignore_conflicts=True,
            batch_size=500
        )
        logger.info(f"{cls.Import.filename} - create_update DB Create - {time.perf_counter() - start:,.2f}s")
        start = time.perf_counter()
        if cls.Import.update_fields:
            cls.objects.bulk_update(
                update_model_list,
                cls.Import.update_fields,
                batch_size=500
            )
            logger.info(f"{cls.Import.filename} - create_update DB Update - {time.perf_counter() - start:,.2f}s")
            start = time.perf_counter()

        elif cls.Import.data_map:
            _fields = [_f[0] for _f in cls.Import.data_map]
            # if cls.Import.lang_fields:
            #     for _f in cls.Import.lang_fields:
            #         _fields += get_langs_for_field(_f)
            cls.objects.bulk_update(
                update_model_list,
                _fields,
                batch_size=500
            )
            logger.info(f"{cls.Import.filename} - create_update DB Update - {time.perf_counter() - start:,.2f}s")
            start = time.perf_counter()

        if cls.Import.lang_fields:
            update_po_file(langs, cls.Import.filename)
            logger.info(f"{cls.Import.filename} - create_update Translate - {time.perf_counter() - start:,.2f}s")
            start = time.perf_counter()

    @classmethod
    def _build_trans_cache(cls):
        _trans_cache = {}
        for l in get_langs():
            _trans_cache[l] = []
        return _trans_cache

    @classmethod
    def load_from_sde(cls, folder_name):
        _creates = []
        _updates = []

        name_lookup = cls.name_lookup()

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
            _trans_cache = cls._build_trans_cache()

            while line := json_file.readline():
                row += 1
                rg = json.loads(line)
                _new, _langs = cls.from_jsonl(rg, name_lookup, row)
                if cls.Import.lang_fields:
                    for f in _langs:
                        _l = f.pop("lang", False)
                        if _l:
                            _trans_cache[_l].append(f)
                if isinstance(_new, list):
                    if pks:
                        for _i in _new:
                            if _i.pk in pks:
                                _updates.append(_new)
                            else:
                                _creates.append(_new)
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

                if (len(_creates) + len(_updates)) >= 5000:
                    # lets batch these to reduce memory overhead
                    logger.info(
                        f"{file_path} - "
                        f"{total_read} Models from {row}/{total_lines} Lines - "
                        f"New: {len(_creates)} - Updates: {len(_updates)}"
                    )
                    cls.create_update(_creates, _updates, _trans_cache)
                    _creates = []
                    _updates = []
                    _trans_cache = cls._build_trans_cache()

            # create/update any that are left.
            logger.info(
                f"{file_path} - "
                f"{total_read} Models from {row}/{total_lines} Lines - "
                f"New: {len(_creates)} - Updates: {len(_updates)}"
            )
            cls.create_update(_creates, _updates, _trans_cache)

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
        with open(f"{folder_name}/_sde.jsonl") as json_file:
            sde_data = json.loads(json_file.read())
            build = sde_data.get("buildNumber", 0)

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
