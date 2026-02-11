from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import engine, SessionLocal, get_db
from app import models
from app.models import Client, Quote, Invoice, User

from app.pdf import generate_quote_pdf

from app.emailer import send_email

from app.pdf import generate_quote_pdf
from app.invoice_pdf import generate_invoice_pdf
import json
from app.models import QuoteItem, InvoiceItem


# -------------------------
# APP SETUP
# -------------------------
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Umvuzo Media Invoicing System")
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="app/static"), name="static")


app.add_middleware(SessionMiddleware, secret_key="super-secret-key")

templates = Jinja2Templates(directory="app/templates")

# =====================================================
# AUTH
# =====================================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()
    db.close()

    if not user or user.password != password:
        return RedirectResponse("/login", status_code=302)

    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# =====================================================
# USER CREATION
# =====================================================

@app.get("/users/create", response_class=HTMLResponse)
def create_user_page(request: Request):
    return templates.TemplateResponse("create_user.html", {"request": request})


@app.post("/users/create")
def create_user(username: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = User(username=username, password=password)
    db.add(user)
    db.commit()
    db.close()
    return RedirectResponse("/dashboard", status_code=302)


# =====================================================
# DASHBOARD
# =====================================================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    db = SessionLocal()

    data = {
        "total_quotes": db.query(Quote).count(),
        "approved_quotes": db.query(Quote).filter(Quote.status == "Approved").count(),
        "converted_quotes": db.query(Quote).filter(Quote.converted == True).count(),
        "total_invoices": db.query(Invoice).count(),
        "paid_invoices": db.query(Invoice).filter(Invoice.paid == True).count(),
        "unpaid_invoices": db.query(Invoice).filter(Invoice.paid == False).count(),
    }

    db.close()
    return templates.TemplateResponse("dashboard.html", {"request": request, **data})


# =====================================================
# CLIENTS
# =====================================================

@app.get("/clients-page", response_class=HTMLResponse)
def clients_page(request: Request):
    db = SessionLocal()
    clients = db.query(Client).all()
    db.close()
    return templates.TemplateResponse("clients.html", {"request": request, "clients": clients})


@app.get("/clients/create", response_class=HTMLResponse)
def create_client_form(request: Request):
    return templates.TemplateResponse("create_client.html", {"request": request})


@app.post("/clients/create")
def create_client(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    db: Session = Depends(get_db)
):
    new_client = Client(name=name, email=email, phone=phone)
    db.add(new_client)
    db.commit()
    return RedirectResponse("/clients-page", status_code=303)


@app.get("/clients/{client_id}", response_class=HTMLResponse)
def client_history(client_id: int, request: Request, db: Session = Depends(get_db)):
    client = db.query(Client).get(client_id)
    quotes = db.query(Quote).filter(Quote.client_id == client_id).all()
    invoices = db.query(Invoice).filter(Invoice.client_id == client_id).all()

    return templates.TemplateResponse("client_history.html", {
        "request": request,
        "client": client,
        "quotes": quotes,
        "invoices": invoices
    })


# =====================================================
# QUOTES
# =====================================================

@app.get("/quotes-page", response_class=HTMLResponse)
def quotes_page(request: Request):
    db = SessionLocal()
    quotes = db.query(Quote).options(joinedload(Quote.client)).all()
    db.close()
    return templates.TemplateResponse("quotes.html", {"request": request, "quotes": quotes})


@app.get("/quotes/create", response_class=HTMLResponse)
def create_quote_form(request: Request, db: Session = Depends(get_db)):
    clients = db.query(Client).all()
    return templates.TemplateResponse("create_quote.html", {
        "request": request,
        "clients": clients
    })




@app.post("/quotes/create")
def create_quote(
    client_id: int = Form(...),
    items_data: str = Form(...),
    db: Session = Depends(get_db)
):
    last_quote = db.query(Quote).order_by(Quote.id.desc()).first()
    next_number = 1 if not last_quote else last_quote.quote_number + 1

    # Create base quote first
    new_quote = Quote(
        quote_number=next_number,
        client_id=client_id,
        total=0,
        status="Draft",
        converted=False
    )

    db.add(new_quote)
    db.commit()
    db.refresh(new_quote)

    # Parse items JSON
    items = json.loads(items_data)

    total_amount = 0

    for item in items:
        line_total = item["unit_cost"] * item["quantity"]
        total_amount += line_total

        quote_item = QuoteItem(
            quote_id=new_quote.id,
            description=item["description"],
            unit_cost=item["unit_cost"],
            quantity=item["quantity"]
        )

        db.add(quote_item)

    # Update quote total
    new_quote.total = total_amount
    db.commit()

    return RedirectResponse("/quotes-page", status_code=303)



@app.get("/quotes/{quote_id}/convert")
def convert_quote(quote_id: int, db: Session = Depends(get_db)):

    quote = db.get(Quote, quote_id)

    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    if quote.converted:
        return RedirectResponse("/quotes-page", status_code=302)

    # Get next invoice number
    last_invoice = db.query(func.max(Invoice.invoice_number)).scalar()
    next_number = 1 if not last_invoice else last_invoice + 1

    # Create invoice
    new_invoice = Invoice(
        invoice_number=next_number,
        client_id=quote.client_id,
        total=0,
        paid=False
    )

    db.add(new_invoice)
    db.commit()
    db.refresh(new_invoice)

    # Fetch Quote Items
    quote_items = db.query(QuoteItem).filter(
        QuoteItem.quote_id == quote.id
    ).all()

    total_amount = 0

    # Copy each QuoteItem to InvoiceItem
    for item in quote_items:
        line_total = item.unit_cost * item.quantity
        total_amount += line_total

        invoice_item = InvoiceItem(
            invoice_id=new_invoice.id,
            description=item.description,
            unit_cost=item.unit_cost,
            quantity=item.quantity
        )

        db.add(invoice_item)

    # Update invoice total
    new_invoice.total = total_amount

    # Mark quote as converted
    quote.converted = True

    db.commit()

    return RedirectResponse("/invoices-page", status_code=302)


# =====================================================
# INVOICES
# =====================================================

@app.get("/invoices-page", response_class=HTMLResponse)
def invoices_page(request: Request):
    db = SessionLocal()
    invoices = db.query(Invoice).options(joinedload(Invoice.client)).all()
    db.close()
    return templates.TemplateResponse("invoices.html", {"request": request, "invoices": invoices})


@app.get("/invoices/{invoice_id}/paid")
def mark_paid(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).get(invoice_id)
    invoice.paid = True
    db.commit()
    return RedirectResponse("/invoices-page", status_code=302)


# =========================
# INVOICE PDF
# =========================
@app.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    client = db.get(Client, invoice.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    items = db.query(InvoiceItem).filter(
        InvoiceItem.invoice_id == invoice.id
    ).all()

    filename = f"invoice_{invoice.id}.pdf"

    generate_invoice_pdf(invoice, client, items, filename)

    return FileResponse(filename, media_type="application/pdf", filename=filename)




# =========================
# INVOICE EMAIL
# =========================
@app.get("/invoices/{invoice_id}/email")
def email_invoice(invoice_id: int, db: Session = Depends(get_db)):

    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    client = db.get(Client, invoice.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    items = db.query(InvoiceItem).filter(
        InvoiceItem.invoice_id == invoice.id
    ).all()

    filename = f"invoice_{invoice.id}.pdf"

    generate_invoice_pdf(invoice, client, items, filename)

    send_email(
        to_email=client.email,
        subject=f"Invoice INV-{invoice.invoice_number:04d}",
        body=f"""
Dear {client.name},

Please find your invoice attached.

Total: R {invoice.total:.2f}

Thank you for your business.
""",
        pdf_path=filename
    )

    return RedirectResponse("/invoices-page", status_code=303)





@app.get("/quotes/{quote_id}/pdf")
def quote_pdf(quote_id: int, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    client = db.get(Client, quote.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    items = db.query(QuoteItem).filter(QuoteItem.quote_id == quote.id).all()

    filename = f"quote_{quote.id}.pdf"
    generate_quote_pdf(quote, client, items, filename)

    return FileResponse(filename, media_type="application/pdf", filename=filename)



@app.get("/quotes/{quote_id}/email")
def email_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    client = db.get(Client, quote.client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    filename = f"quote_{quote.id}.pdf"
    generate_quote_pdf(quote, client, filename)

    send_email(
    to_email=client.email,
    subject=f"Quote Q-{quote.quote_number:04d}",
    body=f"""
Dear {client.name},

Please find your quote attached.

Total: R {quote.total:.2f}

Thank you for your business.
""",
    pdf_path=filename
)


    return RedirectResponse("/quotes-page", status_code=302)




@app.get("/quotes/{quote_id}/approved")
def approve_quote(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.status = "Approved"
    db.commit()

    return RedirectResponse(url="/quotes-page", status_code=302)

@app.get("/quotes/{quote_id}/sent")
def mark_sent(quote_id: int, db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote.status = "Sent"
    db.commit()

    return RedirectResponse(url="/quotes-page", status_code=302)


from app.models import User
from app.database import SessionLocal
import os


def create_default_admin():
    db = SessionLocal()

    # Check if any users exist
    existing_user = db.query(User).first()

    if not existing_user:
        admin_username = os.getenv("ADMIN_USER")
        admin_password = os.getenv("ADMIN_PASS")

        if not admin_username or not admin_password:
            print("ADMIN_USER or ADMIN_PASS not set.")
            db.close()
            return

        admin = User(
            username=admin_username,
            password=admin_password
        )

        db.add(admin)
        db.commit()
        print("Default admin user created.")

    db.close()


create_default_admin()
