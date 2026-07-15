from enum import Enum

from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal
from app.models.wastage_model import WastageReason, WastageType, ReportPeriod

class RecordInventoryWastage(BaseModel):
    """Record wastage for a raw inventory item (perishable or non-perishable)."""
    inventory_item_id: int
    inventory_batch_id: Optional[int] = None
    quantity_wasted: Decimal = Field(..., gt=0)
    unit: str
    wastage_reason: WastageReason
    notes: Optional[str] = None
    photo_url: Optional[str] = None
    wastage_date: Optional[date] = None


class RecordUnsoldDish(BaseModel):
    """Record unsold dish wastage at end of day."""
    dish_id: int
    quantity_unsold: Decimal = Field(..., gt=0)
    preparation_log_id: Optional[int] = None
    notes: Optional[str] = None
    disposal_timestamp: Optional[date] = None

class BulkUnsoldDishes(BaseModel):
    dishes: List[RecordUnsoldDish]

class WastageOut(BaseModel):
    id: UUID
    wastage_type: str
    wastage_reason: str
    quantity_wasted: Decimal
    unit: Optional[str]
    unit_cost: Optional[Decimal]
    cost_value: Optional[Decimal]
    wastage_date: date
    notes: Optional[str]
    photo_url: Optional[str]
    is_breakdown: bool
    parent_wastage_id: Optional[UUID]

    # Resolved names (populated in service)
    item_name: Optional[str] = None
    dish_name: Optional[str] = None
    batch_number: Optional[str] = None
    recorded_by_name: Optional[str] = None

    class Config:
        from_attributes = True


class WastageBreakdownItem(BaseModel):
    ingredient_name: str
    quantity_wasted: Decimal
    unit: str
    unit_cost: Decimal
    cost_value: Decimal


class UnsoldDishWastageOut(BaseModel):
    wastage_id: UUID
    dish_name: str
    quantity_unsold: Decimal
    total_dish_cost: Decimal
    disposal_timestamp: date
    ingredient_breakdown: List[WastageBreakdownItem]


class WastageCategoryTotal(BaseModel):
    reason: str
    total_quantity: Decimal
    total_cost: Decimal
    record_count: int
    percentage_of_total_cost: Optional[float] = None


class TopWastageItem(BaseModel):
    item_name: str
    wastage_type: str
    total_quantity: Decimal
    unit: Optional[str]
    total_cost: Decimal
    occurrences: int


class WastageReport(BaseModel):
    period: str
    start_date: date
    end_date: date
    tenant_id: int

    # Totals
    total_wastage_cost: Decimal
    total_perishable_wastage_cost: Decimal
    total_non_perishable_wastage_cost: Decimal
    total_unsold_dish_cost: Decimal

    # Percentages
    perishable_wastage_pct_of_inventory: Optional[float] = None
    alert_perishable_threshold_exceeded: bool = False

    # Breakdown by reason
    by_reason: List[WastageCategoryTotal]

    # Top items
    top_wastage_items: List[TopWastageItem]

    # Raw records
    records: Optional[List[WastageOut]] = None

class RecordSemiFinishedWastage(BaseModel):
    """Record wastage for a semi-finished product batch (e.g. Dosa Batter)."""
    semi_finished_product_id: UUID
    semi_finished_batch_id: UUID          # the PrePreparedMaterialStock batch
    quantity_wasted: Decimal = Field(..., gt=0)
    unit: str
    wastage_reason: WastageReason         # expiry | damage | contamination | other
    notes: Optional[str] = None
    photo_url: Optional[str] = None
    wastage_date: Optional[date] = None    


class PeriodFilter(str, Enum):
    daily   = "daily"
    weekly  = "weekly"
    monthly = "monthly"
    custom  = "custom"


class ItemTypeFilter(str, Enum):
    perishable     = "perishable"
    non_perishable = "non_perishable"


class WastageRecord(BaseModel):
    wastage_id   : str
    batch_number : Optional[str]
    item_name    : str
    wastage_type : str
    item_type    : Optional[str]
    quantity     : float
    unit         : str
    cost         : float
    reason       : str
    date         : date
    photo_url    : Optional[str]


class WastageSummary(BaseModel):
    total_wastage_cost    : float
    total_wastage_records : int
    dish_wastage_cost     : float
    most_wasted_dish      : Optional[str]
    expiry_losses         : float


class GetWastageResponse(BaseModel):
    success      : bool
    period_label : str
    summary      : WastageSummary
    records      : List[WastageRecord]   