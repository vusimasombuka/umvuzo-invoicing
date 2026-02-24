from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.database import engine, SessionLocal, get_db
from app import models
from app.models import Client, Quote, Invoice, User
from app.emailer import send_email
from app.pdf import generate_quote_pdf
from app.invoice_pdf import generate_invoice_pdf
import json
from app.models import QuoteItem, InvoiceItem
from app.models import Service
from fastapi import Request
from passlib.context import CryptContext
import secrets
from datetime import datetime, timedelta
from app.models import PasswordResetToken
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
import re

EMAIL_REGEX = r"^[^@]+@[^@]+\.[^@]+$"

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

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

    if not user or not verify_password(password, user.password):
        request.session["flash"] = "Invalid email or password."
        return RedirectResponse("/login", status_code=303)

    request.session["user_id"] = user.id
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# =====================================================
# USER CREATION
# =====================================================

@app.get("/users/create", response_class=HTMLResponse)
def create_user_page(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse("create_user.html", {"request": request})



@app.post("/users/create")
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    # 🔒 Require login
    if "user_id" not in request.session:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    # Validate email format
    if not re.match(EMAIL_REGEX, username):
        request.session["flash"] = "Username must be a valid email address."
        db.close()
        return RedirectResponse("/users/create", status_code=303)

    # Check duplicate
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        request.session["flash"] = "User already exists."
        db.close()
        return RedirectResponse("/users/create", status_code=303)

    # Create user with hashed password
    user = User(
        username=username,
        password=hash_password(password)
    )

    db.add(user)
    db.commit()
    db.close()

    request.session["flash"] = "User created successfully."
    return RedirectResponse("/dashboard", status_code=303)


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
    address: str = Form(None),
    billing_name: str = Form(None),
    billing_email: str = Form(None),
    billing_address: str = Form(None),
    vat_number: str = Form(None),
    tax_number: str = Form(None),
    payment_terms: str = Form(None),
    db: Session = Depends(get_db)
):
    
    import re

    # Clean name (letters only)
    clean_name = re.sub(r'[^A-Za-z]', '', name).upper()
    base_code = (clean_name + "XXX")[:3]

    # Check duplicates
    existing_clients = db.query(Client).all()

    duplicate_count = 0
    for c in existing_clients:
        if c.client_code and c.client_code.startswith(base_code):
            duplicate_count += 1

    if duplicate_count > 0:
        client_code = f"{base_code}{duplicate_count + 1}"
    else:
        client_code = base_code

    new_client = Client(
        name=name,
        email=email,
        phone=phone,
        address=address,
        client_code=client_code,
        billing_name=billing_name,
        billing_email=billing_email,
        billing_address=billing_address,
        vat_number=vat_number,
        tax_number=tax_number,
        payment_terms=payment_terms
    )

    db.add(new_client)
    db.commit()

    return RedirectResponse("/clients-page", status_code=303)



@app.get("/clients/{client_id}", response_class=HTMLResponse)
def client_history(client_id: int, request: Request, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)

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
    
    from sqlalchemy.orm import joinedload

    from sqlalchemy.orm import joinedload

    quotes = (
        db.query(Quote)
        .options(
            joinedload(Quote.items),
            joinedload(Quote.client)
        )
        .all()
)
    db.close()

    return templates.TemplateResponse("quotes.html", {"request": request, "quotes": quotes})


@app.get("/quotes/create", response_class=HTMLResponse)
def create_quote_form(request: Request, db: Session = Depends(get_db)):
    clients = db.query(Client).all()
    services = db.query(Service).order_by(Service.name).all()

    return templates.TemplateResponse(
    "create_quote.html",
    {
        "request": request,
        "clients": clients,
        "services": services
    }
)


@app.post("/quotes/create")
def create_quote(
    client_id: int = Form(...),
    items_data: str = Form(...),
    db: Session = Depends(get_db)
):
    last_quote = (
        db.query(func.max(Quote.quote_number))
        .filter(Quote.client_id == client_id)
        .scalar()
)

    next_number = 1 if not last_quote else last_quote + 1

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
    last_invoice = (
        db.query(func.max(Invoice.invoice_number))
        .filter(Invoice.client_id == quote.client_id)
        .scalar()
)

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

    from sqlalchemy.orm import joinedload

    invoices = (
        db.query(Invoice)
        .options(
            joinedload(Invoice.items),
            joinedload(Invoice.client)
        )
        .all()
    )
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
    generate_invoice_pdf(invoice, client, items, filename, client.client_code)
    return FileResponse(filename, media_type="application/pdf", filename=filename)




