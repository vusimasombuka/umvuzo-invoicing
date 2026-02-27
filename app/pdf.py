# app/pdf.py - Unified Quote & Invoice PDF Generator
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
import os

def generate_quote_pdf(quote, client, items, filename):
    return generate_document_pdf(
        doc_type='quote',
        document=quote,
        client=client,
        items=items,
        filename=filename
    )

def generate_invoice_pdf(invoice, client, items, filename, client_prefix=None):
    return generate_document_pdf(
        doc_type='invoice',
        document=invoice,
        client=client,
        items=items,
        filename=filename,
        client_prefix=client_prefix
    )

def generate_document_pdf(doc_type, document, client, items, filename, client_prefix=None):
    # VAT toggle
    VAT_ENABLED = False
    VAT_RATE = 0.15

    # Color scheme
    if doc_type == 'quote':
        accent_color = colors.HexColor("#FC8D33")  # Gold/orange for quotes
        doc_title = "QUOTE"
        number_label = "Quote #"
        status_colors = {
            "Draft": "#6C757D",
            "Sent": "#17a2b8", 
            "Approved": "#28a745",
            "Rejected": "#dc3545"
        }
        status_text = document.status.upper() if hasattr(document, 'status') else "DRAFT"
        status_color = status_colors.get(getattr(document, 'status', 'Draft'), "#6C757D")
        number_display = f"Q-{document.quote_number:04d}"
        valid_until = (document.created_at + __import__('datetime').timedelta(days=30)).strftime('%d %B %Y')
        show_paid_stamp = False
        show_converted_notice = getattr(document, 'converted', False)
    else:  # invoice
        accent_color = colors.HexColor("#FC8D33")  # Coral for invoices
        doc_title = "INVOICE"
        number_label = "Invoice #"
        status_text = "PAID" if document.paid else "PENDING"
        status_color = "#28a745" if document.paid else "#dc3545"
        prefix = client_prefix or client.client_code[:3]
        number_display = f"{prefix}-INV-{document.invoice_number:04d}"
        valid_until = None
        show_paid_stamp = document.paid
        show_converted_notice = False

    brand_color = colors.HexColor("#2C3E50")  # Navy
    light_gray = colors.HexColor("#F8F9FA")
    white = colors.white

    # COMPACT margins for both (matching quote style)
    doc = SimpleDocTemplate(
        filename, 
        pagesize=A4,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.4*inch,
        bottomMargin=0.4*inch
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=brand_color,
        spaceAfter=2,
        fontName='Helvetica-Bold',
        alignment=TA_RIGHT
    )
    
    # ===== LOGO (AS SPECIFIED) =====
    logo_path = "app/static/logo.png"
    if os.path.exists(logo_path):
        logo_table = Table([[Image(logo_path, width=1.5*inch, height=1.0*inch)]], 
                          colWidths=[7*inch], 
                          style=TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
        elements.append(logo_table)
        elements.append(Spacer(1, 0.05*inch))
    
    # ===== HEADER: Company left, Document right (COMPACT) =====
    company_text = f"""<b>Umvuzo Media (Pty) Ltd</b><br/>
<font size=8 color='#6C757D'>4 Veldblom Street, Terenure, Kempton Park, 1619<br/>
Tel: +27 61 213 0052 | info@umvuzomedia.co.za</font>"""

    if doc_type == 'quote':
        doc_info = f"""<font size=8>{number_label}:</font> <b>{number_display}</b><br/>
<font size=8>Date:</font> <b>{document.created_at.strftime('%d %B %Y')}</b><br/>
<font size=8>Valid Until:</font> <b>{valid_until}</b><br/>
<font size=8>Status:</font> <font color='{status_color}'><b>{status_text}</b></font>"""
    else:
        due_date = (document.created_at + __import__('datetime').timedelta(days=30)).strftime('%d %B %Y')
        doc_info = f"""<font size=8>{number_label}:</font> <b>{number_display}</b><br/>
<font size=8>Date:</font> <b>{document.created_at.strftime('%d %B %Y')}</b><br/>
<font size=8>Due Date:</font> <b>{due_date}</b><br/>
<font size=8>Status:</font> <font color='{status_color}'><b>{status_text}</b></font>"""

    header_data = [
        [Paragraph(company_text, ParagraphStyle('Company', parent=styles['Normal'], fontSize=9)), 
         Paragraph(doc_title, title_style)],
        ["", Paragraph(doc_info, ParagraphStyle('DocDetails', parent=styles['Normal'], alignment=TA_RIGHT, fontSize=9))]
    ]
    
    header_table = Table(header_data, colWidths=[4*inch, 3.8*inch])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(header_table)
    
    # Separator line (COMPACT)
    elements.append(Spacer(1, 0.05*inch))
    elements.append(Table([[""]], colWidths=[7.5*inch], style=TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 2, accent_color),
    ])))
    elements.append(Spacer(1, 0.2*inch))
    
        # ===== CLIENT INFO (COMPACT) - BILLING DETAILS ON BOTH =====
    label = "QUOTE TO" if doc_type == 'quote' else "BILL TO"
    client_lines = [f"<b>{client.name}</b>"]
    
    # Billing name on BOTH quote and invoice
    if client.billing_name and client.billing_name != client.name:
        client_lines.append(f"Attn: {client.billing_name}")
    
    client_lines.append(client.email or "")
    
    # Billing email on BOTH
    if client.billing_email and client.billing_email != client.email:
        client_lines.append(f"Billing: {client.billing_email}")
    
    if client.phone:
        client_lines.append(f"Tel: {client.phone}")
    
    # Address - show both regular and billing address on BOTH
    address_parts = []
    if client.address:
        address_parts.append(client.address.replace('\n', ', '))
    if client.billing_address:
        address_parts.append(client.billing_address.replace('\n', ', '))
    if address_parts:
        client_lines.append("<br/>".join(address_parts))
    
    tax_lines = []
    if client.vat_number:
        tax_lines.append(f"<b>VAT:</b> {client.vat_number}")
    if client.tax_number:
        tax_lines.append(f"<b>Tax:</b> {client.tax_number}")
    if tax_lines:
        client_lines.append("<br/>" + " | ".join(tax_lines))
    
    # Payment terms only on invoices (makes sense to keep this invoice-specific)
    if doc_type == 'invoice' and client.payment_terms:
        client_lines.append(f"<br/><b>Payment Terms:</b> {client.payment_terms}")
    
    client_text = "<br/>".join(filter(None, client_lines))
    
    client_data = [
        [Paragraph(f"<b>{label}</b>", ParagraphStyle('Header', parent=styles['Normal'], 
                                                     fontSize=10, textColor=accent_color, 
                                                     fontName='Helvetica-Bold'))],
        [Paragraph(client_text, ParagraphStyle('Client', parent=styles['Normal'], fontSize=9))]
    ]
    
    client_table = Table(client_data, colWidths=[7*inch])
    client_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), light_gray),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, accent_color),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 1), (-1, 1), 'TOP'),
    ]))
    elements.append(client_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # ===== ITEMS TABLE =====
    table_data = [["#", "Description", "Unit Cost", "Qty", "Amount"]]
    total = 0

    for idx, item in enumerate(items, 1):
        amount = item.unit_cost * item.quantity
        total += amount
        table_data.append([
            str(idx),
            Paragraph(item.description, ParagraphStyle('Desc', parent=styles['Normal'], fontSize=9)),
            f"R {item.unit_cost:,.2f}",
            f"{item.quantity}",
            f"R {amount:,.2f}"
        ])

    item_table = Table(table_data, colWidths=[0.4*inch, 4*inch, 1*inch, 0.6*inch, 1.2*inch])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), brand_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (1, 0), 'LEFT'),
        ('ALIGN', (2, 0), (-1, 0), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (1, -1), 'LEFT'),
        ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, light_gray]),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor("#E0E0E0")),
        ('LINEABOVE', (0, 0), (-1, 0), 1.5, brand_color),
        ('LINEBELOW', (0, -1), (-1, -1), 1.5, brand_color),
    ]))

    elements.append(item_table)
    elements.append(Spacer(1, 0.15*inch))

    # ===== TOTALS =====
    if VAT_ENABLED:
        vat_amount = total * VAT_RATE
        grand_total = total + vat_amount
        total_data = [
            ["", "", "Subtotal:", f"R {total:,.2f}"],
            ["", "", "VAT (15%):", f"R {vat_amount:,.2f}"],
            ["", "", "TOTAL DUE:" if doc_type == 'invoice' else "TOTAL:", f"R {grand_total:,.2f}"]
        ]
    else:
        total_data = [
            ["", "", "Subtotal:", f"R {total:,.2f}"],
            ["", "", "TOTAL DUE:" if doc_type == 'invoice' else "TOTAL:", f"R {total:,.2f}"]
        ]
    
    total_table = Table(total_data, colWidths=[3*inch, 2*inch, 1.2*inch, 1.3*inch])
    total_style = [
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (2, -1), (-1, -1), 12),
        ('TEXTCOLOR', (3, -1), (3, -1), accent_color),
        ('FONTNAME', (3, -1), (3, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -2), 4),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
    ]
    
    if VAT_ENABLED:
        total_style.append(('LINEBELOW', (2, -2), (-1, -2), 0.5, colors.HexColor("#E0E0E0")))
    
    total_table.setStyle(TableStyle(total_style))
    elements.append(total_table)
    
    # ===== PAID STAMP (INVOICE ONLY) =====
    if show_paid_stamp:
        elements.append(Spacer(1, 0.2*inch))
        stamp_table = Table([["PAID"]], colWidths=[3*inch], 
                           style=TableStyle([
                               ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                               ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('FONTSIZE', (0, 0), (-1, -1), 40),
                               ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                               ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#28a745")),
                               ('BORDER', (0, 0), (-1, -1), 3, colors.HexColor("#28a745")),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
                               ('TOPPADDING', (0, 0), (-1, -1), 15),
                           ]))
        elements.append(stamp_table)
    
    # ===== WHITESPACE FOR SIGNATURE =====
    elements.append(Spacer(1, 0.8*inch))
    
    # ===== CONVERTED NOTICE (QUOTE ONLY) =====
    if show_converted_notice:
        converted_table = Table([["This quote has been converted to an invoice and is no longer valid for new orders."]], 
                               colWidths=[7*inch],
                               style=TableStyle([
                                   ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                   ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#d4edda")),
                                   ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor("#155724")),
                                   ('FONTSIZE', (0, 0), (-1, -1), 9),
                                   ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                                   ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                                   ('TOPPADDING', (0, 0), (-1, -1), 6),
                               ]))
        elements.append(converted_table)
        elements.append(Spacer(1, 0.3*inch))

    # ===== BANKING DETAILS TABLE (FIXED LINE POSITION) =====
    # Include header as first row of table so line sits correctly
    bank_data = [
        ["BANKING DETAILS", "", "", ""],  # Row 0 - Header (will span)
        ["Bank:", "FNB/RMB", "Account Holder:", "Umvuzo Media (Pty) Ltd"],
        ["Account Type:", "Gold Business Account", "Account Number:", "63181737025"],
        ["Branch Code:", "250655", "Reference:", number_display]
    ]

    bank_table = Table(bank_data, colWidths=[1.3*inch, 2.2*inch, 1.3*inch, 2.2*inch])
    bank_table.setStyle(TableStyle([
        # Header row (row 0) styling
        ('SPAN', (0, 0), (-1, 0)),  # Span all columns for header
        ('BACKGROUND', (0, 0), (-1, 0), light_gray),
        ('LINEBELOW', (0, 0), (-1, 0), 2, accent_color),  # Accent line UNDER header
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'LEFT'),
        ('LEFTPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        
        # Data rows (rows 1-3) styling
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),  # Column 0 labels bold
        ('FONTNAME', (2, 1), (2, -1), 'Helvetica-Bold'),  # Column 2 labels bold
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),       # Column 1 values normal
        ('FONTNAME', (3, 1), (3, -1), 'Helvetica'),       # Column 3 values normal
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 1), (-1, -1), 10),
        ('RIGHTPADDING', (0, 1), (-1, -1), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        
        # Light lines between data rows only (not under header - that's the accent line)
        ('LINEBELOW', (0, 1), (-1, -2), 0.5, colors.HexColor("#E0E0E0")),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
    ]))

    # No separate banking_header - it's inside the table now
    elements.append(bank_table)

    # ===== SIGNATURE SECTION (QUOTES ONLY) =====
    if doc_type == 'quote':
        elements.append(Spacer(1, 0.3*inch))
        sig_data = [
            ["Acceptance:", "_________________________________", "Date:", "___________"]
        ]
        sig_table = Table(sig_data, colWidths=[1*inch, 3*inch, 0.8*inch, 1.5*inch])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(sig_table)
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("<font size=8>By signing, client accepts terms and conditions.</font>", 
                                 ParagraphStyle('SigNote', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8)))

    # ===== FOOTER =====
    elements.append(Spacer(1, 0.3*inch))
    footer_text = """<font size=9 color='#6C757D'>
<b>Thank you for your business!</b>
</font>"""
    elements.append(Paragraph(footer_text, ParagraphStyle('Footer', parent=styles['Normal'], alignment=TA_CENTER)))
    
    # Contact line
    contact_text = """<font size=8 color='#6C757D'>
Queries: +27 61 213 0052 | info@umvuzomedia.co.za | www.umvuzomedia.co.za
</font>"""
    elements.append(Paragraph(contact_text, ParagraphStyle('Contact', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8)))
    
    # Terms line
    if doc_type == 'invoice':
        terms_text = """<font size=8 color='#1e40af'>
Terms: Payment due within 30 days. Interest charged on overdue accounts.
</font>"""
        elements.append(Spacer(1, 0.05*inch))
        elements.append(Paragraph(terms_text, ParagraphStyle('Terms', parent=styles['Normal'], alignment=TA_CENTER, fontSize=8)))

    doc.build(elements)
    return filename