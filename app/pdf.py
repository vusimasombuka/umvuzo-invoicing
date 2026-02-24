from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.platypus import KeepTogether
from reportlab.lib.enums import TA_RIGHT
import os


def generate_quote_pdf(quote, client, items, filename):

    doc = SimpleDocTemplate(filename, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()

    brand_blue = colors.HexColor("#f5ab49")

    # Logo
    logo_path = "app/static/logo.png"
    if os.path.exists(logo_path):
        img = Image(logo_path, width=2 * inch, height=1 * inch)
        elements.append(img)

    elements.append(Spacer(1, 0.2 * inch))


    accent_line = Table([[""]], colWidths=[6 * inch])
    accent_line.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdae54")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(accent_line)
    elements.append(Spacer(1, 0.3 * inch))


    # Header Row (Title + Quote Info)
    header_data = [
        [
            Paragraph("<b>Umvuzo Media (Pty) Ltd</b>", styles["Normal"]),
            Paragraph(f"<b>QUOTE</b>", styles["Title"])
        ],
        [
            Paragraph("4 Veldblom Street<br/>Terenure<br/>Kempton Park<br/>1619", styles["Normal"]),
            Paragraph(f"Quote #: Q-{quote.quote_number:04d}<br/>Date: {quote.created_at.strftime('%Y-%m-%d')}", styles["Normal"])
        ]
    ]

    header_table = Table(header_data, colWidths=[4 * inch, 2 * inch])
    header_table.setStyle(TableStyle([
    ("ALIGN", (1, 0), (1, -1), "RIGHT"),  # Align entire right column to right
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
]))

    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    elements.append(header_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Billed To Section
    billed_data = [
        [Paragraph("<b>Billed To</b>", styles["Normal"])],
        [client.name],
        [client.email or ""]
    ]

    billed_table = Table(billed_data, colWidths=[6 * inch])
    billed_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 2, colors.HexColor("#fdae54")),
        ("BACKGROUND", (0, 0), (-1, 0), brand_blue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    elements.append(billed_table)
    elements.append(Spacer(1, 0.4 * inch))

    # Item Table
    table_data = [["Description", "Unit Cost", "Qty", "Amount"]]
    total = 0

    for item in items:
        amount = item.unit_cost * item.quantity
        total += amount

        table_data.append([
            item.description,
            f"R {item.unit_cost:.2f}",
            f"{item.quantity}",
            f"R {amount:.2f}"
        ])

    item_table = Table(table_data, colWidths=[3 * inch, 1 * inch, 1 * inch, 1 * inch])
    item_table.setStyle(TableStyle([

    # Header underline
    ("LINEBELOW", (0, 0), (-1, 0), 2, colors.HexColor("#fdae54")),

    # Header background
    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),

    # Align description LEFT
    ("ALIGN", (0, 1), (0, -1), "LEFT"),

    # Align numeric columns RIGHT
    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),

    # Align header properly
    ("ALIGN", (0, 0), (0, 0), "LEFT"),
    ("ALIGN", (1, 0), (-1, 0), "RIGHT"),

    # Subtle row separators
    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),

    # Padding
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))



    elements.append(item_table)
    elements.append(Spacer(1, 0.4 * inch))

    # Total Section
    total_table = Table(
    [["TOTAL", f"R {total:.2f}"]],
    colWidths=[2 * inch, 2 * inch]
)

    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdae54")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    wrapper = Table([[total_table]], colWidths=[6 * inch])
    wrapper.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT")
    ]))

    elements.append(wrapper)
    elements.append(Spacer(1, 0.4 * inch))


    # Banking Details
    bank_data = [
        ["Bank:", "FNB/RMB"],
        ["Account Holder:", "Umvuzo Media (Pty) Ltd"],
        ["Account Type:", "Gold Business Account"],
        ["Account Number:", "63181737025"],
        ["Branch Code:", "250655"],
    ]

    bank_table = Table(bank_data, colWidths=[2.5 * inch, 3.5 * inch])
    bank_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#fdae54")),
        ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.grey),

        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
    ]))

    elements.append(bank_table)
    elements.append(Spacer(1, 0.4 * inch))

    # Footer
    footer = Paragraph(
        "Contact: +27612130052 | info@umvuzomedia.co.za | www.umvuzomedia.co.za",
        styles["Normal"]
    )

    elements.append(footer)

    doc.build(elements)
    return filename
