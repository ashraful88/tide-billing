from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from tidebilling.permissions import IsBillingStaffOrReadOnly

from .models import Invoice, InvoiceItem, InvoiceHistory, InvoiceStatus, InvoiceType
from .serializers import (
    InvoiceSerializer, InvoiceItemSerializer, InvoiceHistorySerializer,
    InvoiceListSerializer, InvoiceDetailSerializer
)


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all()
    permission_classes = [IsBillingStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'invoice_type', 'customer', 'payment_terms']
    search_fields = ['invoice_number', 'customer__name', 'notes']
    ordering_fields = ['created_at', 'issue_date', 'due_date', 'total_amount']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return InvoiceListSerializer
        elif self.action == 'retrieve':
            return InvoiceDetailSerializer
        return InvoiceSerializer

    def update(self, request, *args, **kwargs):
        """Block edits to an issued invoice; corrections go via credit note."""
        invoice = self.get_object()
        if invoice.is_finalized:
            return Response(
                {
                    'detail': (
                        f'Invoice {invoice.invoice_number} is {invoice.status} '
                        f'and cannot be edited. Issue a credit note instead.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Issued invoices are never deleted, only cancelled or credit-noted."""
        invoice = self.get_object()
        if invoice.is_finalized:
            return Response(
                {
                    'detail': (
                        f'Invoice {invoice.invoice_number} is {invoice.status} '
                        f'and cannot be deleted. Cancel it or issue a credit note.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Mark invoice as sent"""
        invoice = self.get_object()
        invoice.mark_as_sent(user=request.user)
        serializer = self.get_serializer(invoice)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an invoice, recording the reason in its history."""
        invoice = self.get_object()
        if invoice.status == InvoiceStatus.PAID:
            return Response(
                {'detail': 'A paid invoice cannot be cancelled. Issue a credit note.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice.set_status(
            InvoiceStatus.CANCELLED,
            notes=request.data.get('reason', ''),
            user=request.user,
        )
        return Response(self.get_serializer(invoice).data)

    @action(detail=True, methods=['post'], url_path='credit_note')
    def credit_note(self, request, pk=None):
        """Issue a credit note against this invoice."""
        invoice = self.get_object()
        try:
            note = invoice.create_credit_note(
                amount=request.data.get('amount'),
                reason=request.data.get('reason', ''),
                user=request.user,
            )
        except ValidationError as exc:
            return Response(
                {'detail': exc.messages[0] if exc.messages else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            InvoiceSerializer(note, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def add_item(self, request, pk=None):
        """Add item to invoice"""
        invoice = self.get_object()
        if invoice.is_finalized:
            return Response(
                {
                    'detail': (
                        f'Invoice {invoice.invoice_number} is {invoice.status} '
                        f'and cannot be edited. Issue a credit note instead.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        # `invoice` is a required field on InvoiceItemSerializer (fields = '__all__'),
        # so inject it from the URL rather than making callers repeat it in the body.
        data = request.data.copy()
        data['invoice'] = invoice.pk
        serializer = InvoiceItemSerializer(data=data)

        if serializer.is_valid():
            serializer.save()
            invoice.calculate_totals()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        """Download the invoice as a PDF."""
        from tidebilling.pdf import render_invoice_pdf

        invoice = self.get_object()
        response = HttpResponse(
            render_invoice_pdf(invoice), content_type='application/pdf'
        )
        response['Content-Disposition'] = (
            f'attachment; filename="{invoice.invoice_number}.pdf"'
        )
        return response

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Get overdue invoices"""
        today = timezone.localdate()
        invoices = Invoice.objects.filter(
            due_date__lt=today,
            status__in=['sent', 'partially_paid']
        )
        serializer = InvoiceListSerializer(invoices, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def due_soon(self, request):
        """Get invoices due within specified days"""
        days = int(request.query_params.get('days', 7))
        due_date = timezone.localdate() + timedelta(days=days)

        invoices = Invoice.objects.filter(
            due_date__lte=due_date,
            status__in=['sent', 'partially_paid']
        )
        serializer = InvoiceListSerializer(invoices, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def aging(self, request):
        """Accounts-receivable aging summary bucketed by days overdue."""
        from tidebilling.money import ZERO, money

        today = timezone.localdate()
        buckets = {'current': ZERO, '1-30': ZERO, '31-60': ZERO, '61-90': ZERO, '90+': ZERO}
        counts = {key: 0 for key in buckets}

        # Credit notes carry positive amounts but are money owed back, so
        # counting them as receivable would overstate the balance.
        outstanding = Invoice.objects.filter(
            status__in=[
                InvoiceStatus.SENT,
                InvoiceStatus.PARTIALLY_PAID,
                InvoiceStatus.OVERDUE,
            ]
        ).exclude(invoice_type=InvoiceType.CREDIT_NOTE)
        for invoice in outstanding:
            days = (today - invoice.due_date).days
            if days <= 0:
                key = 'current'
            elif days <= 30:
                key = '1-30'
            elif days <= 60:
                key = '31-60'
            elif days <= 90:
                key = '61-90'
            else:
                key = '90+'
            buckets[key] += money(invoice.outstanding_amount)
            counts[key] += 1

        return Response(
            {
                'as_of': today,
                'buckets': {
                    key: {'amount': str(value), 'count': counts[key]}
                    for key, value in buckets.items()
                },
                'total_outstanding': str(money(sum(buckets.values(), ZERO))),
            }
        )

    @action(detail=True, methods=['get'])
    def items(self, request, pk=None):
        """Get invoice items"""
        invoice = self.get_object()
        items = invoice.items.all()
        serializer = InvoiceItemSerializer(items, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """Get the invoice's audit trail."""
        invoice = self.get_object()
        serializer = InvoiceHistorySerializer(invoice.history.all(), many=True)
        return Response(serializer.data)


class InvoiceItemViewSet(viewsets.ModelViewSet):
    queryset = InvoiceItem.objects.all()
    serializer_class = InvoiceItemSerializer
    permission_classes = [IsBillingStaffOrReadOnly]
    # InvoiceItem has no Meta.ordering; without a deterministic order the
    # paginator can repeat or skip rows across pages.
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['invoice', 'product']
    search_fields = ['description']
    ordering_fields = ['created_at', 'total_price', 'quantity']
    ordering = ['-created_at']
