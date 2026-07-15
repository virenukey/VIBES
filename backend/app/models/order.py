"""
app/models/order.py
Order Management Models
"""
from sqlalchemy import  Column, Integer, String, DateTime, Boolean, Numeric,ForeignKey, Text, Date, CheckConstraint, Index, Enum,Float
from datetime import datetime
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from app.db.base import Base
from sqlalchemy.orm import relationship
from app.db.mixins import TenantMixin
from sqlalchemy.dialects.postgresql import UUID
import uuid

class OrderStatus(PyEnum):
    """Order lifecycle status"""
    PENDING = "PENDING"              # Order received, not yet confirmed
    CONFIRMED = "CONFIRMED"          # Order confirmed, waiting to prepare
    PREPARING = "PREPARING"          # Currently being prepared in kitchen
    READY = "READY"                  # Ready for serving/pickup/delivery
    SERVED = "SERVED"                # Served to customer (dine-in)
    COMPLETED = "COMPLETED"          # Order completed and paid
    CANCELLED = "CANCELLED"          # Order cancelled
    REFUNDED = "REFUNDED"            # Order refunded

class OrderType(PyEnum):
    """Type of order"""
    DINE_IN = "DINE_IN"
    TAKEAWAY = "TAKEAWAY"
    DELIVERY = "DELIVERY"
    CATERING = "CATERING"

class PaymentStatus(PyEnum):
    """Payment status"""
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    REFUNDED = "REFUNDED"
    CANCELLED = "CANCELLED"

class PaymentMethod(PyEnum):
    """Payment methods"""
    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    WALLET = "WALLET"
    BANK_TRANSFER = "BANK_TRANSFER"
    OTHER = "OTHER"

class Order(TenantMixin,Base):
    """Main order table"""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)    
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    order_type = Column(Enum(OrderType), nullable=False, default=OrderType.DINE_IN)
    
    # Customer information
    customer_name = Column(String(100))
    customer_phone = Column(String(20))
    customer_email = Column(String(100))
    table_number = Column(String(20))  # For dine-in
    delivery_address = Column(Text)     # For delivery
    order_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    
    # Financial
    subtotal = Column(Numeric(10, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(10, 2), default=0)
    discount_amount = Column(Numeric(10, 2), default=0)
    delivery_charge = Column(Numeric(10, 2), default=0)
    total_amount = Column(Numeric(10, 2), nullable=False, default=0)
    
    # Payment
    payment_status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    paid_amount = Column(Numeric(10, 2), default=0)
    
    # Staff
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    served_by = Column(Integer, ForeignKey("users.id"))
    
    # Timing
    estimated_preparation_time = Column(Integer)  # in minutes
    preparation_started_at = Column(DateTime)
    ready_at = Column(DateTime)
    served_at = Column(DateTime)
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    
    # Additional
    notes = Column(Text)
    cancellation_reason = Column(Text)
    special_instructions = Column(Text)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("OrderPayment", back_populates="order", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by])
    server = relationship("User", foreign_keys=[served_by])
    packaging_items = relationship("OrderPackaging", back_populates="order", cascade="all, delete-orphan")
    
class OrderItem(TenantMixin,Base):
    """Individual items in an order"""
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    dish_id = Column(Integer, ForeignKey("dishes.id"), nullable=False)
    dish_name = Column(String(100), nullable=False)  # Snapshot of dish name
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    discount_amount = Column(Numeric(10, 2), default=0)
    total_price = Column(Numeric(10, 2), nullable=False)
    status = Column(Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING)
    preparation_log_id = Column(Integer, ForeignKey("dish_preparation_batch_logs.id"))
    prepared_at = Column(DateTime)
    special_instructions = Column(Text)    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order = relationship("Order", back_populates="items")
    dish = relationship("Dish")
    preparation_log = relationship("DishPreparationBatchLog")


class OrderPayment(TenantMixin,Base):
    """Payment transactions for orders"""
    __tablename__ = "order_payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    transaction_id = Column(String(100))  # External payment gateway transaction ID
    reference_number = Column(String(100))
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    notes = Column(Text)
    processed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    order = relationship("Order", back_populates="payments")
    processor = relationship("User")


class OrderStatusHistory(TenantMixin,Base):
    """Track order status changes"""
    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    from_status = Column(Enum(OrderStatus))
    to_status = Column(Enum(OrderStatus), nullable=False)
    changed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    changed_by = Column(Integer, ForeignKey("users.id"))
    
    # Additional info
    notes = Column(Text)
    
    # Relationships
    user = relationship("User")

class OrderPackaging(TenantMixin, Base):
    """Packaging items used for takeaway/delivery orders"""
    __tablename__ = "order_packaging"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    inventory_item_id = Column(Integer, ForeignKey("inventory.id"), nullable=False)
    item_name = Column(String(100), nullable=False)  # Snapshot
    quantity = Column(Integer, nullable=False, default=1)
    unit_cost = Column(Numeric(10, 2), default=0)
    total_cost = Column(Numeric(10, 2), default=0)    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    order = relationship("Order", back_populates="packaging_items")
    inventory_item = relationship("Inventory")    