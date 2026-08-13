# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Django 5.2 + DRF billing system. Domain flow: **Order → Invoice → Payment**, where a subscription-type order produces recurring invoices instead of terminating after one payment.

Stack: Django 5.2.11, Django REST Framework, drf-spectacular (OpenAPI), Celery + Redis, PostgreSQL, Gunicorn behind Nginx, WhiteNoise for static.

## Commands

The Django project lives one level down; `manage.py` is invoked as `python tidebilling/manage.py` **from the repo root** (this is how the Dockerfile, compose, and deploy.sh all call it). `settings.py` reads config straight from `os.environ` — there is no dotenv loader, so `.env` is only consulted by docker-compose, not by Django itself.

```bash
docker-compose up -d
docker-compose exec web python tidebilling/manage.py migrate
docker-compose exec web python tidebilling/manage.py createsuperuser
docker-compose exec web python tidebilling/manage.py create_sample_data --customers 10 --orders 20

# see the Testing section: --settings=tidebilling.settings_test is required
docker compose exec -e TEST_DATABASE=postgres web \
  python tidebilling/manage.py test --settings=tidebilling.settings_test

docker-compose logs -f web       # or: celery, celery-beat, db, nginx
./deploy.sh {deploy|stop|restart|logs|backup|status}
```

Services: `db` (Postgres 15), `redis`, `web` (migrate + collectstatic + gunicorn), `celery` (worker), `celery-beat` (scheduler), `nginx`. The `web` container mounts `./tidebilling` **read-only**, so `makemigrations` and any other file-writing command must run on the host, not via `docker-compose exec`.

For host-side work, `.venv` is current with `requirements.txt`. Recreate it with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` if it drifts.

## Testing

There is a test suite (370 tests) covering models, serializers, ViewSet actions, routing, roles, money handling, compliance and the Celery tasks. Shared helpers live in `tidebilling/tidebilling/`: `factories.py` (object factories) and `apitest.py` (`AuthenticatedAPITestCase`, token-authenticated). Both are named to dodge unittest's `test*.py` discovery pattern.

```bash
# Host, SQLite -- no services needed
python tidebilling/manage.py test --settings=tidebilling.settings_test

# Host, against the compose Postgres
TEST_DATABASE=postgres python tidebilling/manage.py test --settings=tidebilling.settings_test

# Inside the container, against the compose Postgres
docker compose exec -e TEST_DATABASE=postgres web \
  python tidebilling/manage.py test --settings=tidebilling.settings_test
