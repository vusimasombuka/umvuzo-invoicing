from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey, Float, Boolean, Enum)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime
import enum

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"

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
    
    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    created_by = relationship("User", foreign_keys=[created_by_id])

class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    quote_number = Column(Integer, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    total = Column(Float)
    status = Column(String, default="Draft")
    converted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    
    client = relationship("Client")
    items = relationship("QuoteItem", cascade="all, delete")
    created_by = relationship("User")

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
    paid_at = Column(DateTime(timezone=True), nullable=True)
    
    # Audit fields
    created_by_id = Column(Integer, ForeignKey("users.id"))
    marked_paid_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    client = relationship("Client")
    items = relationship("InvoiceItem", cascade="all, delete")
    created_by = relationship("User", foreign_keys=[created_by_id])
    marked_paid_by = relationship("User", foreign_keys=[marked_paid_by_id])

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
    role = Column(Enum(UserRole), default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    token = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    used = Column(Boolean, default=False)
    
    user = relationship("User")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String)
    entity_id = Column(Integer)
    details = Column(String)
    ip_address = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User")