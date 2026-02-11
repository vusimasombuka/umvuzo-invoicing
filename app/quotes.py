from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models import Quote

router = APIRouter(prefix="/quotes", tags=["Quotes"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_next_quote_number(db: Session):
    last = db.query(func.max(Quote.quote_number)).scalar()
    return 1 if last is None else last + 1

@router.post("/")
def create_quote(client_id: int, items: str, total: float, db: Session = Depends(get_db)):
    quote = Quote(
        quote_number=get_next_quote_number(db),
        client_id=client_id,
        items=items,
        total=total
    )
    db.add(quote)
    db.commit()
    db.refresh(quote)
    return quote

@router.get("/")
def list_quotes(db: Session = Depends(get_db)):
    return db.query(Quote).all()