```

`--settings=tidebilling.settings_test` is **required**, including in the container: the containers run `ENVIRONMENT=production`, which turns on `SECURE_SSL_REDIRECT`, and every API test then gets a 301 instead of its expected status. `settings_test` sets `ENVIRONMENT='test'` and disables the redirect.

`settings_test.py` swaps in in-memory SQLite (unless `TEST_DATABASE=postgres`), eager Celery, locmem cache/email and non-manifest static storage, so the suite needs no Postgres, Redis or broker. `TEST_RUNNER` points discovery at `BASE_DIR` because `manage.py` is invoked from the repo root.

Factories deliberately let model `save()` overrides generate identifiers and derived fields, so tests exercise that logic rather than bypass it.

## Billing invariants

These are enforced and covered by tests; breaking one is a regression, not a style choice.

- **Money is always `Decimal`, always quantized.** Use `tidebilling.money` (`money()`, `apply_tax()`, `default_tax_rate()`). `Decimal * float` raises `TypeError`, and because tasks swallow exceptions it surfaces as silently skipped billing.
- **`currency` and `tax_rate` are snapshotted** onto `Order` and `Invoice` at creation, so changing `settings.TAX_RATE`/`CURRENCY_CODE` never alters issued documents. Payment currency must match its invoice (`Payment.clean`).
- **Invoice numbers are gapless and sequential per year** (`INV-2026-000001`), allocated by `invoices.numbering.allocate()` under `select_for_update` inside the caller's transaction. Credit notes use the `CRN` series. Never generate a number outside a transaction.
- **Issued invoices are immutable.** Anything in `FINALIZED_STATUSES` refuses `calculate_totals()`, and the API returns 409 on edit/delete/add_item. Corrections go through `create_credit_note()`.
- **Every status transition writes `InvoiceHistory`** via `set_status()`/`record_status_change()`. Do not assign `invoice.status` directly.
- **Payments and refunds are idempotent by state.** `mark_as_completed()` raises `PaymentStateError` unless pending; refunds settle against the invoice and cap cumulatively at the payment total.
- **Financial records are never destroyed.** Customers/invoices/orders are referenced with `PROTECT`; customers with history are archived (`Customer.archive()`), and `DELETE /customers/{id}/` archives rather than deletes.
- **Access is role-based**: `admin` / `billing` / `readonly` groups, provisioned by `manage.py setup_roles` (run by compose and `deploy.sh`). A user with no role group is read-only.

## Gotchas

- **`Product.base_price` / `price` are `max_digits=5`** — a hard ceiling of 999.99.
- **Creating a Product requires at least one category *and* one tag.** Neither M2M sets `blank=True`, so both are mandatory on write. The tag requirement looks unintentional but relaxing it needs a migration.
- **Decimal arithmetic**: `Decimal * float` raises `TypeError`. Several bugs traced back to float literals in money paths. Use `tidebilling.money` helpers.
- **Celery tasks swallow exceptions** in bare `except Exception: print(...)` blocks, so a failure inside a task is invisible except in worker stdout. Tests call the task functions directly (eager mode propagates) rather than trusting return values.
- **`DateField(default=...)` must be a date factory**, not `timezone.now` — a datetime left on a `DateField` makes DRF refuse to serialize the instance until it is reloaded.
- **Nested-create actions must inject the parent key.** With `fields = '__all__'`, the FK is a required input, so `serializer.save(parent=obj)` alone still fails validation.
- API routes are `/api/v1/<app>/<resource>/`. The app segment cannot be dropped: `products` and `services` both register a `categories` resource.

## Architecture

Seven apps under `tidebilling/`, each following the same layout: `models.py`, `serializers.py`, `views.py` (DRF ViewSets), `urls.py` (DefaultRouter), `admin.py`, and `tasks.py` where background work exists (`invoices`, `subscriptions`, plus project-level `tidebilling/tasks.py`).

Dependency direction: `customers` and `products` are the leaves; `orders` depends on both; `invoices` depends on `orders`; `payments` and `subscriptions` depend on `invoices`/`customers`; `services` is largely standalone (its own categories, requests, deliverables, time logs, feedback).

Business logic lives on **models**, not in views or serializers:

- `save()` overrides generate human-readable identifiers on first save — `ORD-YYYYMMDD-XXXXXXXX`, `INV-…`, `REQ-…` (date + 8 hex chars from a uuid4) — and derive fields like `InvoiceItem.total_price` and `TimeLog.hours`.
- State transitions are model methods: `Invoice.mark_as_sent/mark_as_paid`, `Payment.mark_as_completed/mark_as_failed`, `Subscription.cancel/reactivate/upgrade_plan/add_usage`.
- Totals are recomputed by explicit `calculate_totals()` calls on `Order` and `Invoice` — they are *not* triggered by saving a child item, so callers that mutate items must call it (see `OrderViewSet.add_item`).
- Status vocabularies are `models.TextChoices` classes at module top (`OrderStatus`, `InvoiceStatus`, `PaymentStatus`, `SubscriptionStatus`, `BillingFrequency`, …). Filter and compare against these, not string literals.

Conventions in the API layer:

- ViewSets override `get_serializer_class()` to swap in `<Model>ListSerializer` for `list` and `<Model>DetailSerializer` for `retrieve`, with the plain serializer for writes. Detail serializers nest related objects; list serializers stay flat.
- Serializers use `fields = '__all__'` plus `read_only_fields` for generated values (`invoice_number`, `outstanding_amount`, timestamps). `created_by` is populated in `create()` from `self.context['request'].user`.
- Cross-cutting operations are `@action` methods on the ViewSet (`orders/{id}/add_item`, `invoices/overdue`, `subscriptions/{id}/upgrade`, `services/{id}/assign`).
- Every ViewSet declares `filterset_fields`, `search_fields`, `ordering_fields`; the backends are global in `REST_FRAMEWORK`.
- Auth is DRF `TokenAuthentication` (token from `POST /api/auth/token/`) with `IsAuthenticated` as the global default. `djangorestframework-simplejwt` is installed but unused.

Field-naming is inconsistent by generation: `customers` and `products` (pre-rewrite) use `created`/`modified`; every newer app uses `created_at`/`updated_at`. Match whichever app you're editing.

Every app has a populated `tests.py`, plus focused modules: `invoices/test_compliance.py`, `invoices/test_dunning.py`, `payments/test_settlement.py`, `subscriptions/test_lifecycle.py`, `tidebilling/test_money.py`, `tidebilling/test_permissions.py`. See the Testing section above.

## Container path settings

`BASE_DIR` (`/code/tidebilling`) is mounted **read-only**, but the static, media and log volumes mount at `/code/*`. Three settings exist to bridge that gap and are set in `docker-compose.yml`/`Dockerfile`; leaving them unset makes the container fail at startup:

- `STATIC_ROOT=/code/staticfiles` — otherwise `collectstatic` hits a read-only filesystem
- `MEDIA_ROOT=/code/media`
- `LOG_DIR=/code/logs` — otherwise the file log handler cannot be configured (the handler is dropped rather than crashing, but logs are lost)

Celery must be started with `--workdir=/code/tidebilling`. `WORKDIR` is `/code`, where `tidebilling` resolves to the outer namespace directory rather than the project package, and `celery -A tidebilling` fails with "Module 'tidebilling' has no attribute 'celery'".

`CELERY_RESULT_BACKEND` must be set alongside `CELERY_BROKER_URL`; it defaults to `redis://localhost` and will not reach the `redis` service otherwise.

## Configuration

`ENVIRONMENT=production` is the switch that turns on SSL redirect, HSTS, secure cookies, and `X_FRAME_OPTIONS=DENY`; it also flips Postgres `sslmode` from `disable` to `prefer`. `REDIS_URL` being set is what selects the Redis cache backend over LocMem.

`SECRET_KEY` falls back to a hardcoded value and `DEBUG` defaults to `True` when unset — both must be provided via env in any real deployment. `deploy.sh` provisions a superuser `admin`/`admin123` if none exists.

The README describes PayPal support that doesn't match the code; treat `settings.py`, `urls.py`, and the models as authoritative.

**The system is cash-only by design.** No payment gateway is integrated: `stripe` is in `requirements.txt` but never imported, and the gateway fields on `Payment`/`StoredPaymentMethod`/`Subscription` are unused scaffolding. Payments are recorded by staff, so `mark_as_completed()` is bookkeeping, not a charge. Adding a gateway means also adding inbound webhooks for reconciliation.
