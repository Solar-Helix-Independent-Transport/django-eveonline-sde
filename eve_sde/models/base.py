# Standard Library
import hashlib
import json
import logging
from datetime import datetime, timezone
from functools import reduce

# Third Party
import httpx

# Django
from django.db import connections, models, router
from django.db.models.base import ModelState
from django.utils import translation
from django.utils.translation import gettext as _

# Django EVE SDE
from eve_sde.app_settings import ESDE_BATCH_SIZE, ESDE_CHUNK_SIZE
from eve_sde.models.admin import EveSDESection
from eve_sde.models.utils import get_langs, get_langs_for_field, lang_key, val_from_dict

logger = logging.getLogger(__name__)

# SDE changes feed operations, ROW ones list the changed _keys, FILE ones are true
ROW_CHANGE_OPS = ("added", "changed", "removed", "changedLocalization")
FILE_CHANGE_OPS = ("schemaChanged", "fileAdded", "fileRemoved", "fileRenamed")

# Rows fetched per query when comparing existing rows, keeps under DB parameter limits.
COMPARE_CHUNK_SIZE = 2000

# Per model (default __dict__, attnames with callable defaults), see JSONModel.new_instance
_INSTANCE_TEMPLATES = {}


class JSONModel(models.Model):
    class Import:
        filename = "not_set.jsonl"
        data_map = False
        lang_fields = False
        custom_names = False
        update_fields = False
        extra_data = False
        field_filters = ()
        natural_key = False
        # Other SDE files this model reads while importing, so a change to them
        # reloads this model too (see change_reason). Each entry is a file key
        # ("mapSolarSystems": any change), or (file key, {"ids": {...}}) for
        # changes to those rows only, or (file key, {"ops": {...}}) for those
        # change operations only, e.g. {"ops": {"added", "removed"}}.
        depends_on = ()
        # Bump when the import logic changes in a way the Import config above
        # doesn't show, so the next update reloads this model.
        version = 0

    @classmethod
    def new_instance(cls):
        """
        A fresh unsaved instance with every field at its default, without
        running Model.__init__ (slow with modeltranslation, which resolves a
        default per translated field per language).

        Clones the __dict__ of one real cls() instance. Fields with a callable
        default (e.g. JSONField(default=list)) get a fresh value each time so
        instances never share a mutable default.
        """
        template = _INSTANCE_TEMPLATES.get(cls)
        if template is None:
            _base = {k: v for k, v in cls().__dict__.items() if k != "_state"}
            _callables = [
                f for f in cls._meta.concrete_fields
                # NOT_PROVIDED is a class, so callable() alone is True for no default
                if f.has_default() and callable(f.default)
            ]
            template = _INSTANCE_TEMPLATES[cls] = (_base, _callables)
        _base, _callables = template
        _model = cls.__new__(cls)
        _model.__dict__.update(_base)
        for f in _callables:
            _model.__dict__[f.attname] = f.get_default()
        _model._state = ModelState()
        return _model

    @classmethod
    def map_to_model(cls, json_data, name_lookup=False, pk=True):
        _model = cls.new_instance()
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
                # raw value, the descriptor walks the language fallbacks
                if _model.__dict__["name"] != _nme:
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
    def load_filters(cls) -> dict[str, set]:
        if hasattr(cls.Import, "field_filters") and cls.Import.field_filters:
            output = {}
            for field_name, function in cls.Import.field_filters:
                output[field_name] = set(function())

            return output
        return {}

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
                # the untranslated base column too, not only name_en/name_de/...
                _fields += [_fld] + get_langs_for_field(_fld)
        if cls.Import.custom_names:
            _fields += ["name"] + get_langs_for_field("name")
        return list(dict.fromkeys(_fields))

    @classmethod
    def compare_fields(cls):
        """Fields compared, and written, when an existing row is updated."""
        _fields = cls.Import.update_fields or (cls.get_data_fields() if cls.Import.data_map else [])
        _pk = cls._meta.pk
        # rows are matched by pk, and the pk can't be in an upsert's update_fields
        return [f for f in _fields if f not in (_pk.name, _pk.attname)]

    @classmethod
    def existing_values(cls, pks, fields):
        """{pk: (field values...)} straight from the DB, no model instances."""
        qs = cls._base_manager.all()
        if hasattr(qs, "rewrite"):
            # modeltranslation would otherwise read name_en when asked for name
            qs = qs.rewrite(False)
        out = {}
        for i in range(0, len(pks), COMPARE_CHUNK_SIZE):
            for row in qs.filter(pk__in=pks[i:i + COMPARE_CHUNK_SIZE]).values_list("pk", *fields):
                out[row[0]] = row[1:]
        return out

    @classmethod
    def changed_models(cls, update_model_list):
        """The subset of update_model_list that differs from what is stored."""
        fields = cls.compare_fields()
        if not fields:
            return []
        existing = cls.existing_values([_m.pk for _m in update_model_list], fields)
        # getattr is what saving writes: a translated base field (e.g. a
        # display_name only set via lang_fields) is saved as its _en value
        return [
            _m for _m in update_model_list
            if tuple(getattr(_m, f) for f in fields) != existing.get(_m.pk)
        ]

    @classmethod
    def create_update(cls, create_model_list: list["JSONModel"], update_model_list: list["JSONModel"]):
        cls.objects.bulk_create(
            create_model_list,
            batch_size=ESDE_BATCH_SIZE
        )

        if not update_model_list:
            return
        changed = cls.changed_models(update_model_list)
        if not changed:
            return
        # upsert, a plain INSERT per batch is far faster than bulk_update's CASE WHEN
        upsert = {"update_conflicts": True, "update_fields": cls.compare_fields()}
        if connections[router.db_for_write(cls)].features.supports_update_conflicts_with_target:
            # required by SQLite/PostgreSQL, MySQL raises if it's passed
            upsert["unique_fields"] = [cls._meta.pk.name]
        cls.objects.bulk_create(
            changed,
            batch_size=ESDE_BATCH_SIZE,
            **upsert
        )

    @classmethod
    def load_from_sde(cls, folder_name):
        # setting a translated field (e.g. name) also sets it for the active
        # language, so pin English for the whole import whatever the worker's
        # LANGUAGE_CODE is. lang_fields then fills every other language.
        with translation.override("en"):
            cls._load_from_sde(folder_name)

    @classmethod
    def _load_from_sde(cls, folder_name):
        _creates = []
        _updates = []

        name_lookup = cls.name_lookup()
        extra_fields = cls.load_extra()
        filter_fields = cls.load_filters()

        pks = set(
            cls.objects.all().values_list("pk", flat=True)
        )  # if cls.Import.update_fields else False

        natural_key = cls.natural_key_fields()
        if natural_key:
            # match incoming rows to existing ones by their data, not their pk
            existing_keys = {
                tuple(_r[:-1]): _r[-1] for _r in cls.objects.values_list(*natural_key, "pk")
            }
            seen_keys = set()

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
                    if filter_fields:
                        filtered = False
                        for field_name, allowed_values in filter_fields.items():
                            if rg.get(field_name) not in allowed_values:
                                filtered = True
                                break
                        if filtered:
                            continue
                    _new = cls.from_jsonl(rg, name_lookup)
                except Exception:
                    logger.exception(f"{file_path} - Skipping malformed row {row}")
                    continue

                if natural_key:
                    for _i in (_new if isinstance(_new, list) else [_new]):
                        _nk = tuple(getattr(_i, f) for f in natural_key)
                        if None in _nk:
                            # can't be matched, so it's recreated each import
                            logger.info(f"{file_path} - Row {row} missing natural key {natural_key}: {_nk}")
                            _creates.append(_i)
                        elif _nk in seen_keys:
                            logger.warning(f"{file_path} - Row {row} duplicate natural key {natural_key}: {_nk}")
                            continue
                        elif _nk in existing_keys:
                            _i.pk = existing_keys[_nk]
                            _updates.append(_i)
                        else:
                            _creates.append(_i)
                        seen_keys.add(_nk)
                        total_read += 1
                elif isinstance(_new, list):
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

        if natural_key:
            cls.delete_stale(existing_keys, seen_keys)

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
    def sde_file_key(cls):
        """The key CCP uses for this model's file in the SDE changes feed."""
        return cls.Import.filename.removesuffix(".jsonl")

    @classmethod
    def import_fingerprint(cls):
        """
        Hash of what decides how this model is imported. Stored with each
        section, a mismatch (new fields, languages or Import config) means the
        stored rows predate this code and the model is reloaded in full.
        """
        _i = cls.Import

        def _stable(_v):
            if isinstance(_v, dict):
                return sorted((k, _stable(v)) for k, v in _v.items())
            if isinstance(_v, (set, frozenset)):
                return sorted(_stable(v) for v in _v)
            if isinstance(_v, (list, tuple)):
                return [_stable(v) for v in _v]
            return _v

        parts = [
            [f.attname for f in cls._meta.concrete_fields],
            get_langs(),
            [_f[0] for _f in (getattr(_i, "field_filters", None) or ())],
        ]
        for attr in (
            "filename", "data_map", "lang_fields", "custom_names", "update_fields",
            "extra_data", "natural_key", "depends_on", "version",
        ):
            parts.append(_stable(getattr(_i, attr, None)))
        return hashlib.sha256(repr(parts).encode()).hexdigest()[:32]

    @classmethod
    def change_reason(cls, changes: dict):
        """
        Why this model needs reloading for these SDE changes, or None.

        `changes` is {file key: {"ops": {operation, ...}, "ids": {_key, ...}}},
        merged over every build since this model was last loaded.
        """
        if getattr(cls.Import, "extra_data", False):
            return "loads extra data from outside the SDE"

        own = changes.get(cls.sde_file_key())
        if own:
            ops = own["ops"]
            if "fileRemoved" in ops:
                # loading would fail on the missing file, this needs a code change
                logger.error(f"{cls.__name__} - {cls.Import.filename} was removed from the SDE, not reloading")
                return None
            if "schemaChanged" in ops:
                logger.warning(f"{cls.__name__} - {cls.Import.filename} schema changed, check the Import config")
            return f"{cls.sde_file_key()} {', '.join(sorted(ops))}"

        for dep in getattr(cls.Import, "depends_on", ()):
            key, match = (dep, {}) if isinstance(dep, str) else dep
            change = changes.get(key)
            if not change:
                continue
            if "ids" in match and not (
                change["ids"] & set(match["ids"]) or change["ops"] & set(FILE_CHANGE_OPS)
            ):
                continue
            if "ops" in match and not change["ops"] & set(match["ops"]):
                continue
            return f"depends on {key}"
        return None

    @classmethod
    def natural_key_fields(cls):
        return getattr(cls.Import, "natural_key", False)

    @classmethod
    def delete_stale(cls, existing_keys: dict, seen_keys: set):
        """Delete rows that were in the DB but are no longer in the SDE."""
        stale = [_pk for _nk, _pk in existing_keys.items() if _nk not in seen_keys or None in _nk]
        if stale:
            logger.info(f"{cls.__name__} - Removing {len(stale)} rows no longer in the SDE")
        for i in range(0, len(stale), ESDE_BATCH_SIZE):
            cls.objects.filter(pk__in=stale[i:i + ESDE_BATCH_SIZE]).delete()

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
                "total_rows": total_rows,
                "import_fingerprint": cls.import_fingerprint(),
            }
        )

    class Meta:
        abstract = True
        default_permissions = ()
