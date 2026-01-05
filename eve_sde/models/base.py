# Standard Library
import json
import logging

# Django
from django.db import models

from .utils import get_langs, get_langs_for_field, lang_key, val_from_dict

logger = logging.getLogger(__name__)


class JSONModel(models.Model):
    class Import:
        filename = "not_set.jsonl"
        data_map = False
        lang_fields = False
        custom_names = False
        update_fields = False

    @classmethod
    def from_jsonl(cls, json_data, name_lookup=False):
        if cls.Import.data_map:
            _model = cls(id=val_from_dict("_key", json_data))
            for f, k in cls.Import.data_map:
                setattr(_model, f, val_from_dict(k, json_data))
            # if cls.Import.lang_fields:
            #     for _f in cls.Import.lang_fields:
            #         for lang, _val in json_data.get(_f, {}).items():
            #             setattr(_model, f"{_f}_{lang_key(lang)}", _val)
            if cls.Import.custom_names:
                setattr(_model, f"name", cls.format_name(json_data, name_lookup))

            return _model

        else:
            raise AttributeError("Not Implemented")

    @classmethod
    def name_lookup(cls):
        return False

    @classmethod
    def format_name(cls, data, name_lookup):
        return data.get("name")

    @classmethod
    def create_update(cls, create_model_list: list["JSONModel"], update_model_list: list["JSONModel"]):
        cls.objects.bulk_create(
            create_model_list,
            # ignore_conflicts=True,
            batch_size=500
        )

        if cls.Import.update_fields:
            cls.objects.bulk_update(
                update_model_list,
                cls.Import.update_fields,
                batch_size=500
            )
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
            while line := json_file.readline():
                rg = json.loads(line)
                _new = cls.from_jsonl(rg, name_lookup)
                if isinstance(_new, list):
                    if pks:
                        for _i in _new:
                            if _i.pk in pks:
                                _updates.append(_new)
                            else:
                                _creates.append(_new)
                    else:
                        _creates += _new
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
                        f"{file_path} - {int(total_read / total_lines * 100)}%"
                        f" - {total_read}/{total_lines} Lines - "
                        f"New: {len(_creates)} - Updates: {len(_updates)}"
                    )
                    cls.create_update(_creates, _updates)
                    _creates = []
                    _updates = []

            # create/update any that are left.
            logger.info(
                f"{file_path} - {int(total_read / total_lines * 100)}%"
                f" - {total_read}/{total_lines} Lines - "
                f"New: {len(_creates)} - Updates: {len(_updates)}"
            )
            cls.create_update(_creates, _updates)

        _complete = cls.objects.all().count()
        if _complete != total_lines:
            logger.warning(
                f"{file_path} - Found {_complete}/{total_lines} items after completing import."
            )

    class Meta:
        abstract = True
        default_permissions = ()
