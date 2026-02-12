from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Float,
    Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    quote_number = Column(Integer, unique=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    items = Column(String)  # simple for now
    total = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client")
    status = Column(String, default="Draft")
    converted = Column(Boolean, default=False)


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"))
    description = Column(String, nullable=False)
    unit_cost = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)

    quote = relationship("Quote")



class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(Integer, unique=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    items = Column(String)
    total = Column(Float)
    paid = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client")


from sqlalchemy import Column, Integer, String
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)

class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    description = Column(String, nullable=False)
    unit_cost = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)

    invoice = relationship("Invoice")


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    description = Column(String)
    price = Column(Float)
    category = Column(String)
