"""Money helpers.

Two rules the rest of the codebase depends on:

1. Never mix ``Decimal`` with ``float``. ``Decimal * float`` raises TypeError,
   and because several Celery tasks swallow exceptions that surfaces as
   silently skipped billing rather than a crash.
2. Quantize at every step where a value is stored or compared. The money
   columns are ``decimal_places=2``; leaving un-quantized intermediates around
   means the in-memory value and the persisted value disagree.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

CENTS = Decimal('0.01')
ZERO = Decimal('0.00')


def money(value):
    """Coerce to a 2dp Decimal using banker-safe half-up rounding."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def default_tax_rate():
    """Tax rate from settings as a Decimal.

    ``settings.TAX_RATE`` is parsed as a float at import time, so it must be
    round-tripped through ``str`` rather than handed to Decimal directly.
    """
    return Decimal(str(settings.TAX_RATE))


def default_currency():
    return settings.CURRENCY_CODE


def apply_tax(subtotal, rate):
    """Return the tax due on ``subtotal`` at ``rate``, quantized."""
    return money(money(subtotal) * Decimal(str(rate)))
