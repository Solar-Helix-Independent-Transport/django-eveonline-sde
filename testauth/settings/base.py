"""
Base settings for the test project.

A plain Django project - deliberately not an AllianceAuth one, eve_sde has no
AllianceAuth dependency and the tests shouldn't grow one. Overload anything
here in local.py.
"""

# Standard Library
import os

# Django
from django.utils.translation import gettext_lazy as _

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "solo",
]

SECRET_KEY = "wow I'm a really bad default secret key"

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(PROJECT_DIR)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "testauth.urls"
WSGI_APPLICATION = "testauth.wsgi.application"

LOCALE_PATHS = (os.path.join(BASE_DIR, "locale/"),)

# modeltranslation adds a column per language to every translated field, so
# this list has to match the one the migrations were generated against -
# changing it makes `makemigrations` want new migrations.
LANGUAGES = (  # Sorted by Language Code alphabetical order + English at top
    ("en", _("English")),
    # ("cs-cz", _("Czech")), #Not yet at 50% translated
    ("de", _("German")),
    ("es", _("Spanish")),
    ("it-it", _("Italian")),
    ("ja", _("Japanese")),
    ("ko-kr", _("Korean")),
    ("fr-fr", _("French")),
    ("nl-nl", _("Dutch")),
    ("pl-pl", _("Polish")),
    ("ru", _("Russian")),
    ("uk", _("Ukrainian")),
    ("zh-hans", _("Simplified Chinese")),
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

DEBUG = True
ALLOWED_HOSTS = ["*"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(os.path.join(BASE_DIR, "alliance_auth.sqlite3")),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
