"""
Test settings
"""

# flake8: noqa

########################################################
# local.py settings
# Every setting in base.py can be overloaded by redefining it here.

from .base import *

PACKAGE = "eve_sde"

DEBUG = False
LOGGING = False

# Opt-in MySQL/MariaDB backend, used by CI (the test matrix and the SDE
# load-test workflow) to catch column-range/length issues (e.g. INT overflow,
# VARCHAR truncation) that sqlite doesn't enforce. Off by default so local
# runs keep using sqlite.
if os.environ.get("USE_MYSQL", "False") == "True":
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "tox_allianceauth"),
        "USER": os.environ.get("DB_USER", "user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "password"),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
        "OPTIONS": {"charset": "utf8mb4"},
        "TEST": {
            "CHARSET": "utf8mb4",
            "NAME": "test_tox_allianceauth",
        },
    }

# Opt-in PostgreSQL backend. AllianceAuth only officially supports
# MySQL/MariaDB, so CI runs this as an allowed-to-fail job - it's an early
# warning for postgres-specific breakage, not a support guarantee.
elif os.environ.get("USE_POSTGRES", "False") == "True":
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "tox_allianceauth"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "password"),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
        "TEST": {
            "NAME": "test_tox_allianceauth",
        },
    }

# modeltranslation has to come before django.contrib.admin to patch it
INSTALLED_APPS = ["modeltranslation"] + INSTALLED_APPS

INSTALLED_APPS += [
    PACKAGE,
]
