from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from tidebilling.permissions import IsBillingStaffOrReadOnly
from django.db.models import Q

from .models import Customer, CustomerContact
from .serializers import (
    CustomerSerializer, CustomerContactSerializer, 
    CustomerListSerializer, CustomerDetailSerializer
)


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    permission_classes = [IsBillingStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'created']
    search_fields = ['name', 'email', 'phone']
    ordering_fields = ['name', 'created', 'modified']
    ordering = ['-created']

    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerListSerializer
        elif self.action == 'retrieve':
            return CustomerDetailSerializer
        return CustomerSerializer

    @action(detail=True, methods=['get'])
    def contacts(self, request, pk=None):
        """Get all contacts for a customer"""
        customer = self.get_object()
        contacts = customer.customercontact_set.all()
        serializer = CustomerContactSerializer(contacts, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def search(self, request):
        """Advanced search for customers"""
        query = request.query_params.get('q', '')
        if not query:
            return Response({'detail': 'Query parameter "q" is required.'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        customers = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query) |
            Q(note__icontains=query)
        )
        
        serializer = CustomerListSerializer(customers, many=True)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        """Archive rather than delete when financial history exists.

        Invoices, payments and subscriptions reference customers with PROTECT,
        so a hard delete would fail anyway; archiving retires the customer and
        keeps the audit trail intact.
        """
        customer = self.get_object()
        has_history = (
            customer.invoices.exists()
            or customer.payments.exists()
            or customer.orders.exists()
            or customer.subscriptions.exists()
        )
        if has_history:
            customer.archive()
            return Response(
                {
                    'detail': (
                        'Customer has financial records and was archived '
                        'instead of deleted.'
                    ),
                    'archived': True,
                },
                status=status.HTTP_200_OK,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        """Retire a customer without destroying their history."""
        customer = self.get_object()
        customer.archive()
        return Response(CustomerSerializer(customer).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        customer = self.get_object()
        customer.unarchive()
        return Response(CustomerSerializer(customer).data)

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """Account statement: invoiced, paid and outstanding for a customer."""
        from tidebilling.money import ZERO, money

        from invoices.models import InvoiceType

        customer = self.get_object()
        documents = customer.invoices.exclude(status='cancelled')

        # Credit notes are money owed back to the customer, so they reduce the
        # balance. Summing them alongside invoices would inflate both the
        # invoiced total and what the customer appears to owe.
        invoices = documents.exclude(invoice_type=InvoiceType.CREDIT_NOTE)
        credit_notes = documents.filter(invoice_type=InvoiceType.CREDIT_NOTE)

        invoiced = money(sum((i.total_amount for i in invoices), ZERO))
        credited = money(sum((n.total_amount for n in credit_notes), ZERO))
        paid = money(sum((i.paid_amount for i in invoices), ZERO))

        return Response(
            {
                'customer': customer.name,
                'currency': getattr(invoices.first(), 'currency', None),
                'invoice_count': invoices.count(),
                'credit_note_count': credit_notes.count(),
                'total_invoiced': str(invoiced),
                'total_credited': str(credited),
                'total_paid': str(paid),
                'total_outstanding': str(money(invoiced - credited - paid)),
            }
        )


class CustomerContactViewSet(viewsets.ModelViewSet):
    queryset = CustomerContact.objects.all()
    serializer_class = CustomerContactSerializer
    permission_classes = [IsBillingStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['customer']
    search_fields = ['name', 'email', 'phone']
    ordering_fields = ['name', 'created', 'modified']
    ordering = ['-created']
