"""Settings used by the test suite.

Imports the real settings and overrides only what makes tests hermetic: no
Postgres/Redis/broker required, no network, no collectstatic. Run with:

    python tidebilling/manage.py test --settings=tidebilling.settings_test
"""

import os

from .settings import *  # noqa: F401,F403
from .settings import DATABASES as _POSTGRES_DATABASES

# Default to in-memory SQLite so the suite needs no services. The models use no
# Postgres-specific fields (JSONField is supported on SQLite 3.9+), so the
# schema round-trips cleanly.
#
# Set TEST_DATABASE=postgres to run against the real backend instead -- worth
# doing before release, because SQLite does not enforce every constraint the
# same way (notably row locking, which is a no-op there).
if os.environ.get('TEST_DATABASE') == 'postgres':
    DATABASES = _POSTGRES_DATABASES
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }

# ManifestStaticFilesStorage requires a collectstatic run and raises on any
# missing hashed file, which would break tests that render admin/docs pages.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.InMemoryStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Run Celery tasks synchronously in-process so task logic is testable without a
# broker; exceptions propagate instead of being swallowed by the worker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Keep production security toggles out of the test client's way.
ENVIRONMENT = 'test'
DEBUG = False
SECURE_SSL_REDIRECT = False

LOGGING_CONFIG = None
