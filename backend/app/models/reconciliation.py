"""
app/models/reconciliation.py
Monthly Inventory Reconciliation Models
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Numeric,
    ForeignKey, Text, Date, Enum, Float
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum as PyEnum
import uuid

from app.db.base import Base
from app.db.mixins import TenantMixin

class ReconciliationStatus(str, PyEnum):
    DRAFT = "draft"                        # Period created, not yet submitted
    IN_PROGRESS = "in_progress"            # Physical count being entered
    PENDING_APPROVAL = "pending_approval"  # Submitted, awaiting manager sign-off
    APPROVED = "approved"                  # Manager approved, adjustments applied
    CLOSED = "closed"                      # Finalized, no further changes allowed
    REJECTED = "rejected"                  # Sent back for re-count


class VarianceStatus(str, PyEnum):
    WITHIN_THRESHOLD = "within_threshold"  # Acceptable variance
    EXCEEDS_THRESHOLD = "exceeds_threshold"  # Requires investigation
    INVESTIGATED = "investigated"          # Manager reviewed
    ADJUSTED = "adjusted"                  # Adjustment transaction created


class CostingMethod(str, PyEnum):
    WEIGHTED_AVERAGE = "weighted_average"
    FIFO = "fifo"


class AdjustmentReason(str, PyEnum):
    PHYSICAL_COUNT_VARIANCE = "physical_count_variance"
    DAMAGE = "damage"
    THEFT = "theft"
    EXPIRY = "expiry"
    DATA_ENTRY_ERROR = "data_entry_error"
    OTHER = "other"

class ReconciliationPeriod(TenantMixin, Base):
    """
    Represents a single reconciliation cycle (typically one calendar month).
    One period per (tenant, year, month).
    """
    __tablename__ = "reconciliation_periods"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Period definition
    period_year = Column(Integer, nullable=False)      # e.g. 2025
    period_month = Column(Integer, nullable=False)     # 1-12
    period_start_date = Column(Date, nullable=False)
    period_end_date = Column(Date, nullable=False)

    status = Column(
        Enum(ReconciliationStatus, name="reconciliation_status"),
        default=ReconciliationStatus.DRAFT,
        nullable=False,
    )

    costing_method = Column(
        Enum(CostingMethod, name="costing_method"),
        default=CostingMethod.WEIGHTED_AVERAGE,
        nullable=False,
    )

    # Variance threshold — percentage above which a variance requires investigation
    variance_threshold_pct = Column(Numeric(5, 2), default=5.00)

    # Workflow metadata
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Summary totals (denormalized for fast reporting)
    total_opening_value = Column(Numeric(15, 2), default=0)
    total_purchases_value = Column(Numeric(15, 2), default=0)
    total_consumption_value = Column(Numeric(15, 2), default=0)
    total_wastage_value = Column(Numeric(15, 2), default=0)
    total_adjustment_value = Column(Numeric(15, 2), default=0)
    total_theoretical_closing_value = Column(Numeric(15, 2), default=0)
    total_physical_closing_value = Column(Numeric(15, 2), default=0)
    total_variance_value = Column(Numeric(15, 2), default=0)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    created_by = relationship("User", foreign_keys=[user_id])
    submitted_by = relationship("User", foreign_keys=[submitted_by_user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    line_items = relationship(
        "ReconciliationLineItem",
        back_populates="period",
        cascade="all, delete-orphan",
    )
    physical_counts = relationship(
        "PhysicalCount",
        back_populates="period",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ReconciliationPeriod {self.period_year}-{self.period_month:02d} [{self.status}]>"

class ReconciliationLineItem(TenantMixin, Base):
    """
    Summarized movement for a single inventory item within a reconciliation period.
    Theoretical closing = opening + purchases - consumption - wastage ± adjustments
    Variance = physical_closing - theoretical_closing
    """
    __tablename__ = "reconciliation_line_items"

    id = Column(Integer, primary_key=True, index=True)
    period_id = Column(
        Integer, ForeignKey("reconciliation_periods.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    inventory_item_id = Column(
        Integer, ForeignKey("inventory.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Snapshot of item details at time of reconciliation
    item_name = Column(String(255), nullable=False)
    item_sku = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    item_category = Column(String(100), nullable=True)

    # Quantities
    opening_quantity = Column(Numeric(12, 3), default=0)
    purchases_quantity = Column(Numeric(12, 3), default=0)
    consumption_quantity = Column(Numeric(12, 3), default=0)
    wastage_quantity = Column(Numeric(12, 3), default=0)
    adjustment_quantity = Column(Numeric(12, 3), default=0)   # manual ± adjustments
    theoretical_closing_quantity = Column(Numeric(12, 3), default=0)
    physical_closing_quantity = Column(Numeric(12, 3), nullable=True)  # from physical count
    variance_quantity = Column(Numeric(12, 3), nullable=True)          # physical - theoretical

    # Values (monetary)
    unit_cost = Column(Numeric(10, 2), default=0)              # WAC or FIFO cost
    opening_value = Column(Numeric(15, 2), default=0)
    purchases_value = Column(Numeric(15, 2), default=0)
    consumption_value = Column(Numeric(15, 2), default=0)
    wastage_value = Column(Numeric(15, 2), default=0)
    adjustment_value = Column(Numeric(15, 2), default=0)
    theoretical_closing_value = Column(Numeric(15, 2), default=0)
    physical_closing_value = Column(Numeric(15, 2), nullable=True)
    variance_value = Column(Numeric(15, 2), nullable=True)

    # Variance tracking
    variance_pct = Column(Numeric(8, 4), nullable=True)        # abs(variance/theoretical)*100
    variance_status = Column(
        Enum(VarianceStatus, name="variance_status"),
        default=VarianceStatus.WITHIN_THRESHOLD,
    )
    variance_notes = Column(Text, nullable=True)

    # Adjustment transaction reference (created on approval)
    adjustment_transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventory_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    period = relationship("ReconciliationPeriod", back_populates="line_items")
    inventory_item = relationship("Inventory")
    adjustment_transaction = relationship("InventoryTransaction", foreign_keys=[adjustment_transaction_id])

class PhysicalCount(TenantMixin, Base):
    """
    Records the raw physical stock-count entries entered by staff during
    the opening or closing stocktake for a reconciliation period.
    Multiple count entries per item are allowed (e.g. counted by different users)
    and then consolidated into ReconciliationLineItem.physical_closing_quantity.
    """
    __tablename__ = "physical_counts"

    id = Column(Integer, primary_key=True, index=True)
    period_id = Column(
        Integer, ForeignKey("reconciliation_periods.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    inventory_item_id = Column(
        Integer, ForeignKey("inventory.id", ondelete="SET NULL"),
        nullable=True,
    )
    counted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    count_type = Column(String(20), nullable=False)  # "opening" | "closing"
    counted_quantity = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(50), nullable=True)
    storage_location = Column(String(100), nullable=True)
    batch_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    counted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    period = relationship("ReconciliationPeriod", back_populates="physical_counts")
    inventory_item = relationship("Inventory")
    counted_by = relationship("User")

class ReconciliationAdjustment(TenantMixin, Base):
    """
    Audit trail for every manual adjustment made during or after reconciliation.
    Each adjustment links back to a line item and optionally to an InventoryTransaction.
    """
    __tablename__ = "reconciliation_adjustments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_id = Column(
        Integer, ForeignKey("reconciliation_periods.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_item_id = Column(
        Integer, ForeignKey("reconciliation_line_items.id", ondelete="CASCADE"),
        nullable=True,
    )
    inventory_item_id = Column(
        Integer, ForeignKey("inventory.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    reason = Column(
        Enum(AdjustmentReason, name="adjustment_reason"),
        nullable=False,
    )
    quantity_adjusted = Column(Numeric(12, 3), nullable=False)   # positive = stock added, negative = removed
    unit_cost = Column(Numeric(10, 2), nullable=True)
    value_adjusted = Column(Numeric(15, 2), nullable=True)
    notes = Column(Text, nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Linked inventory transaction created on approval
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("inventory_transactions.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    period = relationship("ReconciliationPeriod")
    line_item = relationship("ReconciliationLineItem")
    inventory_item = relationship("Inventory")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])
    transaction = relationship("InventoryTransaction", foreign_keys=[transaction_id])

class ReconciliationConfig(TenantMixin, Base):
    """
    Tenant-level configuration for reconciliation behaviour.
    """
    __tablename__ = "reconciliation_configs"

    id = Column(Integer, primary_key=True)
    costing_method = Column(
        Enum(CostingMethod, name="costing_method"),
        default=CostingMethod.WEIGHTED_AVERAGE,
    )
    default_variance_threshold_pct = Column(Numeric(5, 2), default=5.00)
    require_manager_approval = Column(Boolean, default=True)
    auto_close_on_approval = Column(Boolean, default=True)
    # Roles allowed to approve
    approver_role = Column(String(50), default="manager")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())