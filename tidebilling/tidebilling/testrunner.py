"""Project test runner.

``manage.py`` is invoked from the repo root (``python tidebilling/manage.py``),
so unittest discovery would otherwise start in the repo root and find nothing.
Default the discovery root to the Django project directory instead, so a bare
``manage.py test`` collects every app's tests.
"""

from django.conf import settings
from django.test.runner import DiscoverRunner


class ProjectTestRunner(DiscoverRunner):
    def build_suite(self, test_labels=None, **kwargs):
        if not test_labels:
            test_labels = [str(settings.BASE_DIR)]
        return super().build_suite(test_labels, **kwargs)
