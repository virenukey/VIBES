"""
app/schemas/reconciliation.py
Pydantic schemas for the Reconciliation module
"""
from pydantic import BaseModel, validator, Field
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

class ReconciliationStatusEnum(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    CLOSED = "closed"
    REJECTED = "rejected"


class VarianceStatusEnum(str, Enum):
    WITHIN_THRESHOLD = "within_threshold"
    EXCEEDS_THRESHOLD = "exceeds_threshold"
    INVESTIGATED = "investigated"
    ADJUSTED = "adjusted"


class CostingMethodEnum(str, Enum):
    WEIGHTED_AVERAGE = "weighted_average"
    FIFO = "fifo"


class AdjustmentReasonEnum(str, Enum):
    PHYSICAL_COUNT_VARIANCE = "physical_count_variance"
    DAMAGE = "damage"
    THEFT = "theft"
    EXPIRY = "expiry"
    DATA_ENTRY_ERROR = "data_entry_error"
    OTHER = "other"


class CountTypeEnum(str, Enum):
    OPENING = "opening"
    CLOSING = "closing"

class ReconciliationPeriodCreate(BaseModel):
    period_year: int = Field(..., ge=2020, le=2100)
    period_month: int = Field(..., ge=1, le=12)
    costing_method: CostingMethodEnum = CostingMethodEnum.WEIGHTED_AVERAGE
    variance_threshold_pct: Optional[Decimal] = Field(default=Decimal("5.00"), ge=0, le=100)
    notes: Optional[str] = None
    tenant_id: Optional[int] = None


class ReconciliationPeriodUpdate(BaseModel):
    variance_threshold_pct: Optional[Decimal] = None
    notes: Optional[str] = None
    costing_method: Optional[CostingMethodEnum] = None


class ReconciliationPeriodOut(BaseModel):
    id: int
    period_year: int
    period_month: int
    period_start_date: date
    period_end_date: date
    status: ReconciliationStatusEnum
    costing_method: CostingMethodEnum
    variance_threshold_pct: Optional[Decimal]
    total_opening_value: Optional[Decimal]
    total_purchases_value: Optional[Decimal]
    total_consumption_value: Optional[Decimal]
    total_wastage_value: Optional[Decimal]
    total_adjustment_value: Optional[Decimal]
    total_theoretical_closing_value: Optional[Decimal]
    total_physical_closing_value: Optional[Decimal]
    total_variance_value: Optional[Decimal]
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    rejection_reason: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class ReconciliationPeriodListItem(BaseModel):
    id: int
    period_year: int
    period_month: int
    status: ReconciliationStatusEnum
    total_variance_value: Optional[Decimal]
    total_physical_closing_value: Optional[Decimal]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

class PhysicalCountEntry(BaseModel):
    inventory_item_id: int
    count_type: CountTypeEnum
    counted_quantity: Decimal = Field(..., gt=0)
    unit: Optional[str] = None
    storage_location: Optional[str] = None
    batch_number: Optional[str] = None
    notes: Optional[str] = None


class PhysicalCountBulkCreate(BaseModel):
    """Submit multiple physical count entries at once (typical for stocktake)"""
    counts: List[PhysicalCountEntry]


class PhysicalCountOut(BaseModel):
    id: int
    inventory_item_id: Optional[int]
    item_name: Optional[str] = None      # resolved in service
    count_type: str
    counted_quantity: Decimal
    unit: Optional[str]
    storage_location: Optional[str]
    batch_number: Optional[str]
    notes: Optional[str]
    counted_at: datetime

    class Config:
        from_attributes = True

class PhysicalCountUpdate(BaseModel):
    """Update physical closing quantity for a specific line item"""
    physical_closing_quantity: Decimal = Field(..., ge=0)
    variance_notes: Optional[str] = None

class LineItemOut(BaseModel):
    id: int
    inventory_item_id: Optional[int]
    item_name: str
    item_sku: Optional[str]
    unit: Optional[str]
    item_category: Optional[str]
    opening_quantity: Optional[Decimal]
    purchases_quantity: Optional[Decimal]
    consumption_quantity: Optional[Decimal]
    wastage_quantity: Optional[Decimal]
    adjustment_quantity: Optional[Decimal]
    theoretical_closing_quantity: Optional[Decimal]
    physical_closing_quantity: Optional[Decimal]
    variance_quantity: Optional[Decimal]
    unit_cost: Optional[Decimal]
    opening_value: Optional[Decimal]
    purchases_value: Optional[Decimal]
    consumption_value: Optional[Decimal]
    wastage_value: Optional[Decimal]
    theoretical_closing_value: Optional[Decimal]
    physical_closing_value: Optional[Decimal]
    variance_value: Optional[Decimal]
    variance_pct: Optional[Decimal]
    variance_status: Optional[VarianceStatusEnum]
    variance_notes: Optional[str]

    class Config:
        from_attributes = True

class AdjustmentCreate(BaseModel):
    inventory_item_id: int
    reason: AdjustmentReasonEnum
    quantity_adjusted: Decimal       # positive = add, negative = remove
    notes: Optional[str] = None


class AdjustmentOut(BaseModel):
    id: str
    inventory_item_id: Optional[int]
    reason: AdjustmentReasonEnum
    quantity_adjusted: Decimal
    unit_cost: Optional[Decimal]
    value_adjusted: Optional[Decimal]
    notes: Optional[str]
    approved_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True

class SubmitForApprovalRequest(BaseModel):
    notes: Optional[str] = None


class ApproveRequest(BaseModel):
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    rejection_reason: str

class MonthlySummaryReport(BaseModel):
    period_id: int
    period_label: str                    # e.g. "March 2025"
    status: ReconciliationStatusEnum
    costing_method: CostingMethodEnum
    # Summary totals
    total_opening_value: Decimal
    total_purchases_value: Decimal
    total_consumption_value: Decimal
    total_wastage_value: Decimal
    total_adjustment_value: Decimal
    total_theoretical_closing_value: Decimal
    total_physical_closing_value: Optional[Decimal]
    total_variance_value: Optional[Decimal]
    total_variance_pct: Optional[Decimal]
    # Line-level detail
    line_items: List[LineItemOut]
    # Items exceeding threshold
    flagged_items_count: int
    flagged_items: List[LineItemOut]


class ReconciliationConfig(BaseModel):
    costing_method: CostingMethodEnum = CostingMethodEnum.WEIGHTED_AVERAGE
    default_variance_threshold_pct: Decimal = Decimal("5.00")
    require_manager_approval: bool = True
    auto_close_on_approval: bool = True

    class Config:
        from_attributes = True