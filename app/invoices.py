from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import SessionLocal
from app.models import Invoice
from fastapi import FastAPI, HTTPException
from starlette.responses import RedirectResponse

router = APIRouter(prefix="/invoices", tags=["Invoices"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_next_invoice_number(db: Session):
    last = db.query(func.max(Invoice.invoice_number)).scalar()
    return 1 if last is None else last + 1

@router.post("/")
def create_invoice(client_id: int, items: str, total: float, db: Session = Depends(get_db)):
    invoice = Invoice(
        invoice_number=get_next_invoice_number(db),
        client_id=client_id,
        items=items,
        total=total
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice

@router.get("/")
def list_invoices(db: Session = Depends(get_db)):
    return db.query(Invoice).all()

@router.get("/invoices/{invoice_id}/paid")
def mark_paid(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).get(invoice_id)
    invoice.paid = True
    db.commit()
    return RedirectResponse("/invoices-page", status_code=303)