# =========================
# INVOICE EMAIL
# =========================
@app.get("/invoices/{invoice_id}/email")

def email_invoice(request: Request, invoice_id: int, db: Session = Depends(get_db)):

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

    generate_invoice_pdf(invoice, client, items, filename, client.client_code)

    send_email(
        to_email=client.email,
        subject=f"Invoice INV-{invoice.invoice_number:04d}",
        body=f"""
Dear {client.name},

Please find your invoice attached.


Thank you for your business.
""",
        pdf_path=filename
    )

    request.session["flash"] = "Invoice emailed successfully."
    
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
def email_quote(quote_id: int, request: Request, db: Session = Depends(get_db)):

    quote = db.query(Quote).filter(Quote.id == quote_id).first()

    if not quote:
        return RedirectResponse("/quotes-page", status_code=status.HTTP_303_SEE_OTHER)

    try:
        filename = f"quote_{quote.quote_number}.pdf"

        # IMPORTANT — match your function signature
        items = db.query(QuoteItem).filter(
            QuoteItem.quote_id == quote.id
        ).all()

        generate_quote_pdf(
            quote,
            quote.client,
            items,
            filename
        )


        send_email(
            quote.client.email,
            f"Quote #{quote.quote_number}",
            f"Dear {quote.client.name},\n\nPlease find your quote attached.\n\nTotal: R {quote.total:.2f}",
            filename
        )

        request.session["flash"] = "Quote emailed successfully."

    except Exception as e:
        print("QUOTE EMAIL ERROR:", e)
        request.session["flash"] = f"Email failed: {str(e)}"

    return RedirectResponse("/quotes-page", status_code=status.HTTP_303_SEE_OTHER)




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
            password=hash_password(admin_password)  # ✅ HASHED
        )

        db.add(admin)
        db.commit()
        print("Default admin user created.")

    db.close()


create_default_admin()


def seed_services():
    db = SessionLocal()

    existing_service = db.query(Service).first()
    if existing_service:
        db.close()
        return  # Services already seeded

    services = [
        # --- IT Support ---
        {"name": "IT Consultation", "description": "General IT consultation and advisory", "price": 450.0, "category": "Consulting"},
        {"name": "Remote Support", "description": "Remote troubleshooting and technical support", "price": 350.0, "category": "Support"},
        {"name": "Onsite Support", "description": "Onsite technical assistance", "price": 650.0, "category": "Support"},
        
        # --- Networking ---
        {"name": "Router Setup", "description": "Router installation and configuration", "price": 650.0, "category": "Networking"},
        {"name": "Network Cabling", "description": "Structured cabling per point", "price": 300.0, "category": "Networking"},
        
        # --- Security ---
        {"name": "CCTV Installation", "description": "CCTV camera installation per unit", "price": 1200.0, "category": "Security"},
        {"name": "Access Control Setup", "description": "Access control system configuration", "price": 1800.0, "category": "Security"},
        
        # --- Cloud & Systems ---
        {"name": "Microsoft 365 Setup", "description": "Email and Microsoft 365 configuration", "price": 950.0, "category": "Cloud"},
        {"name": "Server Setup", "description": "Server installation and configuration", "price": 2500.0, "category": "Infrastructure"},
    ]

    for s in services:
        service = Service(
            name=s["name"],
            description=s["description"],
            price=s["price"],
            category=s["category"]
        )
        db.add(service)

    db.commit()
    db.close()
    print("Charge sheet seeded successfully.")


seed_services()


from fastapi.responses import HTMLResponse
from fastapi import Request
from fastapi.templating import Jinja2Templates




@app.get("/clients/{client_id}/edit")
def edit_client_page(client_id: int, request: Request, db: Session = Depends(get_db)):

    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        return RedirectResponse("/clients-page")

    return templates.TemplateResponse(
        "edit_client.html",
        {"request": request, "client": client}
    )


@app.post("/clients/{client_id}/edit")
def update_client(
    client_id: int,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: str = Form(None),
    billing_name: str = Form(None),
    billing_email: str = Form(None),
    billing_address: str = Form(None),
    vat_number: str = Form(None),
    tax_number: str = Form(None),
    payment_terms: str = Form(None),
    db: Session = Depends(get_db)
):

    client = db.query(Client).filter(Client.id == client_id).first()

    if not client:
        return RedirectResponse("/clients-page")

    client.name = name
    client.email = email
    client.phone = phone
    client.address = address
    client.billing_name = billing_name
    client.billing_email = billing_email
    client.billing_address = billing_address
    client.vat_number = vat_number
    client.tax_number = tax_number
    client.payment_terms = payment_terms

    db.commit()

    return RedirectResponse("/clients-page", status_code=303)


