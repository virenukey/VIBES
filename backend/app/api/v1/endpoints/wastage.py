"""
app/api/v1/endpoints/wastage.py
Wastage Management Endpoints
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from math import ceil
from urllib import response
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, logger, status
import pandas as pd
from io import BytesIO 
from sqlalchemy import and_, case, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from typing import Annotated, Optional
from app.api.deps import get_db
from app.models.dish import Combo, Dish
from app.models.inventory import Inventory, InventoryBatch, ItemCategory, ItemPerishableNonPerishable
from app.models.users import User
from app.models.wastage_model import Wastage, WastageType, WastageReason
from app.schemas.wastage import (
    GetWastageResponse,
    ItemTypeFilter,
    PeriodFilter,
    RecordInventoryWastage,
    RecordSemiFinishedWastage,
    RecordUnsoldDish,
    BulkUnsoldDishes,
)
from app.services.wastage_service import WastageService
from app.utils.auth_helper import get_current_user
from app.utils.common_unit_converter import _normalize_unit, convert_quantity_unit
from app.utils.files_upload import get_presigned_url, upload_wastage_photo
import logging
from collections import defaultdict
from app.core.config import settings
import httpx
from fastapi.responses import StreamingResponse, RedirectResponse
from app.utils.files_upload import upload_wastage_photo, get_presigned_url
from uuid import UUID

logger = logging.getLogger(__name__)

router = APIRouter()

WEIGHT_UNITS  = {"kg", "gm", "mg"}
VOLUME_UNITS  = {"liter", "ml"}
LENGTH_UNITS  = {"m", "mm", "cm"}
COUNT_UNITS   = {"pcs", "packet", "box", "carton", "dozen", "bundle",
                 "roll", "sheet", "sachet", "bottle", "can", "bag"}

BASE_UNIT_MAP = {
    **{u: "gm"    for u in WEIGHT_UNITS},
    **{u: "ml"    for u in VOLUME_UNITS},
    **{u: "mm"    for u in LENGTH_UNITS},
    **{u: "pcs"   for u in COUNT_UNITS},
}

def _to_base(quantity: Decimal, unit: str) -> tuple[Decimal, str]:
    """Convert quantity to its category base unit using your existing function."""
    unit_str = _normalize_unit(unit)
    base_unit = BASE_UNIT_MAP.get(unit_str, unit_str)  # unknown units stay as-is
    if base_unit == unit_str:
        return quantity, unit_str
    converted = convert_quantity_unit(quantity, unit_str, base_unit)
    return converted, base_unit

def _from_base(base_qty: Decimal, base_unit: str) -> tuple[Decimal, str]:
    """Convert from base unit to a human-friendly display unit."""
    if base_unit == "gm":
        if base_qty >= 1000:
            return convert_quantity_unit(base_qty, "gm", "kg"), "kg"
        return base_qty, "gm"
    elif base_unit == "ml":
        if base_qty >= 1000:
            return convert_quantity_unit(base_qty, "ml", "liter"), "liter"
        return base_qty, "ml"
    elif base_unit == "mm":
        if base_qty >= 1000:
            return convert_quantity_unit(base_qty, "mm", "m"), "m"
        elif base_qty >= 10:
            return convert_quantity_unit(base_qty, "mm", "cm"), "cm"
        return base_qty, "mm"
    else:
        return base_qty, base_unit  # pcs, packet, etc.

def _parse_date(raw, field_name: str = "wastage_date") -> Optional[date]:
    """
    Safely parse a date string or datetime object.
    Accepts:
      - None / ""                    → None
      - datetime object              → .date()
      - date object                  → returned as-is
      - "2026-03-06"                 → date(2026, 3, 6)
      - "2026-03-06T14:30:00"        → date(2026, 3, 6)
    """
    if raw is None:
        return None
    # FastAPI may have already parsed it into a datetime/date object
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    # String handling
    if not raw.strip():
        return None
    raw = raw.strip()
    try:
        if len(raw) == 10:
            return date.fromisoformat(raw)
        return datetime.fromisoformat(raw).date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name} '{raw}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS",
        )
    
@router.post("/add-inventory-wastage", status_code=status.HTTP_201_CREATED)
async def record_inventory_wastage(
    inventory_item_id: int = Form(...),
    inventory_batch_id: Optional[int] = Form(None),
    quantity_wasted: float = Form(...),
    unit: str = Form(...),
    wastage_reason: str = Form(...),
    notes: Optional[str] = Form(None),
    wastage_date: Optional[datetime] = Form(None),
    photo: UploadFile = File(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record wastage for a raw inventory item.
    Send as multipart/form-data — photo uploads in same request.

    wastage_reason options:
        damage | contamination | spillage | expiry
        preparation_error | staff_meal | sampling | other
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        reason_enum = WastageReason(wastage_reason)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid wastage_reason '{wastage_reason}'. "
                   f"Allowed: {[r.value for r in WastageReason]}"
        )

    # Upload photo — happens before DB transaction
    photo_url = None
    if photo and photo.filename:
        photo_url = await upload_wastage_photo(photo)

    data = RecordInventoryWastage(
        inventory_item_id=inventory_item_id,
        inventory_batch_id=inventory_batch_id,
        quantity_wasted=Decimal(str(quantity_wasted)),
        unit=unit,
        wastage_reason=reason_enum,
        notes=notes,
        wastage_date=wastage_date,
        photo_url=photo_url,
    )

    try:
        record = WastageService.record_inventory_wastage(
            db=db,
            tenant_id=current_user.tenant_id,
            data=data,
            user_id=current_user.id,
        )
        return {
            "success": True,
            "message": "Inventory wastage recorded successfully",
            "data": {
                "wastage_id": str(record.id),
                "quantity_wasted": float(record.quantity_wasted),
                "unit": record.unit,
                "cost_value": float(record.cost_value or 0),
                "wastage_reason": record.wastage_reason.value,
                "photo_url": f"{settings.BASE_URL}/api/v1/wastage/photo/{str(record.id)}" if record.photo_url else None,
                "wastage_date": record.wastage_date,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to record inventory wastage")

@router.post("/unsold-dish", status_code=status.HTTP_201_CREATED)
def record_unsold_dish(
    data: RecordUnsoldDish,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record a single unsold dish at end of day.

    - Breaks down dish into constituent ingredients automatically
    - Calculates monetary value based on ingredient costs
    - Creates parent wastage record + ingredient breakdown records

    **Example:**
    ```json
    {
      "dish_id": 5,
      "quantity_unsold": 3,
      "notes": "Leftover from dinner service",
      "disposal_timestamp": "2026-02-23T22:00:00Z"
    }
    ```
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        result = WastageService.record_unsold_dish(
            db=db,
            tenant_id=current_user.tenant_id,
            data=data,
            user_id=current_user.id,
        )
        return {"success": True, "message": "Unsold dish wastage recorded", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to record unsold dish wastage")

@router.post("/unsold-dishes/bulk", status_code=status.HTTP_201_CREATED)
def record_bulk_unsold_dishes(
    data: BulkUnsoldDishes,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record multiple unsold dishes at end of day in one call.

    **Example:**
    ```json
    {
      "dishes": [
        {"dish_id": 5, "quantity_unsold": 3},
        {"dish_id": 8, "quantity_unsold": 1, "notes": "Slightly overcooked"}
      ]
    }
    ```
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        result = WastageService.record_bulk_unsold_dishes(
            db=db,
            tenant_id=current_user.tenant_id,
            dishes=data.dishes,
            user_id=current_user.id,
        )
        return {"success": True, "message": "Bulk unsold dish wastage recorded", "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to record bulk unsold dish wastage")

@router.get("/expiry-alerts")
def get_expiry_alerts(
    threshold_days: int = Query(3, ge=1, le=30, description="Days until expiry to flag (default: 3)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get items approaching expiry with 'Use First' recommendations.

    - Returns batches expiring within `threshold_days`
    - Sorted by expiry date ascending (most urgent first)
    - Includes urgency level: CRITICAL (today), HIGH (≤1 day), MEDIUM

    **Example:**
    ```
    GET /wastage/expiry-alerts?threshold_days=3
    ```
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    return WastageService.get_expiry_alerts(
        db=db,
        tenant_id=current_user.tenant_id,
        threshold_days=threshold_days,
    )

@router.post("/auto-flag-expired")
def auto_flag_expired_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger auto-flagging of expired batches.

    Scans all active batches past their expiry date with remaining quantity
    and creates wastage records for them. Normally called by a scheduled task,
    but can be triggered manually.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    result = WastageService.auto_mark_expired_batches(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    return {
        "success": True,
        "message": f"Auto-flagged {result['auto_flagged_count']} expired batch(es)",
        "data": result,
    }

@router.get("/records")
def list_wastage_records(
    filter_type: str = Query("daily", regex="^(daily|weekly|monthly|custom)$"),
    date: Optional[date] = Query(None, description="Reference date, defaults to today"),
    start_date: Optional[date] = Query(None, description="Custom range start date (required when filter_type=custom)"),
    end_date: Optional[date] = Query(None, description="Custom range end date (required when filter_type=custom)"),
    wastage_type: Optional[str] = Query(None, description="dish | inventory | semi_finished"),
    wastage_reason: Optional[str] = Query(
        None,
        description="expiry | damage | contamination | unsold_dish | preparation_error | spillage | other"
    ),
    include_breakdown: bool = Query(False, description="Include ingredient-level breakdown rows"),
    search: Optional[str] = Query(None, description="Search by item name or dish name"),   
    page: int = Query(default=1, ge=1, description="Page number"),                      
    page_size: int = Query(default=10, ge=1, le=100, description="Rows per page"),         
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List wastage records with optional filters.

    **Filter types:**
    - `daily` — single day (defaults to today)
    - `weekly` — full Mon–Sun week containing the given date
    - `monthly` — full calendar month containing the given date
    - `custom` — explicit date range via `start_date` and `end_date`

    **Examples:**
```
    GET /wastage/records?filter_type=daily
    GET /wastage/records?filter_type=daily&date=2026-03-15
    GET /wastage/records?filter_type=weekly&date=2026-03-10
    GET /wastage/records?filter_type=monthly&date=2026-03-01
    GET /wastage/records?filter_type=custom&start_date=2026-03-01&end_date=2026-03-20
    GET /wastage/records?filter_type=monthly&wastage_type=inventory&wastage_reason=expiry
```
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    # --- Resolve filter_type into resolved_start / resolved_end ---
    today = date or datetime.now(timezone.utc).date()

    if filter_type == "daily":
        resolved_start = today
        resolved_end = today

    elif filter_type == "weekly":
        resolved_start = today - timedelta(days=today.weekday())
        resolved_end = resolved_start + timedelta(days=6)

    elif filter_type == "monthly":
        resolved_start = today.replace(day=1)
        if today.month == 12:
            resolved_end = today.replace(day=31)
        else:
            resolved_end = (today.replace(month=today.month + 1, day=1) - timedelta(days=1))

    elif filter_type == "custom":
        if not start_date or not end_date:
            raise HTTPException(
                status_code=400,
                detail="Both start_date and end_date are required when filter_type=custom"
            )
        if start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must not be after end_date"
            )
        resolved_start = start_date
        resolved_end = end_date

    # --- Validate wastage_type ---
    wtype = None
    if wastage_type:
        try:
            wtype = WastageType(wastage_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid wastage_type: {wastage_type}")

    # --- Validate wastage_reason ---
    wreason = None
    if wastage_reason:
        try:
            wreason = WastageReason(wastage_reason)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid wastage_reason: {wastage_reason}")

    response = WastageService.get_wastage_records(
        db=db,
        tenant_id=current_user.tenant_id,
        start_date=resolved_start,
        end_date=resolved_end,
        wastage_type=wtype,
        wastage_reason=wreason,
        include_breakdown=include_breakdown,
        search=search,                                                                     
    )

    all_records   = response["records"]                                                   
    total         = len(all_records)                                                     
    start         = (page - 1) * page_size                                                
    paged_records = all_records[start : start + page_size]                               

    return {
        "success":     True,
        "filter_type": filter_type,
        "start_date":  resolved_start,
        "end_date":    resolved_end,
        "meta": {                                                                         
            "total":       total,                                                         
            "page":        page,                                                          
            "page_size":   page_size,                                                     
            "total_pages": ceil(total / page_size) if total else 1,                     
            "search":      search,                                                        
        },                                                                              
        "total":   total,                                                                  
        "summary": response["summary"],
        "data":    paged_records,                                                         
    }

@router.get("/report/daily")
def daily_wastage_report(
    report_date: Optional[date] = Query(None, description="Date to report (default: today)"),
    perishable_threshold_pct: float = Query(5.0, description="Alert threshold % for perishable wastage"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Daily wastage report.

    - Total wastage cost broken down by reason
    - Perishable vs non-perishable split
    - Unsold dish cost
    - Alert if perishable wastage > threshold % of total perishable inventory value
    - Top 10 wasted items
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    target = report_date or date.today()
    report = WastageService.generate_report(
        db=db,
        tenant_id=current_user.tenant_id,
        period="daily",
        start_date=target,
        end_date=target,
        perishable_threshold_pct=perishable_threshold_pct,
    )
    return {"success": True, "data": report}

@router.get("/report/weekly")
def weekly_wastage_report(
    week_start: Optional[date] = Query(None, description="Start of week (default: this Monday)"),
    perishable_threshold_pct: float = Query(5.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Weekly wastage report (Mon–Sun).
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    today = date.today()
    start = week_start or (today - timedelta(days=today.weekday()))
    end = start + timedelta(days=6)

    report = WastageService.generate_report(
        db=db,
        tenant_id=current_user.tenant_id,
        period="weekly",
        start_date=start,
        end_date=end,
        perishable_threshold_pct=perishable_threshold_pct,
    )
    return {"success": True, "data": report}

@router.get("/report/monthly")
def monthly_wastage_report(
    year: Optional[int] = Query(None, description="Year (default: current year)"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month 1–12 (default: current month)"),
    perishable_threshold_pct: float = Query(5.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Monthly wastage report.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    today = date.today()
    y = year or today.year
    m = month or today.month
    start = date(y, m, 1)
    # Last day of month
    if m == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, m + 1, 1) - timedelta(days=1)

    report = WastageService.generate_report(
        db=db,
        tenant_id=current_user.tenant_id,
        period="monthly",
        start_date=start,
        end_date=end,
        perishable_threshold_pct=perishable_threshold_pct,
    )
    return {"success": True, "data": report}

@router.get("/report/custom")
def custom_wastage_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    perishable_threshold_pct: float = Query(5.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Custom date range wastage report.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    report = WastageService.generate_report(
        db=db,
        tenant_id=current_user.tenant_id,
        period="custom",
        start_date=start_date,
        end_date=end_date,
        perishable_threshold_pct=perishable_threshold_pct,
    )
    return {"success": True, "data": report}

@router.post("/semi-finished", status_code=status.HTTP_201_CREATED)
def record_semi_finished_wastage(
    data: RecordSemiFinishedWastage,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record wastage for a semi-finished product batch.

    Example — Dosa Batter batch expired:
    {
      "semi_finished_product_id": "uuid-of-dosa-batter",
      "semi_finished_batch_id": "uuid-of-batch",
      "quantity_wasted": 2000,
      "unit": "gm",
      "wastage_reason": "expiry",
      "notes": "48hr shelf life exceeded"
    }
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        record = WastageService.record_semi_finished_wastage(
            db=db,
            tenant_id=current_user.tenant_id,
            data=data,
            user_id=current_user.id,
        )
        return {
            "success": True,
            "message": "Semi-finished wastage recorded successfully",
            "data": {
                "wastage_id": str(record.id),
                "product_name": record.semi_finished_product.name,
                "batch_id": str(record.semi_finished_batch_id),
                "quantity_wasted": float(record.quantity_wasted),
                "unit": record.unit,
                "cost_value": float(record.cost_value or 0),
                "wastage_reason": record.wastage_reason.value,
                "wastage_date": record.wastage_date,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to record semi-finished wastage")
    
@router.get("/get-wastage/perishable-non-perishable")
def get_wastage_by_perishable_type(
    perishable_type: Optional[ItemPerishableNonPerishable] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )

    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date cannot be greater than end_date",
        )

    try:
        query = (
            db.query(
                Wastage.id.label("wastage_id"),
                Wastage.quantity_wasted,
                Wastage.cost_value,
                Wastage.wastage_date,
                Wastage.wastage_reason,
                Wastage.unit,
                Inventory.id.label("inventory_id"),
                Inventory.name,
                Inventory.category_type.label("perishable_type"),  # ← from Inventory directly
                ItemCategory.id.label("category_id"),
                ItemCategory.name.label("category_name"),
            )
            .join(Inventory, Wastage.inventory_item_id == Inventory.id)
            .outerjoin(ItemCategory, Inventory.item_category_id == ItemCategory.id)  # ← outerjoin; only needed for category name/id
            .filter(
                Wastage.tenant_id == current_user.tenant_id,
                Wastage.wastage_type == WastageType.INVENTORY,
                Inventory.category_type.isnot(None),  # ← exclude items with no type set
            )
        )

        if perishable_type:
            query = query.filter(Inventory.category_type == perishable_type)  # ← filter on Inventory
        if start_date:
            query = query.filter(Wastage.wastage_date >= start_date)
        if end_date:
            query = query.filter(Wastage.wastage_date <= end_date)

        results = query.order_by(
            Inventory.category_type, Wastage.wastage_date.desc()
        ).all()

        if not results:
            return {
                "success": True,
                "message": "No wastage records found for the given filters",
                "data": [],
            }

        grouped_data = {}
        for row in results:
            p_type = row.perishable_type.value if hasattr(row.perishable_type, "value") else row.perishable_type

            if p_type not in grouped_data:
                grouped_data[p_type] = {
                    "perishable_type": p_type,
                    "total_records": 0,
                    "total_quantity_wasted": 0.0,
                    "total_cost_wasted": 0.0,
                    "records": [],
                }

            grouped_data[p_type]["total_records"] += 1
            grouped_data[p_type]["total_quantity_wasted"] += float(row.quantity_wasted or 0)
            grouped_data[p_type]["total_cost_wasted"] += float(row.cost_value or 0)
            grouped_data[p_type]["records"].append(
                {
                    "wastage_id": row.wastage_id,
                    "inventory_id": row.inventory_id,
                    "item_name": row.name,
                    "category_id": row.category_id,
                    "category_name": row.category_name,
                    "quantity_wasted": float(row.quantity_wasted or 0),
                    "cost_value": float(row.cost_value or 0),
                    "wastage_date": row.wastage_date,
                    "wastage_reason": row.wastage_reason,
                    "unit": row.unit,
                }
            )

        return {
            "success": True,
            "data": list(grouped_data.values()),
        }

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_wastage_by_perishable_type: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred while fetching wastage data",
        )

    except Exception as e:
        logger.error(f"Unexpected error in get_wastage_by_perishable_type: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        )

@router.get("/unsold-dishes")
def get_unsold_dishes(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    dish_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be greater than end_date")

    try:
        # Query only parent (dish-level) wastage records
        query = (
            db.query(Wastage)
            .filter(
                Wastage.tenant_id == current_user.tenant_id,
                Wastage.wastage_type == WastageType.DISH,
                Wastage.wastage_reason == WastageReason.UNSOLD_DISH,
                Wastage.is_breakdown == False,
            )
        )

        if dish_id:
            query = query.filter(Wastage.dish_id == dish_id)
        if start_date:
            query = query.filter(Wastage.wastage_date >= start_date)
        if end_date:
            query = query.filter(Wastage.wastage_date <= end_date)

        records = query.order_by(Wastage.wastage_date.desc()).all()

        if not records:
            return {
                "success": True,
                "message": "No unsold dish records found for the given filters",
                "data": [],
            }

        result = []
        for record in records:
            # Fetch dish name
            dish = db.query(Dish).filter(Dish.id == record.dish_id).first()

            # Fetch ingredient breakdown (child records)
            breakdown_records = (
                db.query(Wastage, Inventory.name.label("inventory_item_name"))
                .outerjoin(Inventory, Wastage.inventory_item_id == Inventory.id)
                .filter(
                    Wastage.parent_wastage_id == record.id,
                    Wastage.is_breakdown == True,
                )
                .all()
            )

            breakdown_items = [
                {
                    "wastage_id": child.id,
                    "inventory_item_id": child.inventory_item_id,
                    "inventory_item_name": inventory_item_name, 
                    "quantity_wasted": float(child.quantity_wasted or 0),
                    "unit": child.unit,
                    "unit_cost": float(child.unit_cost or 0),
                    "cost_value": float(child.cost_value or 0),
                    "notes": child.notes,
                }
                for child ,inventory_item_name in breakdown_records
            ]

            result.append(
                {
                    "wastage_id": record.id,
                    "dish_id": record.dish_id,
                    "dish_name": dish.name if dish else None,
                    "quantity_unsold": float(record.quantity_wasted or 0),
                    "unit_cost": float(record.unit_cost or 0),
                    "total_dish_cost": float(record.cost_value or 0),
                    "wastage_date": record.wastage_date,
                    "notes": record.notes,
                    "recorded_by_user_id": record.recorded_by_user_id,
                    "ingredient_breakdown": breakdown_items,
                }
            )

        return {
            "success": True,
            "total_records": len(result),
            "total_cost_wasted": round(sum(r["total_dish_cost"] for r in result), 2),
            "data": result,
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_unsold_dishes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="A database error occurred while fetching unsold dishes")
    except Exception as e:
        logger.error(f"Unexpected error in get_unsold_dishes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")        

@router.post("/add-wastage", status_code=status.HTTP_201_CREATED)
async def record_wastage(
    wastage_type: str = Form(..., description="inventory | dish | semi_finished | combo"),
    # ── Inventory ──
    inventory_item_id:  Optional[int] = Form(None),
    inventory_batch_id: Optional[int] = Form(None),
    unit:               Optional[str] = Form(None),
    # ── Dish ──
    dish_id:            Optional[int] = Form(None),
    # ── Semi-finished ──
    semi_finished_id:   Optional[int] = Form(None),
    # ── Combo ──
    combo_id:           Optional[int] = Form(None),
    # ── Common ──
    quantity_wasted:    float         = Form(...),
    wastage_reason:     str           = Form(...),
    notes:              Optional[str] = Form(None),
    wastage_date:       Optional[str] = Form(None),
    photo:              UploadFile    = File(default=None),
    db:                 Session       = Depends(get_db),
    current_user:       User          = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    notes          = notes.strip()          if notes          and notes.strip()          else None
    unit           = unit.strip()           if unit           and unit.strip()           else None
    wastage_reason = wastage_reason.strip() if wastage_reason and wastage_reason.strip() else wastage_reason

    parsed_wastage_date = _parse_date(wastage_date)

    try:
        wastage_type_enum = WastageType(wastage_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid wastage_type '{wastage_type}'. Allowed: inventory, dish, semi_finished, combo",
        )

    photo_url = None
    if photo and photo.filename:
        photo_url = await upload_wastage_photo(photo)

    # ── INVENTORY ─────────────────────────────────────────────────────────────
    if wastage_type_enum == WastageType.INVENTORY:
        if not inventory_item_id:
            raise HTTPException(status_code=400, detail="inventory_item_id is required")
        if not unit:
            raise HTTPException(status_code=400, detail="unit is required")

        try:
            reason_enum = WastageReason(wastage_reason)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid wastage_reason. Allowed: {[r.value for r in WastageReason]}",
            )

        data = RecordInventoryWastage(
            inventory_item_id  = inventory_item_id,
            inventory_batch_id = inventory_batch_id,
            quantity_wasted    = Decimal(str(quantity_wasted)),
            unit               = unit,
            wastage_reason     = reason_enum,
            notes              = notes,
            wastage_date       = parsed_wastage_date,
            photo_url          = photo_url,
        )

        try:
            record = WastageService.record_inventory_wastage(
                db         = db,
                tenant_id  = current_user.tenant_id,
                data       = data,
                user_id    = current_user.id,
            )
            return {
                "success":      True,
                "wastage_type": "inventory",
                "message":      "Inventory wastage recorded successfully",
                "data": {
                    "wastage_id":      str(record.id),
                    "quantity_wasted": float(record.quantity_wasted),
                    "unit":            record.unit,
                    "cost_value":      float(record.cost_value or 0),
                    "wastage_reason":  record.wastage_reason.value,
                    "photo_url":       record.photo_url,
                    "wastage_date":    record.wastage_date,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── DISH ──────────────────────────────────────────────────────────────────
    if wastage_type_enum == WastageType.DISH:
        if not dish_id:
            raise HTTPException(status_code=400, detail="dish_id is required")

        try:
            result = WastageService.record_dish_wastage(
                db              = db,
                tenant_id       = current_user.tenant_id,
                dish_id         = dish_id,
                quantity_wasted = int(quantity_wasted),
                wastage_reason  = wastage_reason,
                user_id         = current_user.id,
                notes           = notes,
                wastage_date    = parsed_wastage_date,
                photo_url       = photo_url,
            )
            return {
                "success":      True,
                "wastage_type": "dish",
                "message":      "Dish wastage recorded successfully",
                "data":         result,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── SEMI-FINISHED ─────────────────────────────────────────────────────────
    if wastage_type_enum == WastageType.SEMI_FINISHED:
        if not semi_finished_id:
            raise HTTPException(status_code=400, detail="semi_finished_id is required")

        try:
            result = WastageService.record_semi_finished_wastage(
                db               = db,
                tenant_id        = current_user.tenant_id,
                semi_finished_id = semi_finished_id,
                quantity_wasted  = float(quantity_wasted),
                wastage_reason   = wastage_reason,
                user_id          = current_user.id,
                wastage_unit     = unit, 
                notes            = notes,
                wastage_date     = parsed_wastage_date,
                photo_url        = photo_url,
            )
            return {
                "success":      True,
                "wastage_type": "semi_finished",
                "message":      "Semi-finished wastage recorded successfully",
                "data":         result,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── COMBO ─────────────────────────────────────────────────────────────────
    if wastage_type_enum == WastageType.COMBO:
        if not combo_id:
            raise HTTPException(status_code=400, detail="combo_id is required")

        try:
            result = WastageService.record_combo_wastage(
                db              = db,
                tenant_id       = current_user.tenant_id,
                combo_id        = combo_id,
                quantity_wasted = int(quantity_wasted),
                wastage_reason  = wastage_reason,
                user_id         = current_user.id,
                notes           = notes,
                wastage_date    = parsed_wastage_date,
                photo_url       = photo_url,
            )
            return {
                "success":      True,
                "wastage_type": "combo",
                "message":      "Combo wastage recorded successfully",
                "data":         result,
            }
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))   
 
REQUIRED_COLUMNS = [
    "wastage_type",         # inventory | dish
    "quantity_wasted",
    "wastage_reason",
]
OPTIONAL_COLUMNS = [
    "inventory_item_id",
    "inventory_batch_id",
    "unit",
    "dish_id",
    "notes",
    "wastage_date",         # ISO-8601 or Excel date
]
ALL_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
 
def _find_inventory_item(db: Session, tenant_id: int, name: str) -> Optional[object]:
    """Case-insensitive inventory name lookup."""
    return (
        db.query(Inventory)
        .filter(
            Inventory.tenant_id == tenant_id,
            Inventory.is_active == True,
            Inventory.name.ilike(name.strip()),
        )
        .first()
    )
 
def _find_batch(db: Session, tenant_id: int, inventory_item_id: int, batch_number: str) -> Optional[object]:
    """Find a batch by its human-readable batch_number string."""
    return (
        db.query(InventoryBatch)
        .filter(
            InventoryBatch.tenant_id == tenant_id,
            InventoryBatch.inventory_item_id == inventory_item_id,
            InventoryBatch.batch_number.ilike(batch_number.strip()),
        )
        .first()
    )
 
 
def _find_dish(db: Session, tenant_id: int, name: str) -> Optional[object]:
    """Case-insensitive dish name lookup."""
    return (
        db.query(Dish)
        .filter(
            Dish.tenant_id == tenant_id,
            Dish.is_active == True,
            Dish.name.ilike(name.strip()),
        )
        .first()
    )
 
@router.post("/bulk-upload-via-excel", status_code=status.HTTP_200_OK)
async def bulk_upload_wastage_via_excel(
    file: UploadFile = File(..., description="Excel file (.xlsx / .xls)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    contents = await file.read()
    try:
        xl = pd.ExcelFile(BytesIO(contents))
        sheet_name = "Wastage" if "Wastage" in xl.sheet_names else xl.sheet_names[0]
        df = xl.parse(sheet_name, dtype=str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse Excel file: {e}")

    # Normalise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    df.dropna(how="all", inplace=True)
    df.reset_index(drop=True, inplace=True)

    if df.empty:
        raise HTTPException(status_code=400, detail="Excel file contains no data rows")

    results      = []
    success_count = 0
    failure_count = 0

    for idx, row in df.iterrows():
        row_num = idx + 2
        result  = {"row": row_num, "status": None, "message": None, "data": None}

        def get(col):
            v = row.get(col)
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            v = str(v).strip()
            return None if v in ("", "nan", "NaN", "None") else v

        wastage_type_raw = get("wastage_type")
        qty_raw          = get("quantity_wasted")
        wastage_reason   = get("wastage_reason")
        notes            = get("notes")

        # ── Quantity ────────────────────────────────────────────────────
        try:
            quantity_wasted = float(qty_raw) if qty_raw else 0.0
        except (ValueError, TypeError):
            quantity_wasted = 0.0

        # ── Wastage type ────────────────────────────────────────────────
        try:
            wastage_type_enum = (
                WastageType(wastage_type_raw.lower().strip())
                if wastage_type_raw else WastageType.INVENTORY
            )
        except ValueError:
            wastage_type_enum = WastageType.INVENTORY

        # ── Date parsing ────────────────────────────────────────────────
        # FIX: parse into a plain `date` object (not datetime) so it matches
        # exactly what the manual upload UI sends. record_dish_wastage and
        # record_inventory_wastage both expect a date or datetime and will
        # store it as 00:00:00 UTC (start-of-day) to avoid IST rollover.
        wastage_date_raw = get("wastage_date")
        wastage_date_only: date = date.today()          # default = today

        if wastage_date_raw:
            parsed_dt = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    parsed_dt = datetime.strptime(wastage_date_raw, fmt)
                    break
                except ValueError:
                    continue

            if parsed_dt:
                wastage_date_only = parsed_dt.date()    # always a plain date
            # else: keep today as fallback

        # ════════════════════════════════════════════════════════════════
        # INVENTORY WASTAGE
        # ════════════════════════════════════════════════════════════════
        if wastage_type_enum == WastageType.INVENTORY:

            inventory_name = get("inventory_name")
            batch_number   = get("batch_number")
            unit           = get("unit") or "piece"

            item = (
                _find_inventory_item(db, current_user.tenant_id, inventory_name)
                if inventory_name else None
            )

            inventory_batch_id = None
            if item and batch_number:
                batch = _find_batch(db, current_user.tenant_id, item.id, batch_number)
                if batch:
                    inventory_batch_id = batch.id

            try:
                reason_enum = (
                    WastageReason(wastage_reason)
                    if wastage_reason else list(WastageReason)[0]
                )
            except ValueError:
                reason_enum = list(WastageReason)[0]

            # FIX: pass wastage_date as plain `date` — same as manual upload.
            # record_inventory_wastage will convert it to 00:00:00 UTC internally.
            data = RecordInventoryWastage(
                inventory_item_id  = item.id if item else None,
                inventory_batch_id = inventory_batch_id,
                quantity_wasted    = Decimal(str(quantity_wasted)),
                unit               = unit,
                wastage_reason     = reason_enum,
                notes              = notes,
                wastage_date       = wastage_date_only,   # FIX: plain date not datetime
                photo_url          = None,
            )

            try:
                record = WastageService.record_inventory_wastage(
                    db        = db,
                    tenant_id = current_user.tenant_id,
                    data      = data,
                    user_id   = current_user.id,
                )
                result.update(
                    status  = "success",
                    message = "Inventory wastage recorded",
                    data    = {
                        "wastage_id":      str(record.id),
                        "inventory_name":  inventory_name,
                        "batch_number":    batch_number,
                        "quantity_wasted": float(record.quantity_wasted),
                        "unit":            record.unit,
                        "cost_value":      float(record.cost_value or 0),
                        "wastage_reason":  record.wastage_reason.value,
                        "wastage_date":    str(record.wastage_date),
                    },
                )
                success_count += 1
            except HTTPException as e:
                # Unwrap FastAPI HTTPException so the error message is readable
                detail = e.detail
                if isinstance(detail, dict) and "errors" in detail:
                    message = "; ".join(detail["errors"])
                else:
                    message = str(detail)
                result.update(status="error", message=message)
                failure_count += 1
            except Exception as e:
                result.update(status="error", message=str(e))
                failure_count += 1

        # ════════════════════════════════════════════════════════════════
        # DISH WASTAGE
        # ════════════════════════════════════════════════════════════════
        else:
            dish_name = get("dish_name")

            dish = (
                _find_dish(db, current_user.tenant_id, dish_name)
                if dish_name else None
            )

            if not dish:
                result.update(
                    status  = "error",
                    message = (
                        f"Dish '{dish_name}' not found"
                        if dish_name else "dish_name is required for dish wastage"
                    ),
                )
                failure_count += 1
                results.append(result)
                continue

            try:
                # FIX: pass wastage_date as plain `date` — same as manual upload.
                # record_dish_wastage will convert to 00:00:00 UTC and use
                # func.date(date_added) for batch lookup, so backdated rows work.
                record = WastageService.record_dish_wastage(
                    db              = db,
                    tenant_id       = current_user.tenant_id,
                    dish_id         = dish.id,
                    quantity_wasted = int(quantity_wasted),
                    wastage_reason  = wastage_reason,
                    user_id         = current_user.id,
                    notes           = notes,
                    wastage_date    = wastage_date_only,   # FIX: plain date not datetime
                    photo_url       = None,
                )
                result.update(
                    status  = "success",
                    message = "Dish wastage recorded",
                    data    = record,
                )
                success_count += 1
            except HTTPException as e:
                # Unwrap FastAPI HTTPException so row-level errors are readable
                detail = e.detail
                if isinstance(detail, dict) and "errors" in detail:
                    message = "; ".join(detail["errors"])
                else:
                    message = str(detail)
                result.update(status="error", message=message)
                failure_count += 1
            except Exception as e:
                result.update(status="error", message=str(e))
                failure_count += 1

        results.append(result)

    return {
        "success": True,
        "summary": {
            "total_rows": len(results),
            "successful": success_count,
            "failed":     failure_count,
        },
        "results": results,
    }
 
# ── helper ────────────────────────────────────────────────────────────────────
def _resolve_wastage_date_range(
    period    : str,
    start_date: Optional[date],
    end_date  : Optional[date],
) -> tuple[datetime, datetime]:
    today = datetime.now(timezone.utc).date()  #  utc aware


    if period == "daily":
        s = datetime.combine(today, datetime.min.time())
        e = datetime.combine(today, datetime.max.time())

    elif period == "weekly":
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        s = datetime.combine(monday, datetime.min.time())
        e = datetime.combine(sunday, datetime.max.time())

    elif period == "monthly":
        first = today.replace(day=1)
        last  = (today.replace(month=today.month + 1, day=1) - timedelta(days=1)) \
                if today.month != 12 else today.replace(day=31)
        s = datetime.combine(first, datetime.min.time())
        e = datetime.combine(last,  datetime.max.time())

    else:  # custom
        if not start_date or not end_date:
            raise ValueError("start_date and end_date required for period=custom")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")
        s = datetime.combine(start_date, datetime.min.time())
        e = datetime.combine(end_date,   datetime.max.time())

    return s, e

@router.get("/reports/wastage-summary", status_code=status.HTTP_200_OK)
def get_wastage_summary(
    period    : str            = Query("daily", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    db        : Session        = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    Summary cards:
      - Total Wastage Cost
      - Total Records
      - Avg Daily Loss  (total cost / number of days in range)
      - Total Inventory Loss (inventory wastage only)
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_wastage_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # ── current period ────────────────────────────────────────────────────
        agg = (
            db.query(
                func.coalesce(func.sum(Wastage.cost_value), 0).label("total_cost"),
                func.count(Wastage.id).label("total_records"),
                func.coalesce(
                    func.sum(
                        case(
                            (Wastage.wastage_type == WastageType.INVENTORY, Wastage.cost_value),
                            else_=0,
                        )
                    ), 0
                ).label("inventory_loss"),
            )
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= start_dt,
                Wastage.wastage_date <= end_dt,
                Wastage.is_breakdown == False,
            )
            .one()
        )

        # ── previous period (for % change labels) ────────────────────────────
        delta        = end_dt - start_dt
        prev_start   = start_dt - delta - timedelta(seconds=1)
        prev_end     = start_dt - timedelta(seconds=1)

        prev_agg = (
            db.query(
                func.coalesce(func.sum(Wastage.cost_value), 0).label("total_cost"),
                func.count(Wastage.id).label("total_records"),
            )
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= prev_start,
                Wastage.wastage_date <= prev_end,
                Wastage.is_breakdown == False,
            )
            .one()
        )

        # ── avg daily loss ────────────────────────────────────────────────────
        num_days   = max((end_dt.date() - start_dt.date()).days + 1, 1)
        avg_daily  = float(agg.total_cost) / num_days

        # ── % change helpers ──────────────────────────────────────────────────
        def pct_change(current, previous):
            if not previous or previous == 0:
                return None
            return round(((current - previous) / previous) * 100, 1)

        return {
            "success"   : True,
            "period"    : period,
            "date_range": {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to"  : end_dt.strftime("%d-%m-%Y"),
            },
            "summary": {
                "total_wastage_cost" : float(round(agg.total_cost, 2)),
                "total_records"      : agg.total_records,
                "avg_daily_loss"     : float(round(avg_daily, 2)),
                "total_inventory_loss": float(round(agg.inventory_loss, 2)),
                "vs_last_period": {
                    "total_cost_change_pct"   : pct_change(float(agg.total_cost),    float(prev_agg.total_cost)),
                    "total_records_change_pct": pct_change(agg.total_records, prev_agg.total_records),
                },
            },
        }

    except Exception as e:
        logger.exception(f"Error fetching wastage summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch wastage summary")

@router.get("/reports/wastage-trend", status_code=status.HTTP_200_OK)
def get_wastage_trend(
    period    : str            = Query("monthly", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    db        : Session        = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    Bar chart data:
    - daily   → hourly buckets
    - weekly  → Mon–Sun
    - monthly → one per day
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_wastage_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        records = (
            db.query(Wastage)
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= start_dt,
                Wastage.wastage_date <= end_dt,
                Wastage.is_breakdown == False,
            )
            .all()
        )

        buckets: dict = defaultdict(lambda: {"wastage_count": 0, "total_cost": 0.0})

        for w in records:
            if not w.wastage_date:
                continue
            if period == "daily":
                key = w.wastage_date.strftime("%H:00")
            elif period == "weekly":
                key = w.wastage_date.strftime("%a")
            else:
                key = w.wastage_date.strftime("%d %b")

            buckets[key]["wastage_count"] += 1
            buckets[key]["total_cost"]    += float(w.cost_value or 0)

        # Build ordered keys
        if period == "daily":
            all_keys = [f"{h:02d}:00" for h in range(24)]
        elif period == "weekly":
            all_keys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        else:
            delta    = (end_dt.date() - start_dt.date()).days + 1
            all_keys = [
                (start_dt + timedelta(days=i)).strftime("%d %b")
                for i in range(delta)
            ]

        trends = [
            {
                "label"        : key,
                "wastage_count": buckets[key]["wastage_count"],
                "total_cost"   : round(buckets[key]["total_cost"], 2),
            }
            for key in all_keys
        ]

        return {
            "success"   : True,
            "period"    : period,
            "date_range": {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to"  : end_dt.strftime("%d-%m-%Y"),
            },
            "trends": trends,
        }

    except Exception as e:
        logger.exception(f"Error fetching wastage trend: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch wastage trend")

@router.get("/reports/wastage-by-reason", status_code=status.HTTP_200_OK)
def get_wastage_by_reason(
    period    : str            = Query("monthly", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    db        : Session        = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    Donut chart — distribution of wastage across reasons.
    Returns count, cost, and percentage per reason.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_wastage_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        rows = (
            db.query(
                Wastage.wastage_reason,
                func.count(Wastage.id).label("count"),
                func.coalesce(func.sum(Wastage.cost_value), 0).label("total_cost"),
            )
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= start_dt,
                Wastage.wastage_date <= end_dt,
                Wastage.is_breakdown == False,
            )
            .group_by(Wastage.wastage_reason)
            .order_by(func.count(Wastage.id).desc())
            .all()
        )

        total_count = sum(r.count for r in rows) or 1

        reasons = [
            {
                "reason"    : r.wastage_reason.value,
                "count"     : r.count,
                "total_cost": float(round(r.total_cost, 2)),
                "percentage": round((r.count / total_count) * 100, 1),
            }
            for r in rows
        ]

        return {
            "success"      : True,
            "period"       : period,
            "date_range"   : {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to"  : end_dt.strftime("%d-%m-%Y"),
            },
            "total_records": total_count,
            "by_reason"    : reasons,
        }

    except Exception as e:
        logger.exception(f"Error fetching wastage by reason: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch wastage by reason")

@router.get("/reports/top-wastage-items", status_code=status.HTTP_200_OK)
def get_top_wastage_items(
    period    : str            = Query("monthly", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    limit     : int            = Query(10, ge=1, le=50),
    db        : Session        = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_wastage_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # ── fetch individual records per wastage type ─────────────────────────
        # Raw rows are fetched (not pre-aggregated in SQL) because units must be
        # normalized per-record before summing — a single item can have wastage
        # logged in mixed units (e.g. "kg" on one row, "g" on another).
        # is_breakdown == False excludes constituent-ingredient rows, since those
        # are children of a parent wastage row (linked via parent_wastage_id) and
        # summing them in would double-count cost already captured on the parent.

        inv_records = (
            db.query(
                Wastage.inventory_item_id,
                Wastage.quantity_wasted,
                Wastage.cost_value,
                Wastage.unit,
            )
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= start_dt,
                Wastage.wastage_date <= end_dt,
                Wastage.wastage_type == WastageType.INVENTORY,
                Wastage.is_breakdown == False,
                Wastage.inventory_item_id.isnot(None),
            )
            .all()
        )

        dish_records = (
            db.query(
                Wastage.dish_id,
                Wastage.quantity_wasted,
                Wastage.cost_value,
                Wastage.unit,
            )
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= start_dt,
                Wastage.wastage_date <= end_dt,
                Wastage.wastage_type == WastageType.DISH,
                Wastage.is_breakdown == False,
                Wastage.dish_id.isnot(None),
            )
            .all()
        )

        combo_records = (
            db.query(
                Wastage.combo_id,
                Wastage.quantity_wasted,
                Wastage.cost_value,
                Wastage.unit,
            )
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= start_dt,
                Wastage.wastage_date <= end_dt,
                Wastage.wastage_type == WastageType.COMBO,
                Wastage.is_breakdown == False,
                Wastage.combo_id.isnot(None),
            )
            .all()
        )

        # ── resolve names in bulk ─────────────────────────────────────────────
        inv_ids   = [r.inventory_item_id for r in inv_records]
        dish_ids  = [r.dish_id for r in dish_records]
        combo_ids = [r.combo_id for r in combo_records]

        inv_map = {
            i.id: i.name
            for i in db.query(Inventory).filter(Inventory.id.in_(inv_ids)).all()
        } if inv_ids else {}

        dish_map = {
            d.id: d.name
            for d in db.query(Dish).filter(Dish.id.in_(dish_ids)).all()
        } if dish_ids else {}

        combo_map = {
            c.id: c.name
            for c in db.query(Combo).filter(Combo.id.in_(combo_ids)).all()
        } if combo_ids else {}

        # ── aggregate inventory records with unit normalization ───────────────
        inv_agg: dict[int, dict] = {}  # item_id -> {base_qty, base_unit, total_cost}

        for rec in inv_records:
            item_id = rec.inventory_item_id
            unit_str = _normalize_unit(rec.unit or "pcs")
            qty = Decimal(str(rec.quantity_wasted or 0))
            cost = Decimal(str(rec.cost_value or 0))

            base_qty, base_unit = _to_base(qty, unit_str)

            if item_id not in inv_agg:
                inv_agg[item_id] = {"base_qty": Decimal("0"), "base_unit": base_unit, "total_cost": Decimal("0")}

            inv_agg[item_id]["base_qty"]    += base_qty
            inv_agg[item_id]["total_cost"]  += cost

        # ── aggregate dish records with unit normalization ────────────────────
        dish_agg: dict[int, dict] = {}

        for rec in dish_records:
            dish_id = rec.dish_id
            unit_str = _normalize_unit(rec.unit or "pcs")
            qty = Decimal(str(rec.quantity_wasted or 0))
            cost = Decimal(str(rec.cost_value or 0))

            base_qty, base_unit = _to_base(qty, unit_str)

            if dish_id not in dish_agg:
                dish_agg[dish_id] = {"base_qty": Decimal("0"), "base_unit": base_unit, "total_cost": Decimal("0")}

            dish_agg[dish_id]["base_qty"]   += base_qty
            dish_agg[dish_id]["total_cost"] += cost

        # ── aggregate combo records with unit normalization ───────────────────
        combo_agg: dict[int, dict] = {}

        for rec in combo_records:
            combo_id = rec.combo_id
            unit_str = _normalize_unit(rec.unit or "pcs")
            qty = Decimal(str(rec.quantity_wasted or 0))
            cost = Decimal(str(rec.cost_value or 0))

            base_qty, base_unit = _to_base(qty, unit_str)

            if combo_id not in combo_agg:
                combo_agg[combo_id] = {"base_qty": Decimal("0"), "base_unit": base_unit, "total_cost": Decimal("0")}

            combo_agg[combo_id]["base_qty"]   += base_qty
            combo_agg[combo_id]["total_cost"] += cost

        # ── merge + sort ──────────────────────────────────────────────────────
        combined = []

        for item_id, agg in inv_agg.items():
            display_qty, display_unit = _from_base(agg["base_qty"], agg["base_unit"])
            combined.append({
                "item_name"   : inv_map.get(item_id, "Unknown"),
                "wastage_type": "inventory",
                "total_qty"   : float(round(display_qty, 3)),
                "unit"        : display_unit,
                "total_cost"  : float(round(agg["total_cost"], 2)),
            })

        for dish_id, agg in dish_agg.items():
            display_qty, display_unit = _from_base(agg["base_qty"], agg["base_unit"])
            combined.append({
                "item_name"   : dish_map.get(dish_id, "Unknown"),
                "wastage_type": "dish",
                "total_qty"   : float(round(display_qty, 3)),
                "unit"        : display_unit,
                "total_cost"  : float(round(agg["total_cost"], 2)),
            })

        for combo_id, agg in combo_agg.items():
            display_qty, display_unit = _from_base(agg["base_qty"], agg["base_unit"])
            combined.append({
                "item_name"   : combo_map.get(combo_id, "Unknown"),
                "wastage_type": "combo",
                "total_qty"   : float(round(display_qty, 3)),
                "unit"        : display_unit,
                "total_cost"  : float(round(agg["total_cost"], 2)),
            })

        combined.sort(key=lambda x: x["total_cost"], reverse=True)
        top_items = combined[:limit]

        for rank, item in enumerate(top_items, start=1):
            item["rank"] = rank

        return {
            "success"   : True,
            "period"    : period,
            "date_range": {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to"  : end_dt.strftime("%d-%m-%Y"),
            },
            "top_wastage_items": top_items,
        }

    except Exception as e:
        logger.exception(f"Error fetching top wastage items: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch top wastage items")
    
# Add temporarily at the top of the function
@router.get("/reports/wastage-by-item-type", status_code=status.HTTP_200_OK)
def get_wastage_by_item_type(
    period    : str            = Query("monthly", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    db        : Session        = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_wastage_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        records = (
            db.query(Wastage)
            .filter(
                Wastage.tenant_id    == current_user.tenant_id,
                Wastage.wastage_date >= start_dt,
                Wastage.wastage_date <= end_dt,
                Wastage.wastage_type == WastageType.INVENTORY,
                Wastage.is_breakdown == False,
                Wastage.inventory_item_id.isnot(None),
            )
            .all()
        )

        # ── resolve item_category_type via Inventory → ItemCategory ──────────
        inv_ids = list({w.inventory_item_id for w in records})

        # inv_category_rows = (
        #     db.query(Inventory.id, ItemCategory.category_type)
        #     .join(ItemCategory, ItemCategory.id == Inventory.item_category_id, isouter=True)
        #     .filter(Inventory.id.in_(inv_ids))
        #     .all()
        # )

        # inv_type_map: inventory_id → "perishable" | "non_perishable" | None
        inv_type_map = {
            row.id: row.category_type.value if row.category_type else None
            for row in db.query(Inventory.id, Inventory.category_type)
                         .filter(Inventory.id.in_(inv_ids))
                         .all()
        }

        # ── build buckets ─────────────────────────────────────────────────────
        perishable_buckets    : dict = defaultdict(float)
        non_perishable_buckets: dict = defaultdict(float)

        for w in records:
            if not w.wastage_date:
                continue

            item_type = inv_type_map.get(w.inventory_item_id)

            if period == "daily":
                key = w.wastage_date.strftime("%H:00")
            elif period == "weekly":
                key = w.wastage_date.strftime("%a")
            else:
                key = w.wastage_date.strftime("%d %b")

            cost = float(w.cost_value or 0)

            if item_type == "perishable":
                perishable_buckets[key] += cost
            elif item_type == "non_perishable":
                non_perishable_buckets[key] += cost

        # ── build ordered keys ────────────────────────────────────────────────
        if period == "daily":
            all_keys = [f"{h:02d}:00" for h in range(24)]
        elif period == "weekly":
            all_keys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        else:
            delta    = (end_dt.date() - start_dt.date()).days + 1
            all_keys = [
                (start_dt + timedelta(days=i)).strftime("%d %b")
                for i in range(delta)
            ]

        trends = [
            {
                "label"         : key,
                "perishable"    : round(perishable_buckets[key], 2),
                "non_perishable": round(non_perishable_buckets[key], 2),
            }
            for key in all_keys
        ]

        return {
            "success"   : True,
            "period"    : period,
            "date_range": {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to"  : end_dt.strftime("%d-%m-%Y"),
            },
            "trends": trends,
        }

    except Exception as e:
        logger.exception(f"Error fetching wastage by item type: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch wastage by item type")
    
@router.get("/photo/{wastage_id}")
async def get_wastage_photo(
    wastage_id: str,
    db: Session = Depends(get_db),
    # current_user: User = Depends(get_current_user),
):
    wastage = db.query(Wastage).filter(
        Wastage.id == wastage_id,
        # Wastage.tenant_id == current_user.tenant_id,
    ).first()

    if not wastage:
        raise HTTPException(status_code=404, detail="Wastage record not found")
    if not wastage.photo_url:
        raise HTTPException(status_code=404, detail="No photo found")

    # ← old records with localhost URL
    if "amazonaws.com" not in wastage.photo_url:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=wastage.photo_url)

    # ← new records with S3 URL
    presigned_url = get_presigned_url(wastage.photo_url, expiry=60)
    async with httpx.AsyncClient() as client:
        response = await client.get(presigned_url)
        return StreamingResponse(
            response.aiter_bytes(),
            media_type=response.headers["content-type"],
        )    
    
@router.put("/edit-wastage/{wastage_id}", status_code=status.HTTP_200_OK)
async def edit_wastage(
    wastage_id: UUID,
    wastage_reason: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    wastage_date: Optional[str] = Form(None),        
    photo: UploadFile = File(default=None),
    quantity_wasted: Optional[float] = Form(None),
    unit: Optional[str] = Form(None),
    inventory_item_id: Optional[int] = Form(None),
    inventory_batch_id: Optional[int] = Form(None),
    dish_id: Optional[int] = Form(None),
    semi_finished_product_id: Optional[int] = Form(None),   
    combo_id: Optional[int] = Form(None),                   
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    # ── Parse wastage_date safely ─────────────────────────────────────────
    parsed_wastage_date: Optional[date] = None
    if wastage_date:
        try:
            # Accept both "2024-01-25" and "2024-01-25T00:00:00" formats
            parsed_wastage_date = datetime.fromisoformat(wastage_date).date()
        except ValueError:
            try:
                parsed_wastage_date = date.fromisoformat(wastage_date)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid wastage_date format. Use YYYY-MM-DD or ISO datetime.",
                )

    # ── Upload new photo before DB work ──────────────────────────────────
    photo_url = None
    if photo and photo.filename:
        photo_url = await upload_wastage_photo(photo)

    try:
        result = WastageService.edit_wastage(
            db                       = db,
            tenant_id                = current_user.tenant_id,
            wastage_id               = wastage_id,
            user_id                  = current_user.id,
            wastage_reason           = wastage_reason,
            notes                    = notes,
            wastage_date             = parsed_wastage_date,
            photo_url                = photo_url,
            quantity_wasted          = quantity_wasted,
            unit                     = unit,
            inventory_item_id        = inventory_item_id,
            inventory_batch_id       = inventory_batch_id,
            dish_id                  = dish_id,
            semi_finished_product_id = semi_finished_product_id,
            combo_id                 = combo_id,
        )
        return {"success": True, "message": "Wastage updated successfully", "data": result}

    except HTTPException:
        raise  # re-raise HTTPExceptions from service (stock validation errors etc.)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("[EDIT WASTAGE] Unexpected error wastage_id=%s", wastage_id)
        raise HTTPException(status_code=500, detail=str(e))