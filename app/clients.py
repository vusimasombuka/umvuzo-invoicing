from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Client

router = APIRouter(prefix="/clients", tags=["Clients"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/")
def create_client(name: str, email: str = None, phone: str = None, address: str = None, db: Session = Depends(get_db)):
    client = Client(
        name=name,
        email=email,
        phone=phone,
        address=address
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client

@router.get("/")
def list_clients(db: Session = Depends(get_db)):
    return db.query(Client).all()
