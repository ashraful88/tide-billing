"""Project-level views that are not tied to a single app."""

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def health_check(request):
    """Liveness/readiness probe.

    Consumed by the Dockerfile HEALTHCHECK, the nginx `location /health/` block
    and `deploy.sh health_check`, all of which treat a non-2xx response as
    unhealthy. Deliberately unauthenticated so probes work without a token.
    """
    checks = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        checks['database'] = 'ok'
    except Exception as exc:  # pragma: no cover - depends on live DB failure
        checks['database'] = f'error: {exc}'

    healthy = all(value == 'ok' for value in checks.values())
    return JsonResponse(
        {'status': 'healthy' if healthy else 'unhealthy', 'checks': checks},
        status=200 if healthy else 503,
    )