# =====================================================
# SERVICES
# =====================================================

@app.get("/services", response_class=HTMLResponse)
def services_page(request: Request, db: Session = Depends(get_db)):
    services = db.query(Service).order_by(Service.category, Service.name).all()

    return templates.TemplateResponse(
        "services.html",
        {
            "request": request,
            "services": services
        }
    )



@app.get("/services/{service_id}/edit", response_class=HTMLResponse)
def edit_service_page(service_id: int, request: Request, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        return RedirectResponse("/services", status_code=303)

    return templates.TemplateResponse("edit_service.html", {
        "request": request,
        "service": service
    })


@app.post("/services/{service_id}/edit")
def update_service(
    service_id: int,
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    category: str = Form(...),
    db: Session = Depends(get_db)
):
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        return RedirectResponse("/services", status_code=303)

    service.name = name
    service.description = description
    service.price = price
    service.category = category

    db.commit()

    return RedirectResponse("/services", status_code=303)


@app.post("/services/create")
def create_service(
    name: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    category: str = Form(...),
    db: Session = Depends(get_db)
):
    print("Creating service:", name, description, price, category)
    service = Service(
        name=name,
        description=description,
        price=price,
        category=category
    )

    db.add(service)
    db.commit()

    return RedirectResponse("/services", status_code=303)

@app.get("/services/{service_id}/delete")
def delete_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()

    if service:
        db.delete(service)
        db.commit()

    return RedirectResponse("/services", status_code=303)


@app.get("/change-password")
def change_password_page(request: Request):
    if "user_id" not in request.session:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("change_password.html", {"request": request})


@app.post("/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    if "user_id" not in request.session:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()
    user = db.query(User).get(request.session["user_id"])

    if not verify_password(current_password, user.password):
        request.session["flash"] = "Current password is incorrect."
        db.close()
        return RedirectResponse("/change-password", status_code=303)

    if new_password != confirm_password:
        request.session["flash"] = "Passwords do not match."
        db.close()
        return RedirectResponse("/change-password", status_code=303)

    user.password = hash_password(new_password)
    db.commit()
    db.close()

    request.session["flash"] = "Password updated successfully."
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/forgot-password")
def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        "forgot_password.html",
        {"request": request}
    )


@app.post("/forgot-password")
def forgot_password(request: Request, username: str = Form(...)):
    db = SessionLocal()
    user = db.query(User).filter(User.username == username).first()

    # Always show same message (prevent user enumeration)
    flash_message = "If that email exists, a reset link has been sent."

    if user:
        token = secrets.token_urlsafe(32)

        reset = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )

        db.add(reset)
        db.commit()

        BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
        reset_link = f"{BASE_URL}/reset-password/{token}"

        send_email(
            to_email=user.username,
            subject="Password Reset - Umvuzo Invoicing",
            body=f"""
Hello,

Click the link below to reset your password:

{reset_link}

This link expires in 1 hour.

If you did not request this, ignore this email.
""",
    pdf_path=None
)

    db.close()

    request.session["flash"] = flash_message
    return RedirectResponse("/login", status_code=303)



@app.get("/reset-password/{token}")
def reset_password_page(request: Request, token: str):
    db = SessionLocal()
    reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token
    ).first()
    db.close()

    if not reset or reset.expires_at < datetime.utcnow():
        request.session["flash"] = "Invalid or expired reset link."
        return RedirectResponse("/login", status_code=303)

    return templates.TemplateResponse(
        "reset_password.html",
        {"request": request, "token": token}
    )


@app.post("/reset-password/{token}")
def reset_password(
    request: Request,
    token: str,
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    db = SessionLocal()

    reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token
    ).first()

    if not reset:
        db.close()
        request.session["flash"] = "Invalid or expired reset link."
        return RedirectResponse("/login", status_code=303)

    if reset.expires_at < datetime.utcnow():
        db.delete(reset)
        db.commit()
        db.close()
        request.session["flash"] = "Reset link has expired."
        return RedirectResponse("/login", status_code=303)

    if new_password != confirm_password:
        db.close()
        request.session["flash"] = "Passwords do not match."
        return RedirectResponse(f"/reset-password/{token}", status_code=303)

    user = db.query(User).get(reset.user_id)
    user.password = hash_password(new_password)

    db.delete(reset)  # one-time use
    db.commit()
    db.close()

    request.session["flash"] = "Password reset successfully."
    return RedirectResponse("/login", status_code=303)