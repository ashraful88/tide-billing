"""Invoice PDF rendering.

Uses reportlab's low-level canvas rather than a templating stack: it is pure
Python with no system libraries, which keeps the Docker image unchanged.
"""

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

LEFT = 20 * mm
RIGHT = 190 * mm
LINE = 6 * mm


def render_invoice_pdf(invoice):
    """Render ``invoice`` and return the PDF as bytes."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    _, height = A4
    y = height - 25 * mm

    is_credit_note = invoice.invoice_type == 'credit_note'
    title = 'CREDIT NOTE' if is_credit_note else 'INVOICE'

    pdf.setFont('Helvetica-Bold', 18)
    pdf.drawString(LEFT, y, title)
    pdf.setFont('Helvetica', 10)
    pdf.drawRightString(RIGHT, y, invoice.invoice_number)
    y -= LINE * 2

    pdf.setFont('Helvetica-Bold', 10)
    pdf.drawString(LEFT, y, 'Bill To')
    y -= LINE
    pdf.setFont('Helvetica', 10)
    for line in (invoice.customer.name, invoice.customer.email, invoice.customer.phone):
        pdf.drawString(LEFT, y, str(line))
        y -= LINE

    y += LINE * 3
    pdf.drawRightString(RIGHT, y, f'Issue date: {invoice.issue_date}')
    y -= LINE
    pdf.drawRightString(RIGHT, y, f'Due date: {invoice.due_date}')
    y -= LINE
    pdf.drawRightString(RIGHT, y, f'Status: {invoice.get_status_display()}')
    if is_credit_note and invoice.original_invoice_id:
        y -= LINE
        pdf.drawRightString(
            RIGHT, y, f'Against: {invoice.original_invoice.invoice_number}'
        )
    y -= LINE * 3

    pdf.setFont('Helvetica-Bold', 10)
    pdf.drawString(LEFT, y, 'Description')
    pdf.drawRightString(LEFT + 100 * mm, y, 'Qty')
    pdf.drawRightString(LEFT + 130 * mm, y, 'Unit')
    pdf.drawRightString(RIGHT, y, 'Amount')
    y -= 2 * mm
    pdf.line(LEFT, y, RIGHT, y)
    y -= LINE

    pdf.setFont('Helvetica', 10)
    for item in invoice.items.all():
        if y < 40 * mm:
            pdf.showPage()
            y = height - 25 * mm
            pdf.setFont('Helvetica', 10)
        pdf.drawString(LEFT, y, str(item.description)[:60])
        pdf.drawRightString(LEFT + 100 * mm, y, str(item.quantity))
        pdf.drawRightString(LEFT + 130 * mm, y, str(item.unit_price))
        pdf.drawRightString(RIGHT, y, str(item.total_price))
        y -= LINE

    y -= 2 * mm
    pdf.line(LEFT + 110 * mm, y, RIGHT, y)
    y -= LINE

    currency = invoice.currency
    rows = [
        ('Subtotal', invoice.subtotal),
        (f'Tax ({invoice.tax_rate * 100:.2f}%)', invoice.tax_amount),
    ]
    if invoice.discount_amount:
        rows.append(('Discount', -invoice.discount_amount))
    rows.append(('Total', invoice.total_amount))
    rows.append(('Paid', invoice.paid_amount))
    rows.append(('Outstanding', invoice.outstanding_amount))

    for label, value in rows:
        if label in ('Total', 'Outstanding'):
            pdf.setFont('Helvetica-Bold', 10)
        else:
            pdf.setFont('Helvetica', 10)
        pdf.drawRightString(LEFT + 150 * mm, y, label)
        pdf.drawRightString(RIGHT, y, f'{currency} {value}')
        y -= LINE

    if invoice.notes:
        y -= LINE
        pdf.setFont('Helvetica-Oblique', 9)
        pdf.drawString(LEFT, y, str(invoice.notes)[:110])

    if invoice.footer_text:
        pdf.setFont('Helvetica', 8)
        pdf.drawString(LEFT, 15 * mm, str(invoice.footer_text)[:130])

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
