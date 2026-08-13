"""Gapless sequential invoice numbering.

Statutory numbering must be sequential with no gaps, per year. That rules out
the previous random-hex scheme and also rules out generating the number before
the surrounding transaction is known to commit.

Allocation takes a row lock on the per-year counter, so concurrent invoice
creation serialises on that row rather than racing. The lock is held for the
remainder of the caller's transaction, which is why ``allocate`` must be called
inside ``transaction.atomic``.
"""

from django.db import models, transaction
from django.utils import timezone

INVOICE_PREFIX = 'INV'
CREDIT_NOTE_PREFIX = 'CRN'
SEQUENCE_WIDTH = 6


class DocumentSequence(models.Model):
    """Per-year, per-prefix counter for statutory document numbers."""

    prefix = models.CharField(max_length=10)
    year = models.PositiveIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['prefix', 'year']
        verbose_name = 'Document sequence'
        verbose_name_plural = 'Document sequences'

    def __str__(self):
        return f'{self.prefix}-{self.year}: {self.last_value}'


def allocate(prefix=INVOICE_PREFIX, year=None):
    """Return the next number for ``prefix`` in ``year``, e.g. INV-2026-000001.

    Must run inside an atomic block: the counter row stays locked until the
    caller's transaction ends, which is what makes the sequence gapless. If the
    caller rolls back, the counter rolls back with it.
    """
    year = year or timezone.localdate().year

    with transaction.atomic():
        sequence, _ = DocumentSequence.objects.get_or_create(
            prefix=prefix, year=year
        )
        # Re-fetch under a row lock; get_or_create cannot lock a row it creates.
        sequence = DocumentSequence.objects.select_for_update().get(
            pk=sequence.pk
        )
        sequence.last_value += 1
        sequence.save(update_fields=['last_value'])

    return f'{prefix}-{year}-{sequence.last_value:0{SEQUENCE_WIDTH}d}'
