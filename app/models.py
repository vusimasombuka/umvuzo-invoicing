from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey, Float, Boolean)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime

class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    address = Column(String)

    client_code = Column(String, unique=True, index=True)

    # Billing Details
    billing_name = Column(String)
    billing_email = Column(String)
    billing_address = Column(String)
    vat_number = Column(String)
    tax_number = Column(String)
    payment_terms = Column(String)



class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    quote_number = Column(Integer, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    total = Column(Float)
    status = Column(String, default="Draft")
    converted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client")
    items = relationship("QuoteItem", cascade="all, delete")


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"))
    description = Column(String, nullable=False)
    unit_cost = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)

    quote = relationship("Quote")



class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(Integer, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    total = Column(Float)
    paid = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client")
    items = relationship("InvoiceItem", cascade="all, delete")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    description = Column(String, nullable=False)
    unit_cost = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)

    invoice = relationship("Invoice")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)


class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    category = Column(String, nullable=False)

    
    
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)