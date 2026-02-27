from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text
from app.database import engine, SessionLocal, get_db
from app import models
from app.models import (
    Client, Quote, Invoice, User, Service, PasswordResetToken, 
    QuoteItem, InvoiceItem, AuditLog, UserRole
)
from app.emailer import send_email
from app.pdf import generate_quote_pdf
from app.invoice_pdf import generate_invoice_pdf
import json
import os
import secrets
import re
from datetime import datetime, timedelta
from passlib.context import CryptContext

# SECURITY CONFIG
EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def require_auth(request: Request, db: Session = Depends(get_db)):
    """Ensure user is logged in"""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        request.session.clear()
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    
    return user

def require_admin(current_user: User = Depends(require_auth)):
    """Ensure user is admin"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def generate_csrf_token():
    return secrets.token_urlsafe(32)

def log_audit_action(db: Session, user_id: int, action: str, entity_type: str = None, 
                     entity_id: int = None, details: str = None, ip_address: str = None):
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address
    )
    db.add(log)
    db.commit()

# APP SETUP
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Umvuzo Media Invoicing System - Secure")

# CSRF Token Middleware
@app.middleware("http")
async def add_csrf_token(request: Request, call_next):
    if "session" in request.scope:
        if "csrf_token" not in request.session:
            request.session["csrf_token"] = generate_csrf_token()
    response = await call_next(request)
    return response

# Security Middleware
SECRET_KEY = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=3600)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

app.add_middleware(SecurityHeadersMiddleware)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# =========================
# AUTH ROUTES
# =========================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "csrf_token": request.session.get("csrf_token", generate_csrf_token())
    })

@app.post("/login")
def login_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    
    if not user or not verify_password(password, user.password):
        request.session["flash"] = "Invalid credentials."
        return RedirectResponse("/login", status_code=303)
    
    user.last_login = datetime.utcnow()
    db.commit()
    
    request.session["user_id"] = user.id
    request.session["csrf_token"] = generate_csrf_token()
    
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {
        "request": request,
        "csrf_token": request.session.get("csrf_token", generate_csrf_token())
    })

@app.post("/forgot-password")
def forgot_password(
    request: Request, 
    username: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    user = db.query(User).filter(User.username == username).first()
    
    flash_message = "If that email exists, a reset link has been sent."
    
    if user:
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used == False
        ).update({"used": True})
        
        token = secrets.token_urlsafe(32)
        reset = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(minutes=30)
        )
        db.add(reset)
        db.commit()
        
        BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
        reset_link = f"{BASE_URL}/reset-password/{token}"
        
        try:
            send_email(
                to_email=user.username,
                subject="Password Reset - Umvuzo Invoicing",
                body=f"""Hello,\n\nClick to reset:\n{reset_link}\n\nExpires in 30 minutes.""",
                pdf_path=None
            )
        except:
            pass
    
    request.session["flash"] = flash_message
    return RedirectResponse("/login", status_code=303)

@app.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_page(request: Request, token: str, db: Session = Depends(get_db)):
    reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.used == False
    ).first()
    
    if not reset or reset.expires_at < datetime.utcnow():
        request.session["flash"] = "Invalid or expired link."
        return RedirectResponse("/login", status_code=303)
    
    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "token": token,
        "csrf_token": request.session.get("csrf_token", generate_csrf_token())
    })

@app.post("/reset-password/{token}")
def reset_password(
    request: Request,
    token: str,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    reset = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == token,
        PasswordResetToken.used == False
    ).first()
    
    if not reset or reset.expires_at < datetime.utcnow():
        request.session["flash"] = "Invalid link."
        return RedirectResponse("/login", status_code=303)
    
    if new_password != confirm_password:
        request.session["flash"] = "Passwords don't match."
        return RedirectResponse(f"/reset-password/{token}", status_code=303)
    
    if len(new_password) < 8:
        request.session["flash"] = "Password too short (min 8)."
        return RedirectResponse(f"/reset-password/{token}", status_code=303)
    
    user = db.query(User).get(reset.user_id)
    user.password = hash_password(new_password)
    reset.used = True
    db.commit()
    
    log_audit_action(db, user.id, "password_reset", ip_address=request.client.host)
    
    request.session["flash"] = "Password reset!"
    return RedirectResponse("/login", status_code=303)

# =========================
# DASHBOARD
# =========================

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        data = {
            "total_quotes": db.query(Quote).count(),
            "approved_quotes": db.query(Quote).filter(Quote.status == "Approved").count(),
            "converted_quotes": db.query(Quote).filter(Quote.converted == True).count(),
            "total_invoices": db.query(Invoice).count(),
            "paid_invoices": db.query(Invoice).filter(Invoice.paid == True).count(),
            "unpaid_invoices": db.query(Invoice).filter(Invoice.paid == False).count(),
        }
    else:
        data = {
            "total_quotes": db.query(Quote).filter(Quote.created_by_id == current_user.id).count(),
            "approved_quotes": db.query(Quote).filter(Quote.created_by_id == current_user.id, Quote.status == "Approved").count(),
            "converted_quotes": db.query(Quote).filter(Quote.created_by_id == current_user.id, Quote.converted == True).count(),
            "total_invoices": db.query(Invoice).filter(Invoice.created_by_id == current_user.id).count(),
            "paid_invoices": db.query(Invoice).filter(Invoice.created_by_id == current_user.id, Invoice.paid == True).count(),
            "unpaid_invoices": db.query(Invoice).filter(Invoice.created_by_id == current_user.id, Invoice.paid == False).count(),
        }
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "current_user": current_user,
        **data
    })

# =========================
# USER MANAGEMENT (Admin Only)
# =========================

@app.get("/users/create", response_class=HTMLResponse)
def create_user_page(request: Request, current_user: User = Depends(require_admin)):
    return templates.TemplateResponse("create_user.html", {
        "request": request,
        "csrf_token": request.session.get("csrf_token"),
        "current_user": current_user
    })

@app.post("/users/create")
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    if not re.match(EMAIL_REGEX, username):
        request.session["flash"] = "Username must be a valid email."
        return RedirectResponse("/users/create", status_code=303)
    
    if len(password) < 8:
        request.session["flash"] = "Password must be at least 8 characters."
        return RedirectResponse("/users/create", status_code=303)
    
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        request.session["flash"] = "User already exists."
        return RedirectResponse("/users/create", status_code=303)
    
    user = User(
        username=username,
        password=hash_password(password),
        role=UserRole.ADMIN if role == "admin" else UserRole.USER
    )
    db.add(user)
    db.commit()
    
    log_audit_action(db, current_user.id, "user_created", "user", user.id, 
                    f"Created {username}", request.client.host)
    
    request.session["flash"] = "User created!"
    return RedirectResponse("/dashboard", status_code=303)

@app.get("/change-password", response_class=HTMLResponse)
def change_password_page(request: Request, current_user: User = Depends(require_auth)):
    return templates.TemplateResponse("change_password.html", {
        "request": request,
        "csrf_token": request.session.get("csrf_token"),
        "current_user": current_user
    })

@app.post("/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    if not verify_password(current_password, current_user.password):
        request.session["flash"] = "Current password is wrong."
        return RedirectResponse("/change-password", status_code=303)
    
    if new_password != confirm_password:
        request.session["flash"] = "Passwords don't match."
        return RedirectResponse("/change-password", status_code=303)
    
    if len(new_password) < 8:
        request.session["flash"] = "Password too short."
        return RedirectResponse("/change-password", status_code=303)
    
    current_user.password = hash_password(new_password)
    db.commit()
    
    log_audit_action(db, current_user.id, "password_changed", ip_address=request.client.host)
    
    request.session["flash"] = "Password updated!"
    return RedirectResponse("/dashboard", status_code=303)

# =========================
# CLIENTS
# =========================

@app.get("/clients-page", response_class=HTMLResponse)
def clients_page(request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        clients = db.query(Client).all()
    else:
        clients = db.query(Client).filter(Client.created_by_id == current_user.id).all()
    
    return templates.TemplateResponse("clients.html", {
        "request": request, 
        "clients": clients,
        "current_user": current_user
    })

@app.get("/clients/create", response_class=HTMLResponse)
def create_client_form(request: Request, current_user: User = Depends(require_auth)):
    return templates.TemplateResponse("create_client.html", {
        "request": request,
        "csrf_token": request.session.get("csrf_token"),
        "current_user": current_user
    })

@app.post("/clients/create")
def create_client(
    request: Request,
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
    csrf_token: str = Form(...),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
      
    try:
        clean_name = re.sub(r'[^A-Za-z]', '', name).upper()
        if len(clean_name) < 3:
            clean_name = (clean_name + "XXX")[:3]
        
        base_code = clean_name[:3]
        existing = db.query(Client).filter(Client.client_code.like(f"{base_code}%")).all()
        
        if existing:
            numbers = []
            for c in existing:
                try:
                    num = int(c.client_code[3:])
                    numbers.append(num)
                except:
                    continue
            next_num = max(numbers) + 1 if numbers else 1
        else:
            next_num = 1
        
        client_code = f"{base_code}{next_num:03d}"
        
        client = Client(
            name=name, email=email, phone=phone, address=address,
            client_code=client_code, billing_name=billing_name,
            billing_email=billing_email, billing_address=billing_address,
            vat_number=vat_number, tax_number=tax_number,
            payment_terms=payment_terms, created_by_id=current_user.id
        )
        db.add(client)
        db.commit()
        
        log_audit_action(db, current_user.id, "client_created", "client", client.id, 
                        f"Created {name} ({client_code})", request.client.host)
        
        request.session["flash"] = f"Client created: {client_code}"
        return RedirectResponse("/clients-page", status_code=303)
        
    except Exception as e:
        db.rollback()
        request.session["flash"] = "Error creating client."
        return RedirectResponse("/clients/create", status_code=303)

@app.get("/clients/{client_id}/edit", response_class=HTMLResponse)
def edit_client_page(client_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return RedirectResponse("/clients-page", status_code=303)
    
    if current_user.role != UserRole.ADMIN and client.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return templates.TemplateResponse("edit_client.html", {
        "request": request, "client": client,
        "csrf_token": request.session.get("csrf_token"),
        "current_user": current_user
    })

@app.post("/clients/{client_id}/edit")
def update_client(
    client_id: int, request: Request, name: str = Form(...),
    email: str = Form(...), phone: str = Form(...), address: str = Form(None),
    billing_name: str = Form(None), billing_email: str = Form(None),
    billing_address: str = Form(None), vat_number: str = Form(None),
    tax_number: str = Form(None), payment_terms: str = Form(None),
    csrf_token: str = Form(...), current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return RedirectResponse("/clients-page", status_code=303)
    
    if current_user.role != UserRole.ADMIN and client.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
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
    log_audit_action(db, current_user.id, "client_updated", "client", client.id, 
                    f"Updated {name}", request.client.host)
    
    return RedirectResponse("/clients-page", status_code=303)

@app.get("/clients/{client_id}", response_class=HTMLResponse)
def client_history(client_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        return RedirectResponse("/clients-page")
    
    if current_user.role != UserRole.ADMIN and client.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if current_user.role == UserRole.ADMIN:
        quotes = db.query(Quote).filter(Quote.client_id == client_id).all()
        invoices = db.query(Invoice).filter(Invoice.client_id == client_id).all()
    else:
        quotes = db.query(Quote).filter(Quote.client_id == client_id, Quote.created_by_id == current_user.id).all()
        invoices = db.query(Invoice).filter(Invoice.client_id == client_id, Invoice.created_by_id == current_user.id).all()
    
    return templates.TemplateResponse("client_history.html", {
        "request": request, "client": client, "quotes": quotes,
        "invoices": invoices, "current_user": current_user
    })

# =========================
# QUOTES
# =========================

@app.get("/quotes-page", response_class=HTMLResponse)
def quotes_page(request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        quotes = db.query(Quote).options(joinedload(Quote.items), joinedload(Quote.client)).all()
    else:
        quotes = db.query(Quote).filter(Quote.created_by_id == current_user.id).options(
            joinedload(Quote.items), joinedload(Quote.client)).all()
    
    return templates.TemplateResponse("quotes.html", {
        "request": request, "quotes": quotes, "current_user": current_user
    })

@app.get("/quotes/create", response_class=HTMLResponse)
def create_quote_form(request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        clients = db.query(Client).all()
    else:
        clients = db.query(Client).filter(Client.created_by_id == current_user.id).all()
    
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.name).all()
    
    return templates.TemplateResponse("create_quote.html", {
        "request": request, "clients": clients, "services": services,
        "csrf_token": request.session.get("csrf_token"), "current_user": current_user
    })

@app.post("/quotes/create")
def create_quote(
    request: Request, client_id: int = Form(...), items_data: str = Form(...),
    csrf_token: str = Form(...), current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client or (current_user.role != UserRole.ADMIN and client.created_by_id != current_user.id):
        raise HTTPException(status_code=403, detail="Invalid client")
    
    try:
        items = json.loads(items_data)
        if not items:
            request.session["flash"] = "Add at least one item."
            return RedirectResponse("/quotes/create", status_code=303)
    except:
        request.session["flash"] = "Invalid data."
        return RedirectResponse("/quotes/create", status_code=303)
    
    try:
        last = db.query(func.max(Quote.quote_number)).filter(Quote.client_id == client_id).scalar()
        next_num = 1 if not last else last + 1
        
        quote = Quote(
            quote_number=next_num, client_id=client_id, total=0,
            status="Draft", converted=False, created_by_id=current_user.id
        )
        db.add(quote)
        db.flush()
        
        total = 0
        for item in items:
            line = float(item["unit_cost"]) * float(item["quantity"])
            total += line
            db.add(QuoteItem(
                quote_id=quote.id, description=item["description"],
                unit_cost=float(item["unit_cost"]), quantity=float(item["quantity"])
            ))
        
        quote.total = total
        db.commit()
        
        log_audit_action(db, current_user.id, "quote_created", "quote", quote.id, 
                        f"Q-{next_num:04d} for {client.name}", request.client.host)
        return RedirectResponse("/quotes-page", status_code=303)
    except:
        db.rollback()
        request.session["flash"] = "Error creating quote."
        return RedirectResponse("/quotes/create", status_code=303)

@app.get("/quotes/{quote_id}/convert")
def convert_quote(quote_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).with_for_update().first()
    
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    
    if current_user.role != UserRole.ADMIN and quote.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if quote.converted:
        request.session["flash"] = "Already converted."
        return RedirectResponse("/quotes-page", status_code=303)
    
    if quote.status != "Approved":
        request.session["flash"] = "Quote must be approved first."
        return RedirectResponse("/quotes-page", status_code=303)
    
    try:
        last_inv = db.query(func.max(Invoice.invoice_number)).filter(Invoice.client_id == quote.client_id).scalar()
        next_inv = 1 if not last_inv else last_inv + 1
        
        invoice = Invoice(
            invoice_number=next_inv, client_id=quote.client_id,
            total=0, paid=False, created_by_id=current_user.id
        )
        db.add(invoice)
        db.flush()
        
        quote_items = db.query(QuoteItem).filter(QuoteItem.quote_id == quote.id).all()
        total = 0
        for item in quote_items:
            line = item.unit_cost * item.quantity
            total += line
            db.add(InvoiceItem(
                invoice_id=invoice.id, description=item.description,
                unit_cost=item.unit_cost, quantity=item.quantity
            ))
        
        invoice.total = total
        quote.converted = True
        db.commit()
        
        log_audit_action(db, current_user.id, "quote_converted", "invoice", invoice.id, 
                        f"Q-{quote.quote_number:04d} to INV-{next_inv:04d}", request.client.host)
        return RedirectResponse("/invoices-page", status_code=303)
    except:
        db.rollback()
        request.session["flash"] = "Error converting."
        return RedirectResponse("/quotes-page", status_code=303)

@app.get("/quotes/{quote_id}/pdf")
def quote_pdf(quote_id: int, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    quote = db.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Not found")
    
    if current_user.role != UserRole.ADMIN and quote.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    client = db.get(Client, quote.client_id)
    items = db.query(QuoteItem).filter(QuoteItem.quote_id == quote.id).all()
    filename = f"quote_{quote.id}.pdf"
    generate_quote_pdf(quote, client, items, filename)
    return FileResponse(filename, media_type="application/pdf", filename=filename)

@app.get("/quotes/{quote_id}/email")
def email_quote(quote_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        return RedirectResponse("/quotes-page", status_code=303)
    
    if current_user.role != UserRole.ADMIN and quote.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        items = db.query(QuoteItem).filter(QuoteItem.quote_id == quote.id).all()
        filename = f"quote_{quote.quote_number}.pdf"
        generate_quote_pdf(quote, quote.client, items, filename)
        
        send_email(
            quote.client.email,
            f"Quote #{quote.quote_number:04d}",
            f"Dear {quote.client.name},\n\nPlease find your quote attached.\n\nTotal: R {quote.total:.2f}",
            filename
        )
        
        request.session["flash"] = "Quote emailed!"
        log_audit_action(db, current_user.id, "quote_emailed", "quote", quote.id, 
                        f"To {quote.client.email}", request.client.host)
    except Exception as e:
        request.session["flash"] = f"Email failed: {str(e)}"
    
    return RedirectResponse("/quotes-page", status_code=303)

@app.get("/quotes/{quote_id}/approved")
def approve_quote(quote_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Not found")
    
    if current_user.role != UserRole.ADMIN and quote.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    quote.status = "Approved"
    db.commit()
    log_audit_action(db, current_user.id, "quote_approved", "quote", quote.id, ip_address=request.client.host)
    return RedirectResponse("/quotes-page", status_code=303)

@app.get("/quotes/{quote_id}/sent")
def mark_sent(quote_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Not found")
    
    if current_user.role != UserRole.ADMIN and quote.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    quote.status = "Sent"
    db.commit()
    log_audit_action(db, current_user.id, "quote_sent", "quote", quote.id, ip_address=request.client.host)
    return RedirectResponse("/quotes-page", status_code=303)

# =========================
# INVOICES
# =========================

@app.get("/invoices-page", response_class=HTMLResponse)
def invoices_page(request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    if current_user.role == UserRole.ADMIN:
        invoices = db.query(Invoice).options(joinedload(Invoice.items), joinedload(Invoice.client)).all()
    else:
        invoices = db.query(Invoice).filter(Invoice.created_by_id == current_user.id).options(
            joinedload(Invoice.items), joinedload(Invoice.client)).all()
    
    return templates.TemplateResponse("invoices.html", {
        "request": request, "invoices": invoices, "current_user": current_user
    })

@app.get("/invoices/{invoice_id}/paid")
def mark_paid(invoice_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Not found")
    
    if current_user.role != UserRole.ADMIN and invoice.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not invoice.paid:
        invoice.paid = True
        invoice.paid_at = datetime.utcnow()
        invoice.marked_paid_by_id = current_user.id
        db.commit()
        log_audit_action(db, current_user.id, "invoice_marked_paid", "invoice", invoice.id, ip_address=request.client.host)
    
    return RedirectResponse("/invoices-page", status_code=303)

@app.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Not found")
    
    if current_user.role != UserRole.ADMIN and invoice.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    client = db.get(Client, invoice.client_id)
    items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).all()
    filename = f"invoice_{invoice.id}.pdf"
    generate_invoice_pdf(invoice, client, items, filename, client.client_code)
    return FileResponse(filename, media_type="application/pdf", filename=filename)

@app.get("/invoices/{invoice_id}/email")
def email_invoice(request: Request, invoice_id: int, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Not found")
    
    if current_user.role != UserRole.ADMIN and invoice.created_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    client = db.get(Client, invoice.client_id)
    items = db.query(InvoiceItem).filter(InvoiceItem.invoice_id == invoice.id).all()
    filename = f"invoice_{invoice.id}.pdf"
    generate_invoice_pdf(invoice, client, items, filename, client.client_code)
    
    try:
        send_email(
            to_email=client.email,
            subject=f"Invoice {client.client_code}-INV-{invoice.invoice_number:04d}",
            body=f"Dear {client.name},\n\nPlease find invoice attached.\n\nTotal: R {invoice.total:.2f}\n{'PAID' if invoice.paid else 'PENDING'}",
            pdf_path=filename
        )
        request.session["flash"] = "Invoice emailed!"
        log_audit_action(db, current_user.id, "invoice_emailed", "invoice", invoice.id, 
                        f"To {client.email}", request.client.host)
    except Exception as e:
        request.session["flash"] = f"Email failed: {str(e)}"
    
    return RedirectResponse("/invoices-page", status_code=303)

# =========================
# SERVICES
# =========================

@app.get("/services", response_class=HTMLResponse)
def services_page(request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    services = db.query(Service).filter(Service.is_active == True).order_by(Service.category, Service.name).all()
    return templates.TemplateResponse("services.html", {
        "request": request, "services": services,
        "current_user": current_user, "csrf_token": request.session.get("csrf_token")
    })

@app.post("/services/create")
def create_service(
    request: Request, name: str = Form(...), description: str = Form(...),
    price: float = Form(...), category: str = Form(...),
    csrf_token: str = Form(...), current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    service = Service(name=name, description=description, price=price, category=category, is_active=True)
    db.add(service)
    db.commit()
    log_audit_action(db, current_user.id, "service_created", "service", service.id, name, request.client.host)
    return RedirectResponse("/services", status_code=303)

@app.get("/services/{service_id}/edit", response_class=HTMLResponse)
def edit_service_page(service_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id, Service.is_active == True).first()
    if not service:
        return RedirectResponse("/services", status_code=303)
    return templates.TemplateResponse("edit_service.html", {
        "request": request, "service": service,
        "current_user": current_user, "csrf_token": request.session.get("csrf_token")
    })

@app.post("/services/{service_id}/edit")
def update_service(
    service_id: int, request: Request, name: str = Form(...),
    description: str = Form(...), price: float = Form(...), category: str = Form(...),
    csrf_token: str = Form(...), current_user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    if csrf_token != request.session.get("csrf_token"):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    service = db.query(Service).filter(Service.id == service_id).first()
    if not service:
        return RedirectResponse("/services", status_code=303)
    
    service.name = name
    service.description = description
    service.price = price
    service.category = category
    db.commit()
    log_audit_action(db, current_user.id, "service_updated", "service", service.id, ip_address=request.client.host)
    return RedirectResponse("/services", status_code=303)

@app.get("/services/{service_id}/delete")
def delete_service(service_id: int, request: Request, current_user: User = Depends(require_auth), db: Session = Depends(get_db)):
    service = db.query(Service).filter(Service.id == service_id).first()
    if service:
        service.is_active = False
        db.commit()
        log_audit_action(db, current_user.id, "service_deleted", "service", service.id, service.name, request.client.host)
        request.session["flash"] = "Service removed."
    return RedirectResponse("/services", status_code=303)

# =========================
# INITIALIZATION
# =========================

def create_default_admin():
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if not existing:
            username = os.getenv("ADMIN_USER")
            password = os.getenv("ADMIN_PASS")
            if username and password:
                admin = User(username=username, password=hash_password(password), role=UserRole.ADMIN)
                db.add(admin)
                db.commit()
                print(f"Admin created: {username}")
            else:
                print("Set ADMIN_USER and ADMIN_PASS in .env")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

def seed_services():
    db = SessionLocal()
    try:
        if db.query(Service).filter(Service.is_active == True).first():
            return
        
        services = [
            {"name": "IT Consultation", "description": "General IT consultation", "price": 450.0, "category": "Consulting"},
            {"name": "Remote Support", "description": "Remote troubleshooting", "price": 350.0, "category": "Support"},
            {"name": "Onsite Support", "description": "Onsite technical assistance", "price": 650.0, "category": "Support"},
            {"name": "Router Setup", "description": "Router installation", "price": 650.0, "category": "Networking"},
            {"name": "Network Cabling", "description": "Structured cabling", "price": 300.0, "category": "Networking"},
            {"name": "CCTV Installation", "description": "CCTV installation", "price": 1200.0, "category": "Security"},
            {"name": "Access Control", "description": "Access control setup", "price": 1800.0, "category": "Security"},
            {"name": "Microsoft 365", "description": "Email setup", "price": 950.0, "category": "Cloud"},
            {"name": "Server Setup", "description": "Server installation", "price": 2500.0, "category": "Infrastructure"},
        ]
        for s in services:
            db.add(Service(**s, is_active=True))
        db.commit()
        print("Services seeded.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

@app.on_event("startup")
async def startup_event():
    create_default_admin()
    seed_services()