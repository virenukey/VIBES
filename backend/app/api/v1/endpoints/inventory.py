"""
app/api/v1/endpoints/inventory.py
Inventory management endpoints
"""
from decimal import Decimal
from enum import Enum
from io import BytesIO
import math
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile , status
import openpyxl
from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime, timedelta, timezone
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from pydantic import BaseModel
from app.api.deps import get_db
from app.models.dish import DishIngredient
from app.models.expense import Expense
from app.models.inventory import Inventory, InventoryBatch, InventoryTransaction,ItemCategory, StorageLocation, TransactionType,PerishableLifecycle
from app.models.users import User
from app.models.wastage_model import Wastage, WastageReason, WastageType
from app.schemas.batch import BatchCreate, BatchUpdate
from app.schemas.inventory import InventoryListResponse, InventoryOut, InventoryResponse,InventoryUpdate,InventoryItemCreate, ItemCategoryListResponseAll, ItemCategoryOut,ItemPerishableNonPerishable,ItemCategoryCreate,ItemCategoryUpdate,ItemCategoryResponse
from app.services.inventory_service import InventoryService
from app.schemas.inventory_storage import StorageLocationCreate,StorageLocationUpdate,StorageLocationResponse
from app.utils.auth_helper import get_current_user,get_tanant_scope
from app.schemas.common import ApiResponse
from app.utils.inventory_batch_helper import calculate_days_until_expiry, determine_lifecycle_stage, generate_batch_number_sequential, sync_dish_ingredient_costs,sync_inventory_totals
from app.utils.response_helper import success_response
from app.tasks import update_batch_lifecycles_status
import pandas as pd
import logging
import re

logger = logging.getLogger(__name__)

from app.models.inventory import UnitType

router = APIRouter()

class StorageLocationCreateResponse(BaseModel):
    status_code: int
    message: str
    location: StorageLocationResponse
    
class StorageLocationsListResponse(BaseModel):
    data: list[StorageLocationResponse]

class StorageLocationDetailResponse(BaseModel):
    status: int
    message: str
    data: StorageLocationResponse  

class StorageLocationUpdateResponse(BaseModel):
    status: int
    message: str
    data: StorageLocationResponse
class StorageLocationDeleteResponse(BaseModel):
    status: int
    message: str
    data: StorageLocationResponse    

@router.post("/add_item", status_code=status.HTTP_201_CREATED)
def add_item(
    item: InventoryItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    logger.info(f"[add_item] START - user_id={current_user.id}, tenant_id={current_user.tenant_id}")
    logger.info(f"[add_item] Payload: {item.dict()}")

    if not current_user.tenant_id:
        logger.warning(f"[add_item] No tenant_id for user_id={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )

    try:
        # ── 1. Resolve storage location ───────────────────────────────────────
        if item.storage_location_id is not None and item.storage_location_id > 0:
            logger.info(f"[add_item] Resolving storage_location_id={item.storage_location_id}")
            storage_location = (
                db.query(StorageLocation)
                .filter(
                    StorageLocation.id == item.storage_location_id,
                    StorageLocation.tenant_id == current_user.tenant_id,
                )
                .first()
            )
            if not storage_location:
                logger.warning(
                    f"[add_item] Storage location not found: id={item.storage_location_id}, tenant_id={current_user.tenant_id}"
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Storage location not found",
                )
            logger.info(f"[add_item] Storage location resolved: {storage_location.id}")

        # ── 2. Duplicate name check ───────────────────────────────────────────
        normalized_name = item.name.strip().lower()
        logger.info(f"[add_item] Checking duplicate for name='{normalized_name}', tenant_id={current_user.tenant_id}")
        existing = (
            db.query(Inventory)
            .filter(
                func.lower(Inventory.name) == normalized_name,
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.is_active == True,
            )
            .first()
        )
        if existing:
            logger.warning(
                f"[add_item] Duplicate found: existing_id={existing.id}, name='{existing.name}', tenant_id={existing.tenant_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Inventory item '{item.name}' already exists",
            )
        logger.info(f"[add_item] No duplicate found, proceeding to create")

        # ── 3. Create inventory item ──────────────────────────────────────────
        logger.info(f"[add_item] Building Inventory object with fields: "
                    f"name={item.name!r}, category_type={item.category_type!r}, "
                    f"sku={item.sku!r}, unit={item.unit!r}, type={item.type!r}, "
                    f"reorder_point={item.reorder_point!r}, expiry_date={item.expiry_date!r}, "
                    f"purchase_unit={item.purchase_unit!r}, purchase_unit_size={item.purchase_unit_size!r}, "
                    f"shelf_life_in_days={item.shelf_life_in_days!r}, is_fixed_cost={item.is_fixed_cost!r}")

        inventory_item = Inventory(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            storage_location_id=item.storage_location_id if item.storage_location_id else None,
            name=item.name,
            category_type=item.category_type,
            sku=item.sku,
            quantity=0,
            current_quantity=0,
            unit=item.unit,
            price_per_unit=0,
            unit_cost=0,
            total_cost=0,
            type=item.type or "",
            reorder_point=item.reorder_point,
            expiry_date=item.expiry_date,
            purchase_unit=item.purchase_unit,
            purchase_unit_size=item.purchase_unit_size,
            shelf_life_in_days=item.shelf_life_in_days,
            date_added=item.date_added or datetime.utcnow(),
            is_active=True,
            is_fixed_cost=item.is_fixed_cost,
        )
        logger.info(f"[add_item] Inventory object built, calling db.add()")

        db.add(inventory_item)
        logger.info(f"[add_item] db.add() done, calling db.commit()")

        db.commit()
        logger.info(f"[add_item] db.commit() done, calling db.refresh()")

        db.refresh(inventory_item)
        logger.info(f"[add_item] db.refresh() done, inventory_item.id={inventory_item.id}")

        return {
            "success": True,
            "message": "Inventory item added successfully",
            "data": inventory_item,
        }

    except HTTPException:
        logger.info(f"[add_item] HTTPException raised, rolling back")
        db.rollback()
        raise

    except Exception as e:
        logger.error(f"[add_item] UNEXPECTED ERROR: {type(e).__name__}: {e}")
        logger.error(f"[add_item] Full traceback:\n{traceback.format_exc()}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add inventory item | {type(e).__name__}: {e}",
        )
    
# class UnitType(str, Enum):
#     KILOGRAM = "kg"
#     GRAM = "gm"
#     MILLIGRAM = "mg"
#     LITER = "liter"
#     MILLILITER = "ml"
#     BOTTLE = "bottle"

UNIT_MAPPING = {
    # kg
    "kg": "kg", "kgs": "kg", "kilogram": "kg", "kilograms": "kg",
    # gm
    "g": "gm", "gm": "gm", "gram": "gm", "grams": "gm",
    # mg
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    # liter
    "l": "liter", "liter": "liter", "litre": "liter", "ltr": "liter",
    # ml
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    # pcs  ← "piece/pieces/pcs" all map to "pcs" now
    "pcs": "pcs", "piece": "pcs", "pieces": "pcs", "ps": "pcs", "pis": "pcs",
    # packet
    "packet": "packet", "packets": "packet", "pkt": "packet", "pkd": "packet",
    "pkg": "packet", "pack": "packet", "pouch": "packet",
    # box
    "box": "box", "boxes": "box",
    # sheet
    "sheet": "sheet", "sheets": "sheet",
    # carton
    "carton": "carton", "cartons": "carton",
    # dozen
    "dozen": "dozen",
    # bundle
    "bundle": "bundle", "bundles": "bundle", "bandel": "bundle",
    # roll
    "roll": "roll", "rolls": "roll",
    # sachet
    "sachet": "sachet", "sachets": "sachet",
    # bottle
    "bottle": "bottle", "bottles": "bottle", "bottel": "bottle",
    # can
    "can": "can", "cans": "can",
    # bag
    "bag": "bag", "bags": "bag",
    # m / mm / cm
    "m": "m", "meter": "m", "metre": "m",
    "mm": "mm", "millimeter": "mm", "millimetre": "mm",
    "cm": "cm", "centimeter": "cm", "centimetre": "cm",

    "rupee": "rupee", "rupees": "rupee", "rs": "rupee", "inr": "rupee", "₹": "rupee",

}

@router.post("/add_items_via_excel", status_code=status.HTTP_201_CREATED)
def add_items_via_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Upload .xlsx or .xls only",
        )

    try:
        file.file.seek(0)
        contents = file.file.read()

        if len(contents) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty"
            )

        df = pd.read_excel(BytesIO(contents), engine="openpyxl", header=0)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to read Excel file: {str(e)}",
        )

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Excel file is empty",
        )

    def safe_get(row, col, default=None):
        """Safely get a value from a row, returning default if missing or NaN."""
        val = row.get(col, default)
        try:
            if pd.isna(val):
                return default
        except (TypeError, ValueError):
            pass
        if isinstance(val, str) and val.strip().lower() in ("nan", "none", ""):
            return default
        return val

    validated_rows = []
    skipped_rows = []

    for index, row in df.iterrows():
        row_number = index + 2  # account for header + skiprows

        # ── 1. Name — only hard requirement ──────────────────────────────────
        name = safe_get(row, "name")
        if not name:
            skipped_rows.append({"row": row_number, "reason": "Missing item name"})
            continue
        name = str(name).strip()
        if not name:
            skipped_rows.append({"row": row_number, "reason": "Empty item name"})
            continue

        # ── 2. Skip duplicates silently ───────────────────────────────────────
        existing = db.query(Inventory).filter(
            Inventory.name == name,
            Inventory.tenant_id == current_user.tenant_id,
            Inventory.is_active == True,
        ).first()
        if existing:
            skipped_rows.append({"row": row_number, "item_name": name, "reason": "Already exists"})
            continue

        # ── 3. Unit — fall back to None if invalid/missing ────────────────────
        unit = None
        raw_unit = safe_get(row, "unit")
        if raw_unit:
            raw_unit_str = str(raw_unit).strip().lower()
            unit = UNIT_MAPPING.get(raw_unit_str)  # None if not found

        # ── 4. Category — skip row silently if not found ──────────────────────
        category_id = None
        category_name = safe_get(row, "item_category_name")
        if category_name:
            category_name = str(category_name).strip()
            category = db.query(ItemCategory).filter(
                func.lower(ItemCategory.name) == category_name.lower(),
                ItemCategory.tenant_id == current_user.tenant_id,
            ).first()
            if category:
                category_id = category.id

        # ── 4b. Category type — optional enum ────────────────────────────────
        category_type = None
        raw_ct = safe_get(row, "category_type")
        if raw_ct:
            raw_ct_str = str(raw_ct).strip().lower()
            # Map common inputs to your enum values
            for enum_val in ItemPerishableNonPerishable:
                if raw_ct_str == enum_val.value.lower():
                    category_type = enum_val
                    break        
            # if category not found, just leave category_id as None

        # ── 5. Storage location — optional, skip silently if not found ────────
        storage_location_id = None
        location_name = safe_get(row, "storage_location_name")
        if location_name:
            location_name = str(location_name).strip()
            storage = db.query(StorageLocation).filter(
                func.lower(StorageLocation.name) == location_name.lower(),
                StorageLocation.tenant_id == current_user.tenant_id,
            ).first()
            if storage:
                storage_location_id = storage.id
            # if not found, just ignore

        # ── 6. Purchase unit — optional ───────────────────────────────────────
        purchase_unit = None
        raw_pu = safe_get(row, "purchase_unit")
        if raw_pu:
            purchase_unit = UNIT_MAPPING.get(str(raw_pu).strip().lower())

        # ── 7. Reorder point — optional ───────────────────────────────────────
        reorder_point = None
        raw_rp = safe_get(row, "reorder_point")
        if raw_rp is not None:
            try:
                reorder_point = float(raw_rp)
            except (ValueError, TypeError):
                pass

        # ── 8. Shelf life — optional ──────────────────────────────────────────
        shelf_life_in_days = None
        raw_sl = safe_get(row, "shelf_life_in_days")
        if raw_sl is not None:
            try:
                shelf_life_in_days = int(float(raw_sl))
            except (ValueError, TypeError):
                pass

        # ── 9. Purchase unit size — optional ──────────────────────────────────
        purchase_unit_size = None
        raw_pus = safe_get(row, "purchase_unit_size")
        if raw_pus is not None:
            try:
                purchase_unit_size = float(raw_pus)
            except (ValueError, TypeError):
                pass

        # ── 10. Date added — optional ─────────────────────────────────────────
        date_added = None
        raw_date = safe_get(row, "date_added")
        if raw_date is not None:
            try:
                if isinstance(raw_date, datetime):
                    date_added = raw_date
                else:
                    date_added = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d")
            except (ValueError, TypeError):
                pass  # invalid date → use utcnow() at insert time

        # ── 11. SKU and type — optional strings ───────────────────────────────
        sku = safe_get(row, "sku")
        item_type = str(safe_get(row, "type", "")).strip()

        validated_rows.append({
            "name": name,
            "unit": unit,
            "item_category_id": category_id,
            "storage_location_id": storage_location_id,
            "sku": sku,
            "reorder_point": reorder_point,
            "shelf_life_in_days": shelf_life_in_days,
            "purchase_unit": purchase_unit,
            "purchase_unit_size": purchase_unit_size,
            "type": item_type,
            "date_added": date_added,
            "category_type": category_type,
        })

    # ── Save all validated rows ───────────────────────────────────────────────
    try:
        for row_data in validated_rows:
            inventory_item = Inventory(
                user_id=current_user.id,
                tenant_id=current_user.tenant_id,
                storage_location_id=row_data["storage_location_id"],
                item_category_id=row_data["item_category_id"],
                name=row_data["name"],
                sku=row_data["sku"],
                unit=row_data["unit"],
                type=row_data["type"],
                reorder_point=row_data["reorder_point"],
                purchase_unit=row_data["purchase_unit"],
                purchase_unit_size=row_data["purchase_unit_size"],
                shelf_life_in_days=row_data["shelf_life_in_days"],
                date_added=row_data["date_added"] or datetime.utcnow(),
                is_active=True,
                quantity=0,
                current_quantity=0,
                price_per_unit=0,
                unit_cost=0,
                total_cost=0,
                category_type=row_data["category_type"],
            )
            db.add(inventory_item)

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while saving Excel data",
        )

    return {
        "success": True,
        "message": "Upload complete",
        "summary": {
            "total_rows": len(df),
            "saved_count": len(validated_rows),
            "skipped_count": len(skipped_rows),
        },
        "skipped_rows": skipped_rows,  # remove this line if you want zero feedback
    }

@router.get("/")
def get_all_inventory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    # --- FILTERS ---
    search: Optional[str] = Query(None, description="Search by item name or category"),
    lifecycle_stage: Optional[str] = Query(None, description="Status filter: fresh, expired, etc."),
    category_type: Optional[str] = Query(None, description="Filter by perishable or non_perishable"),
    item_category: Optional[str] = Query(None, description="Filter by category name"),
    storage_location: Optional[str] = Query(None, description="Filter by storage location name"),
    unit: Optional[str] = Query(None, description="Filter by unit e.g. kg, gm, carton"),
    min_quantity: Optional[float] = Query(None),
    max_quantity: Optional[float] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_total_cost: Optional[float] = Query(None),
    max_total_cost: Optional[float] = Query(None),
    date_from: Optional[date] = Query(None, description="date_added from"),
    date_to: Optional[date] = Query(None, description="date_added to"),
    expiry_from: Optional[date] = Query(None, description="expiry_date from"),
    expiry_to: Optional[date] = Query(None, description="expiry_date to"),
    # --- SORTING ---
    sort_by: Optional[str] = Query(None, description="name, category, total_cost, quantity, price_per_unit, storage, unit,lifecycle_stage, current_quantity"),
    sort_order: Optional[str] = Query("asc", description="asc or desc"),
    # --- PAGINATION ---
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Rows per page"),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required"
        )

    SORTABLE_FIELDS = {
        "name": Inventory.name,
        "total_cost": Inventory.total_cost,
        "quantity": Inventory.quantity,
        "price_per_unit": Inventory.price_per_unit,
        "unit": Inventory.unit,
        "date_added": Inventory.date_added,
        "expiry_date": Inventory.expiry_date,
        "lifecycle_stage": Inventory.lifecycle_stage,
        "current_quantity": Inventory.current_quantity,
        "category": ItemCategory.name,
        "storage": StorageLocation.name,
    }

    # --- Validate before try block so HTTPException isn't swallowed ---
    lifecycle_stage_enum = None
    if lifecycle_stage:
        try:
            lifecycle_stage_enum = PerishableLifecycle(lifecycle_stage.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid lifecycle_stage. Allowed values: {[e.value for e in PerishableLifecycle]}"
            )

    category_type_enum = None
    if category_type:
        try:
            category_type_enum = ItemPerishableNonPerishable(category_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category_type. Allowed values: {[e.value for e in ItemPerishableNonPerishable]}"
            )

    if sort_by and sort_by not in SORTABLE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort_by. Allowed values: {list(SORTABLE_FIELDS.keys())}"
        )

    if sort_order not in ("asc", "desc"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sort_order must be 'asc' or 'desc'"
        )

    try:
        # --- BASE QUERY ---
        query = (
            db.query(Inventory)
            .filter(Inventory.tenant_id == current_user.tenant_id, Inventory.is_active == True)
        )

        # --- CATEGORY JOIN: innerjoin only when filtering by category name ---
        if item_category:
            query = query.join(Inventory.item_category)
        else:
            query = query.outerjoin(Inventory.item_category)

        # --- STORAGE JOIN: innerjoin only when filtering by storage ---
        if storage_location:
            query = query.join(Inventory.storage_location)
        else:
            query = query.outerjoin(Inventory.storage_location)

        # --- SEARCH (name or category name, outerjoin-safe) ---
        if search:
            query = query.filter(
                or_(
                    Inventory.name.ilike(f"%{search}%"),
                    and_(
                        Inventory.item_category_id.isnot(None),
                        ItemCategory.name.ilike(f"%{search}%")
                    )
                )
            )

        # --- FILTERS ---
        if lifecycle_stage_enum:
            query = query.filter(Inventory.lifecycle_stage == lifecycle_stage_enum)

        if category_type_enum:
            query = query.filter(Inventory.category_type == category_type_enum)

        if item_category:
            query = query.filter(ItemCategory.name.ilike(f"%{item_category}%"))

        if storage_location:
            query = query.filter(StorageLocation.name.ilike(f"%{storage_location}%"))

        if unit:
            query = query.filter(Inventory.unit.ilike(f"%{unit}%"))

        if min_quantity is not None:
            query = query.filter(Inventory.quantity >= min_quantity)
        if max_quantity is not None:
            query = query.filter(Inventory.quantity <= max_quantity)

        if min_price is not None:
            query = query.filter(Inventory.price_per_unit >= min_price)
        if max_price is not None:
            query = query.filter(Inventory.price_per_unit <= max_price)

        if min_total_cost is not None:
            query = query.filter(Inventory.total_cost >= min_total_cost)
        if max_total_cost is not None:
            query = query.filter(Inventory.total_cost <= max_total_cost)

        if date_from is not None:
            query = query.filter(Inventory.date_added >= date_from)
        if date_to is not None:
            query = query.filter(Inventory.date_added <= date_to)

        if expiry_from is not None:
            query = query.filter(Inventory.expiry_date >= expiry_from)
        if expiry_to is not None:
            query = query.filter(Inventory.expiry_date <= expiry_to)

        # --- SORTING ---
        if sort_by:
            sort_column = SORTABLE_FIELDS[sort_by]
            query = query.order_by(
                desc(sort_column) if sort_order == "desc" else asc(sort_column)
            )

        # --- PAGINATION ---
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()

        return {
            "success": True,
            "message": "Inventory fetched successfully",
            "meta": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": math.ceil(total / page_size) if total else 1,
                "filters_applied": {
                    "search": search,
                    "lifecycle_stage": lifecycle_stage,
                    "category_type": category_type,
                    "item_category": item_category,
                    "storage_location": storage_location,
                    "unit": unit,
                    "quantity_range": [min_quantity, max_quantity],
                    "price_range": [min_price, max_price],
                    "total_cost_range": [min_total_cost, max_total_cost],
                    "date_added_range": [str(date_from), str(date_to)],
                    "expiry_date_range": [str(expiry_from), str(expiry_to)],
                },
                "sort": {
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                }
            },
            "data": [
                {
                    "id": item.id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "sku": item.sku,
                    "item_category": item.item_category.name if item.item_category else None,
                    "storage_location": item.storage_location.name if item.storage_location else None,
                    "price_per_unit": item.price_per_unit,
                    "total_cost": item.total_cost,
                    "purchase_unit": item.purchase_unit,
                    "purchase_unit_size": item.purchase_unit_size,
                    "type": item.type,
                    "lifecycle_stage": item.lifecycle_stage,
                    "shelf_life_in_days": item.shelf_life_in_days,
                    "date_added": item.date_added,
                    "expiry_date": item.expiry_date,
                    "current_quantity": item.current_quantity,
                    "category_type": item.category_type,
                    "is_fixed_cost": item.is_fixed_cost,
                }
                for item in items
            ]
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch inventory",
        )
    
@router.get("/search", response_model=InventoryListResponse, status_code=status.HTTP_200_OK)
def search_inventory(
    name: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
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
            detail="start_date cannot be after end_date",
        )
    
    try:

        service = InventoryService(db)
        inventory = service.search_items (
            tenant_id=current_user.tenant_id,
            name=name,
            type=type,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "success": True,
            "message": "Inventory search completed",
            "data": inventory,
        }
    
    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search inventory",
        )

@router.put("/{item_id}", status_code=status.HTTP_200_OK)
def update_inventory_item(
    item_id: int,
    item_update: InventoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    
    try:
        service = InventoryService(db)
        updated_item = service.update_item( 
            item_id=item_id,
            tenant_id=current_user.tenant_id,
            item_update=item_update,
        )
        
        if not updated_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventory item not found",
            )
        
        return {
            "success": True,
            "status_code": status.HTTP_200_OK,
            "message": "Inventory item updated successfully",
            "data": updated_item,
        }
    
    except HTTPException:
        # Don't catch and return - just re-raise
        raise
    
    except SQLAlchemyError:
        db.rollback()
        # Don't return dict - raise HTTPException
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update inventory item due to database error"
        )
    
    except Exception:
        db.rollback()
        # Don't return dict - raise HTTPException
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update inventory item"
        )

@router.delete("/{item_id}")
def delete_inventory_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        item = db.query(Inventory).filter(
            Inventory.id == item_id,
            Inventory.tenant_id == current_user.tenant_id
        ).first()

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inventory item not found"
            )

        is_used = db.query(DishIngredient).filter(
            DishIngredient.ingredient_id == item_id
        ).first()

        if is_used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete inventory item as it is used in one or more dishes. Remove it from all dishes first."
            )

        db.delete(item)
        db.commit()

        return {
            "success": True,
            "status_code": 200,
            "message": "Inventory item deleted successfully"
        }

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete inventory item due to database error"
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting inventory item"
        )

@router.delete("/")
def delete_all_inventory(
    confirm: bool = Query(False, description="Confirm deletion"),
    db: Session = Depends(get_db),
    current_user : User = Depends(get_current_user)
):
    
    if not current_user.tenant_id:
        return {
            "success": False,
            "status_code": status.HTTP_403_FORBIDDEN,
            "message": "Tenant access required",
        }
    """Delete all inventory items (use with caution)"""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Please confirm deletion by setting confirm=true"
        )
    
    service = InventoryService(db)
    deleted_count = service.delete_all_items()
    return {
        "message": f"Deleted {deleted_count} item(s) from inventory"
    }

#ITEM-CATEGORIES API'S
@router.post("/add-item-category",response_model=ItemCategoryResponse)
def create_item_category(
    data: ItemCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)

):
    # if not current_user.tenant_id:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Tenant access required",
    #     )

    tenant_id = get_tanant_scope(
        current_user=current_user,
        requested_tenant_id=data.tenant_id
)
    
    try:
        category_type_enum = ItemPerishableNonPerishable(data.category_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category_type: {data.category_type}",
        )
        
    existing =( db.query(ItemCategory).filter(
        ItemCategory.name == data.name,
        ItemCategory.tenant_id == tenant_id,
    ).first() )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Category with this name already exists"
        )
    try:
        
        category = ItemCategory(
            tenant_id=tenant_id,
            name=data.name,
            category_type=category_type_enum.value,
            user_id=current_user.id
        )

        db.add(category)
        db.commit()
        db.refresh(category)

        return success_response(
        data=category,
        message="Item category created successfully",
        # status_code=status.HTTP_201_CREATED,
    )
    
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create item category",
        )

@router.get("/get-item-categories")
def list_item_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    try:
        categories = (
            db.query(ItemCategory)
            .filter(ItemCategory.tenant_id == current_user.tenant_id)
            .order_by(ItemCategory.name)
            .all()
    )


        return {
                "success": True,
                "status_code": 200,
                "message": "Item categories fetched successfully",
                "data": categories
            } 
     
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch item categories",
        )   

@router.get("/{item_id}",status_code=status.HTTP_200_OK)
def get_inventory_item(
    item_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    
    try:
        service = InventoryService(db)
        item = service.get_item_by_id(
            item_id=item_id,
            tenant_id=current_user.tenant_id,
        )

        if not item:
            # Option 1: Return empty data (if you want 200 OK with empty response)
            return {
                "success": False,
                "message": "Inventory item not found",
                "data": None,  # or [] if data should be a list
            }
            
            # Option 2: Raise 404 (standard REST practice - uncomment if you prefer this)
            # raise HTTPException(
            #     status_code=status.HTTP_404_NOT_FOUND,
            #     detail="Inventory item not found",
            # )
        
        return {
           "success": True,
                "message": "Inventory item fetched successfully",
                "data": {
                    "id": item.id,
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "sku":item.sku,
                    "item_category": item.item_category.name if item.item_category else None,
                    "storage_location": item.storage_location.name if item.storage_location else None,
                    "price_per_unit": item.price_per_unit,
                    "total_cost": item.total_cost,
                    "purchase_unit": item.purchase_unit,
                    "purchase_unit_size": item.purchase_unit_size,
                    "type": item.type,
                    "lifecycle_stage": item.lifecycle_stage,
                    "shelf_life_in_days": item.shelf_life_in_days,
                    "date_added": item.date_added,
                    "expiry_date": item.expiry_date,
                }
            }


    except HTTPException:
        raise

    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while fetching inventory item",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch inventory item",
        )

@router.get("/get-category-id/{category_id}",response_model=ItemCategoryResponse,status_code=status.HTTP_200_OK)
def get_item_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    
    try:
        category = (
             db.query(ItemCategory)
            .filter(
                ItemCategory.id == category_id,
                ItemCategory.tenant_id == current_user.tenant_id,
            )
            .first()
        )

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item category not found",
            )
        
        return {
            "success": True,
            "message": "Item category fetched successfully",
            "data": category,
            "status_code":status.HTTP_200_OK,
        }
   
    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch item category",
        )

@router.put("/update-item-category/{category_id}", response_model=ItemCategoryResponse)
def update_item_category(
    category_id: int,
    data: ItemCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),

):
    
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    
    category = (
        db.query(ItemCategory).filter(
            ItemCategory.id == category_id,
            ItemCategory.tenant_id == current_user.tenant_id
        ).first()
    )

    if not category:
        raise HTTPException(
            status_code=404,
            detail="Item Category not found"
        )
    try:

        if data.name is not None:
        
            existing =(
               db.query(ItemCategory).filter(ItemCategory.name == data.name,
                    ItemCategory.tenant_id == current_user.tenant_id,
                    ItemCategory.id != category_id,).first()
            )
            if existing:
               raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category with this name already exists",
                )
            category.name = data.name


        if data.category_type is not None:
            try:
                category.category_type = ItemPerishableNonPerishable(data.category_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid category_type: {data.category_type}",
                )
            
       
        db.commit()
        db.refresh(category)

        return success_response(
        data=category,
        message="Item category created successfully",
        # status_code=status.HTTP_201_CREATED,
    )
    
    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update item category",
        )

@router.delete("/delete-item-categories/{category_id}",status_code=status.HTTP_200_OK)
def delete_item_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),

):
    if not current_user.tenant_id:
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    
    try:
        category = (db.query(ItemCategory).filter(
                ItemCategory.id == category_id
            ).first())  

        if not category:
            raise HTTPException(
                status_code=404,
                detail="Item category not found"
            )
        
        if category.inventory_items:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete category with inventory items",
            )
        
        db.delete(category)
        db.commit()

        return {
                "success": True,
                "message": "Item category deleted successfully",
            }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete item category",
        )
    
#STORAGE LOCATION API's
@router.post("/add-storage",response_model=StorageLocationCreateResponse,status_code=status.HTTP_201_CREATED)
def add_storage_location(
    data: StorageLocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    tenant_id = get_tanant_scope(
        current_user=current_user,
        requested_tenant_id=data.tenant_id  
    )
    try:

        existing = db.query(StorageLocation).filter(
            StorageLocation.tenant_id == current_user.tenant_id,
            StorageLocation.name == data.name,
            StorageLocation.is_active == True
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Storage location with this name already exists."
            )
        
        location = StorageLocation(
            tenant_id=tenant_id,
            user_id=current_user.id,
            name=data.name,
            storage_temp_min=data.storage_temp_min,
            storage_temp_max=data.storage_temp_max,
            special_handling_instructions=data.special_handling_instructions,
            is_active=True
        )

        db.add(location)
        db.commit()
        db.refresh(location)

        result = update_batch_lifecycles_status.delay()


        return {
            "status_code": 201,
            "message": "Storage location added successfully!",
            "location": location,
            "result":result.id
        }
    
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Storage location could not be created due to a database constraint"
        )
        
    except HTTPException:
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create storage location"
        )
    
@router.get("/get-all-storage/all", response_model=StorageLocationsListResponse)
def get_storage_locations (
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        locations = db.query(StorageLocation).filter(
                StorageLocation.tenant_id == current_user.tenant_id,
                StorageLocation.is_active == True
            ).offset(skip).limit(limit).all()
       
        return {
            "status": 200,
            "message": "Storage locations fetched successfully",
            "data": locations
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fresh storage locations"
        )    
    
@router.get("/storage-id/{location_id}",response_model=StorageLocationDetailResponse)
def get_location_by_id(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        location = db.query(StorageLocation).filter(
                StorageLocation.id == location_id,
                StorageLocation.tenant_id == current_user.tenant_id,
                StorageLocation.is_active == True
            ).first()

        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storage location not found"
            )

        return {
            "status": 200,
            "message": "Storage locations fetched successfully",
            "data": location
        }

    except HTTPException:
        raise
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch storage location"
        )

@router.put("/update-storage/{location_id}", response_model=StorageLocationUpdateResponse)
def update_location(
    location_id: int,
    data: StorageLocationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        location = db.query(StorageLocation).filter(
            StorageLocation.id == location_id,
            StorageLocation.tenant_id == current_user.tenant_id
        ).first()

        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storage location not found"
            )

        # Prevent renaming to existing name
        if data.name:
            duplicate = db.query(StorageLocation).filter(
                StorageLocation.tenant_id == current_user.tenant_id,
                StorageLocation.name == data.name,
                StorageLocation.id != location_id,
                StorageLocation.is_active == True
            ).first()

            if duplicate:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Storage location with this name already exists"
                )

        for field, value in data.dict(exclude_unset=True).items():
            setattr(location, field, value)

        db.commit()
        db.refresh(location)
        return {
           "status": 200,
            "message": "Storage location updated successfully",
            "data": location  
        }

    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Update violates a database constraint"
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update storage location"
        )

@router.delete("/delete-storage-id/{location_id}", response_model=StorageLocationDeleteResponse)
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        location = db.query(StorageLocation).filter(
            StorageLocation.id == location_id,
            StorageLocation.tenant_id == current_user.tenant_id
        ).first()

        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Storage location not found"
            )

        location.is_active = False
        db.commit()
        db.refresh(location)
        return {
            "status": 200,
            "message": "Storage location deleted successfully",
            "data": location 
        }

    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete storage location"
        )
    
#INVENTORY BATCH API's
@router.post("/items/{item_id}/batches")
def create_batch(
    item_id: int,
    batch_data: BatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    try:
        tenant_id = current_user.tenant_id

        # ══════════════════════════════════════════════════════════════════════
        # VALIDATE — Item exists and belongs to tenant
        # ══════════════════════════════════════════════════════════════════════
        item = db.query(Inventory).filter(
            Inventory.id        == item_id,
            Inventory.tenant_id == tenant_id,
            Inventory.is_active == True,
        ).first()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        if not batch_data.quantity_received:
            raise HTTPException(status_code=400, detail="quantity_received is required")

        if not batch_data.total_cost and not batch_data.unit_cost:
            raise HTTPException(status_code=400, detail="unit_cost is required")

        # ══════════════════════════════════════════════════════════════════════
        # RESOLVE — Costs, unit, dates
        # ══════════════════════════════════════════════════════════════════════
        qty = Decimal(str(batch_data.quantity_received))

        if batch_data.unit_cost:
            resolved_unit_cost  = Decimal(str(batch_data.unit_cost))
            resolved_total_cost = (
                Decimal(str(batch_data.total_cost))
                if batch_data.total_cost
                else resolved_unit_cost * qty
            )
        else:
            resolved_total_cost = Decimal(str(batch_data.total_cost))
            resolved_unit_cost  = resolved_total_cost / qty

        resolved_unit  = batch_data.unit or item.unit
        date_added     = batch_data.date_added or datetime.now(timezone.utc)
        new_batch_date = date_added.date() if hasattr(date_added, "date") else date_added

        # ══════════════════════════════════════════════════════════════════════
        # STEP 1 — Find the next batch after this one (if any)
        # ══════════════════════════════════════════════════════════════════════
        next_batch = (
            db.query(InventoryBatch)
            .filter(
                InventoryBatch.tenant_id         == tenant_id,
                InventoryBatch.inventory_item_id == item_id,
                InventoryBatch.date_added > datetime.combine(
                    new_batch_date, datetime.max.time()
                ).replace(tzinfo=timezone.utc),
            )
            .order_by(InventoryBatch.date_added.asc())
            .first()
        )

        # ══════════════════════════════════════════════════════════════════════
        # STEP 2 — Resolve expiry_date for the new batch
        # ══════════════════════════════════════════════════════════════════════
        if batch_data.expiry_date:
            new_batch_expiry = (
                batch_data.expiry_date.date()
                if hasattr(batch_data.expiry_date, "date")
                else batch_data.expiry_date
            )
        elif next_batch:
            next_batch_date  = (
                next_batch.date_added.date()
                if hasattr(next_batch.date_added, "date")
                else next_batch.date_added
            )
            new_batch_expiry = next_batch_date - timedelta(days=1)
        else:
            new_batch_expiry = None

        # ══════════════════════════════════════════════════════════════════════
        # STEP 3 — Close previous open-ended batches (DATE BOUNDARY ONLY)
        # ══════════════════════════════════════════════════════════════════════
        previous_open_batches = (
            db.query(InventoryBatch)
            .filter(
                InventoryBatch.tenant_id         == tenant_id,
                InventoryBatch.inventory_item_id == item_id,
                InventoryBatch.expiry_date       == None,
                InventoryBatch.date_added < datetime.combine(
                    new_batch_date, datetime.min.time()
                ).replace(tzinfo=timezone.utc),
            )
            .all()
        )

        closed_batch_ids = []
        for old_batch in previous_open_batches:
            old_batch.expiry_date     = new_batch_date - timedelta(days=1)
            old_days_until_expiry     = calculate_days_until_expiry(old_batch.expiry_date)
            old_batch.lifecycle_stage = determine_lifecycle_stage(
                old_days_until_expiry,
                item.fresh_threshold_days       or 3,
                item.near_expiry_threshold_days or 1,
            )
            closed_batch_ids.append(old_batch.id)

            logger.info(
                f"Batch {old_batch.batch_number} closed: "
                f"expiry={old_batch.expiry_date} | "
                f"lifecycle={old_batch.lifecycle_stage} | "
                f"qty_remaining={old_batch.quantity_remaining} (preserved)"
            )

        # ✅ Flush STEP 3 into DB before any further queries
        if closed_batch_ids:
            db.flush()

        # ══════════════════════════════════════════════════════════════════════
        # STEP 4 — Resolve lifecycle_stage for the new batch
        # ══════════════════════════════════════════════════════════════════════
        days_until_expiry = calculate_days_until_expiry(new_batch_expiry)
        lifecycle         = determine_lifecycle_stage(
            days_until_expiry,
            item.fresh_threshold_days       or 3,
            item.near_expiry_threshold_days or 1,
        )

        # ══════════════════════════════════════════════════════════════════════
        # STEP 5 — Resolve packets / pieces / pricing
        # ══════════════════════════════════════════════════════════════════════
        batch_number = generate_batch_number_sequential(
            item_id=item_id,
            db=db,
            prefix="BATCH",
        )

        # total_pieces: provided → else quantity_received × pieces_per_packet
        if batch_data.quantity_received and batch_data.pieces:
            calculated_total_pieces = int(batch_data.quantity_received * batch_data.pieces)
        else:
            calculated_total_pieces = None

        # price_per_packet: provided → else total_cost / packets
        if batch_data.price_per_packet:
            resolved_price_per_packet = batch_data.price_per_packet
        elif resolved_total_cost and batch_data.packets:
            resolved_price_per_packet = float(resolved_total_cost / batch_data.packets)
        else:
            resolved_price_per_packet = None

        # price_per_piece: provided → else total_cost / total_pieces
        if batch_data.price_per_piece:
            resolved_price_per_piece = batch_data.price_per_piece
        elif resolved_total_cost and calculated_total_pieces:
            resolved_price_per_piece = float(resolved_total_cost / calculated_total_pieces)
        else:
            resolved_price_per_piece = None

        # ══════════════════════════════════════════════════════════════════════
        # STEP 6 — Create the new batch
        # ══════════════════════════════════════════════════════════════════════
        batch = InventoryBatch(
            user_id            = current_user.id,
            tenant_id          = tenant_id,
            inventory_item_id  = item_id,
            batch_number       = batch_number,
            expiry_date        = new_batch_expiry,
            quantity_received  = float(qty),
            quantity_remaining = float(qty),
            unit               = resolved_unit,
            packets            = batch_data.packets,
            pieces             = batch_data.pieces,       # pieces_per_packet
            total_pieces       = calculated_total_pieces,
            price_per_packet   = resolved_price_per_packet,
            price_per_piece    = resolved_price_per_piece,
            unit_cost          = resolved_unit_cost,
            total_cost         = resolved_total_cost,
            lifecycle_stage    = lifecycle,
            date_added         = date_added,
            is_active          = True,
        )

        db.add(batch)
        db.flush()

        # ══════════════════════════════════════════════════════════════════════
        # STEP 7 — Purchase transaction
        # ══════════════════════════════════════════════════════════════════════
        db.add(InventoryTransaction(
            tenant_id         = tenant_id,
            inventory_item_id = item_id,
            batch_id          = batch.id,
            transaction_type  = TransactionType.PURCHASE,
            quantity          = float(qty),
            unit_cost         = float(resolved_unit_cost),
            unit              = resolved_unit,
            total_value       = float(resolved_total_cost),
            reference_id      = f"Batch {batch.batch_number} received",
            transaction_date  = date_added,
        ))

        db.flush()

        sync_inventory_totals(item_id, db)

        db.commit()

        return {
            "success":            True,
            "message":            "Batch created successfully",
            "batch_id":           batch.id,
            "batch_number":       batch.batch_number,
            "date_added":         date_added.isoformat(),
            "expiry_date":        new_batch_expiry.isoformat() if new_batch_expiry else None,
            "unit_cost":          float(resolved_unit_cost),
            "total_cost":         float(resolved_total_cost),
            "total_pieces":       calculated_total_pieces,
            "price_per_packet":   resolved_price_per_packet,
            "price_per_piece":    resolved_price_per_piece,
            "lifecycle_stage":    lifecycle.value if lifecycle else None,
            "days_until_expiry":  days_until_expiry,
            "batches_closed":     len(previous_open_batches),
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/items/{item_id}/batches")
def get_batches_by_item(
    item_id: int,
    date_from: date | None = Query(default=None, description="Filter batches added from this date (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="Filter batches added up to this date (YYYY-MM-DD)"),
    date_added_order: str = Query(default="asc", description="Sort direction for date_added (asc or desc)"),
    expiry_date_order: str = Query(default="asc", description="Sort direction for expiry_date (asc or desc)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )

    try:
        item = (
            db.query(Inventory)
            .filter(
                Inventory.id == item_id,
                Inventory.tenant_id == current_user.tenant_id
            )
            .first()
        )

        if not item:
            raise HTTPException(status_code=404, detail="Inventory item not found")

        query = (
            db.query(InventoryBatch)
            .filter(
                InventoryBatch.inventory_item_id == item_id,
                InventoryBatch.tenant_id == current_user.tenant_id,
                InventoryBatch.quantity_remaining > 0,
            )
        )

        if date_from:
            query = query.filter(InventoryBatch.date_added >= date_from)
        if date_to:
            query = query.filter(InventoryBatch.date_added <= date_to)

        date_added_sort = InventoryBatch.date_added.asc() if date_added_order == "asc" else InventoryBatch.date_added.desc()
        expiry_date_sort = InventoryBatch.expiry_date.asc() if expiry_date_order == "asc" else InventoryBatch.expiry_date.desc()
    

        batches = query.order_by(date_added_sort, expiry_date_sort).all()

        # ══════════════════════════════════════════════════════════════════════
        # Recalculate lifecycle_stage live based on today's date.
        # ══════════════════════════════════════════════════════════════════════
        for batch in batches:
            if batch.expiry_date:
                days = calculate_days_until_expiry(batch.expiry_date)
                fresh_lifecycle = determine_lifecycle_stage(
                    days,
                    item.fresh_threshold_days       or 3,
                    item.near_expiry_threshold_days or 1,
                )
                if batch.lifecycle_stage != fresh_lifecycle:
                    batch.lifecycle_stage = fresh_lifecycle

        db.commit()

        # ══════════════════════════════════════════════════════════════════════
        # Serialize
        # ══════════════════════════════════════════════════════════════════════
        def serialize_batch(batch: InventoryBatch) -> dict:
            qty_remaining     = batch.quantity_remaining if batch.quantity_remaining else 0.0
            pieces_per_packet = int(batch.pieces) if batch.pieces else 0

            return {
                "id":                 batch.id,
                "batch_number":       batch.batch_number,
                "inventory_item_id":  batch.inventory_item_id,
                "tenant_id":          str(batch.tenant_id),
                "user_id":            batch.user_id,
                "quantity_received":  batch.quantity_received,
                "quantity_remaining": batch.quantity_remaining,
                "pieces_remaining":   qty_remaining * pieces_per_packet if pieces_per_packet > 0 else None,  # ✅ round to int  # ✅ NEW
                "unit":               batch.unit.value if batch.unit else None,
                "packets":            batch.packets,
                "pieces":             batch.pieces,
                "total_pieces":       batch.total_pieces,
                "price_per_packet":   batch.price_per_packet,
                "price_per_piece":    batch.price_per_piece,
                "unit_cost":          float(batch.unit_cost)  if batch.unit_cost  else None,
                "total_cost":         float(batch.total_cost) if batch.total_cost else None,
                "lifecycle_stage":    batch.lifecycle_stage.value if batch.lifecycle_stage else None,
                "expiry_date":        batch.expiry_date.isoformat() if batch.expiry_date else None,
                "date_added":         batch.date_added.isoformat() if batch.date_added else None,
                "is_active":          batch.is_active,
                "created_at":         batch.created_at.isoformat() if batch.created_at else None,
                "updated_at":         batch.updated_at.isoformat() if batch.updated_at else None,
            }

        return {
            "success":   True,
            "item_id":   item_id,
            "item_name": item.name,
            "count":     len(batches),
            "data":      [serialize_batch(b) for b in batches],
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch batches: {str(e)}"
        )
    
@router.get("/items/{item_id}/get-baches-by-id/{batch_id}")
def get_batch_by_id(
    item_id: int,
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )
    
    try:
        # Verify item belongs to tenant
        item = (
            db.query(Inventory)
            .filter(
                Inventory.id == item_id,
                Inventory.tenant_id == current_user.tenant_id
            )
            .first()
        )

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # Fetch batch
        batch = (
            db.query(InventoryBatch)
            .filter(
                InventoryBatch.id == batch_id,
                InventoryBatch.inventory_item_id == item_id,
                InventoryBatch.tenant_id == current_user.tenant_id,
                InventoryBatch.is_active == True
            )
            .first()
        )

        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        days_until_expiry = calculate_days_until_expiry(batch.expiry_date)

        return {
            "success": True,
            "data": {
                "id": batch.id,
                "batch_number": batch.batch_number,
                "expiry_date": batch.expiry_date,
                "quantity_received": batch.quantity_received,
                "quantity_remaining": batch.quantity_remaining,
                "unit": batch.unit,
                "packets": batch.packets,
                "pieces": batch.pieces,
                "total_pieces": batch.total_pieces,
                "price_per_packet": batch.price_per_packet,
                "price_per_piece": batch.price_per_piece,
                "unit_cost": batch.unit_cost,
                "lifecycle_stage": batch.lifecycle_stage.value,
                "days_until_expiry": days_until_expiry,
                "is_active": batch.is_active,
                "created_at": batch.created_at
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/items/{item_id}/update-batch/{batch_id}")
def update_batch(
    item_id: int,
    batch_id: int,
    batch_data: BatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")
    
    try:
        batch = (db.query(InventoryBatch)
            .filter(
                InventoryBatch.id == batch_id,
                InventoryBatch.inventory_item_id == item_id,
                InventoryBatch.tenant_id == current_user.tenant_id,
                InventoryBatch.is_active == True
            ).first())
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        item = (db.query(Inventory)
            .filter(
                Inventory.id == item_id,
                Inventory.tenant_id == current_user.tenant_id,
                Inventory.is_active == True
            ).first())
        
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # ✅ Resolve costs with Decimal
        if batch_data.unit_cost:
            resolved_unit_cost  = Decimal(str(batch_data.unit_cost))
            resolved_total_cost = Decimal(str(batch_data.total_cost)) if batch_data.total_cost \
                                  else resolved_unit_cost * Decimal(str(batch_data.quantity_received or batch.quantity_received))

        elif batch_data.total_cost and batch_data.quantity_received:
            resolved_total_cost = Decimal(str(batch_data.total_cost))
            resolved_unit_cost  = resolved_total_cost / Decimal(str(batch_data.quantity_received))

        else:
            resolved_unit_cost  = Decimal(str(batch.unit_cost))   if batch.unit_cost  else Decimal("0")
            resolved_total_cost = Decimal(str(batch.total_cost))  if batch.total_cost else Decimal("0")

        # Recalculate lifecycle
        expiry_date       = batch_data.expiry_date or batch.expiry_date
        days_until_expiry = calculate_days_until_expiry(expiry_date)
        lifecycle         = determine_lifecycle_stage(
            days_until_expiry,
            item.fresh_threshold_days or 3,
            item.near_expiry_threshold_days or 1
        )

        # Update batch fields
        batch.expiry_date        = batch_data.expiry_date        or batch.expiry_date
        batch.quantity_received  = batch_data.quantity_received  or batch.quantity_received
        batch.quantity_remaining = batch_data.quantity_received  or batch.quantity_remaining
        batch.unit               = batch_data.unit               or batch.unit
        batch.packets            = batch_data.packets            or batch.packets
        batch.pieces             = batch_data.pieces             or batch.pieces
        batch.total_pieces       = batch_data.total_pieces       or batch.total_pieces
        batch.price_per_packet   = batch_data.price_per_packet   or batch.price_per_packet
        batch.price_per_piece    = batch_data.price_per_piece    or batch.price_per_piece
        batch.unit_cost          = resolved_unit_cost
        batch.total_cost         = resolved_total_cost
        batch.lifecycle_stage    = lifecycle
        batch.date_added         = batch_data.date_added         or batch.date_added

        # Update linked PURCHASE transaction
        transaction = (db.query(InventoryTransaction)
            .filter(
                InventoryTransaction.batch_id == batch_id,
                InventoryTransaction.transaction_type == TransactionType.PURCHASE
            ).first())
        
        if transaction:
            transaction.quantity    = batch_data.quantity_received or transaction.quantity
            transaction.unit_cost   = resolved_unit_cost
            transaction.total_value = resolved_total_cost
            transaction.unit        = batch_data.unit or transaction.unit

        sync_inventory_totals(item_id, db)
        sync_dish_ingredient_costs(item_id, db, current_user.tenant_id)  # ✅ dish costs update
        db.commit()

        return {
            "success":          True,
            "message":          "Batch updated successfully",
            "batch_id":         batch.id,
            "unit_cost":        float(resolved_unit_cost),
            "total_cost":       float(resolved_total_cost),
            "lifecycle_stage":  lifecycle.value,
            "days_until_expiry": days_until_expiry
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/items/{item_id}/delete-batch-by-id/{batch_id}")
def delete_batch(
    item_id: int,
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required"
        )

    try:
        # 1. Validate item
        item = db.query(Inventory).filter(
            Inventory.id == item_id,
            Inventory.tenant_id == current_user.tenant_id,
            Inventory.is_active == True
        ).first()

        if not item:
            raise HTTPException(status_code=404, detail="Item not found")

        # 2. Validate batch
        batch = db.query(InventoryBatch).filter(
            InventoryBatch.id == batch_id,
            InventoryBatch.inventory_item_id == item_id,
            InventoryBatch.tenant_id == current_user.tenant_id,
            InventoryBatch.is_active == True
        ).first()

        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")

        # 3. Soft delete batch
        batch.is_active = False
        db.flush()  # flush so sync_inventory_totals sees updated is_active

        # 4. Delete linked PURCHASE transaction
        transaction = db.query(InventoryTransaction).filter(
            InventoryTransaction.batch_id == batch_id,
            InventoryTransaction.transaction_type == TransactionType.PURCHASE
        ).first()

        if transaction:
            db.delete(transaction)

        db.flush()  # flush transaction delete too

        # 5. Resync inventory totals
        sync_inventory_totals(item_id, db)
        sync_dish_ingredient_costs(batch.inventory_item_id, db, current_user.tenant_id)
        db.commit()

        return {
            "success": True,
            "message": "Batch deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add-item-categories-via-excel", status_code=status.HTTP_201_CREATED)
def add_item_categories_via_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Upload .xlsx or .xls only",
        )

    try:
        file.file.seek(0)
        contents = file.file.read()

        if len(contents) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        df = pd.read_excel(BytesIO(contents), engine="openpyxl", header=0, skiprows=[1])

    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Excel file contains no data",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error reading Excel: {str(e)}",
        )

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Excel file is empty",
        )

    required_columns = {"name", "category_type"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns: {', '.join(missing_columns)}",
        )

    validated_rows = []
    errors = []
    skipped_rows = []  # ← separate bucket for duplicates

    for index, row in df.iterrows():
        row_number = index + 2
        name = None
        try:
            name = str(row.get("name", "")).strip()
            if not name or name.lower() == "nan":
                raise ValueError("Category name is required")

            raw_category_type = str(row.get("category_type", "")).strip()
            if not raw_category_type or raw_category_type.lower() == "nan":
                raise ValueError("category_type is required")

            try:
                category_type_enum = ItemPerishableNonPerishable(raw_category_type)
            except ValueError:
                valid_values = [e.value for e in ItemPerishableNonPerishable]
                raise ValueError(
                    f"Invalid category_type '{raw_category_type}'. "
                    f"Allowed values: {valid_values}"
                )

            existing = db.query(ItemCategory).filter(
                func.lower(ItemCategory.name) == name.lower(),
                ItemCategory.tenant_id == current_user.tenant_id,
            ).first()

            if existing:
                # ← skip duplicate, don't treat as a hard error
                skipped_rows.append({
                    "row": row_number,
                    "category_name": name,
                    "reason": f"Category '{name}' already exists, skipped",
                })
                continue

            validated_rows.append({
                "name": name,
                "category_type": category_type_enum.value,
            })

        except (ValueError, TypeError) as e:
            errors.append({
                "row": row_number,
                "category_name": name if name and name.lower() != "nan" else None,
                "error": str(e),
            })

    # Only block saving if there are real validation errors (not duplicates)
    if errors and not validated_rows:
        return {
            "success": False,
            "message": "Excel validation failed. No data saved.",
            "summary": {
                "total_rows": len(df),
                "failed_count": len(errors),
                "skipped_count": len(skipped_rows),
            },
            "failed_rows": errors,
            "skipped_rows": skipped_rows,
        }

    try:
        for row_data in validated_rows:
            category = ItemCategory(
                tenant_id=current_user.tenant_id,
                name=row_data["name"],
                category_type=row_data["category_type"],
                user_id=current_user.id,
            )
            db.add(category)

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while saving categories",
        )

    return {
        "success": True,
        "message": "Categories processed successfully",
        "summary": {
            "total_rows": len(df),
            "saved_count": len(validated_rows),
            "skipped_count": len(skipped_rows),   # duplicates
            "failed_count": len(errors),           # real bad rows
        },
        **({"skipped_rows": skipped_rows} if skipped_rows else {}),
        **({"failed_rows": errors} if errors else {}),
    }

TEMPLATE_COLUMNS = [
    # (field,              example,        required)
    ("item_name",          "Tomatoes",     True),
    ("expiry_date",        "2025-12-31",   True),
    ("quantity_received",  100,            True),
    ("unit",               "kg",           True),
    ("unit_cost",          5.50,           False),
    ("total_cost",         550.00,         False),
    ("packets",            "",             False),
    ("pieces",             "",             False),
    ("total_pieces",       "",             False),
    ("price_per_packet",   "",             False),
    ("price_per_piece",    "",             False),
    ("date_added",         "2025-01-15",   False),
]

REQUIRED_COLS = {col for col, _, required in TEMPLATE_COLUMNS if required}

def _to_plain_date(val) -> date | None:
    """Always returns a plain date object or None. Handles datetime, date, and str."""
    if val is None:
        return None
    if isinstance(val, datetime):       # ← must check datetime BEFORE date
        return val.date()               #   because datetime is subclass of date
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).strip())
    except ValueError:
        return None

@router.post("/items/batches/bulk-via-excel")
async def create_batches_bulk(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tenant access required")

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx / .xls files are accepted")

    raw = await file.read()
    try:
        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not parse the uploaded file")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="File has no data rows (row 2 onward)")

    # Normalise headers — strip *, whitespace, lowercase
    headers = [str(h).rstrip("*").strip().lower() if h else "" for h in rows[0]]
    col = {name: idx for idx, name in enumerate(headers)}

    # ══════════════════════════════════════════════════════════════════
    # VALIDATION — required columns must exist in the sheet header
    # ══════════════════════════════════════════════════════════════════
    missing_required_cols = REQUIRED_COLS - set(col.keys())
    if missing_required_cols:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Missing required column(s) in uploaded file: "
                f"{', '.join(sorted(missing_required_cols))}. "
                f"Expected columns: {', '.join(c for c, _, _ in TEMPLATE_COLUMNS)}"
            ),
        )

    # Row-level required fields — expiry_date is excluded here on purpose:
    # the endpoint already computes it from the next batch's date when blank.
    ROW_REQUIRED_FIELDS = REQUIRED_COLS - {"expiry_date"}

    # ── Helper: safely extract a cell value ───────────────────────────────
    def _get(row, name):
        idx = col.get(name)
        if idx is None or idx >= len(row):
            return None
        val = row[idx]
        if isinstance(val, (list, tuple)):
            val = val[0] if val else None
        return val

    # ── Helper: clean raw value before numeric conversion ─────────────────
    def _clean(v):
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if isinstance(v, str):
            v = v.replace(",", "").strip()
            if v == "":
                return None
        return v

    def _opt_int(row, name):
        v = _clean(_get(row, name))
        if v in (None, ""):
            return None
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None

    def _opt_float(row, name):
        v = _clean(_get(row, name))
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _opt_decimal(v):
        v = _clean(v)
        if v in (None, ""):
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    results:  List[dict] = []
    warnings: List[dict] = []

    for row_num, row in enumerate(rows[1:], start=2):
        row_result = {"row": row_num, "success": False, "error": None, "batch_id": None}

        # Skip fully empty rows silently
        if all(cell in (None, "") for cell in row):
            continue

        # Reset item_name_raw so the except block can always reference it safely
        item_name_raw = None

        # ══════════════════════════════════════════════════════════════
        # VALIDATION — required field values must be present for this row
        # ══════════════════════════════════════════════════════════════
        missing_fields = [
            field for field in ROW_REQUIRED_FIELDS
            if _get(row, field) in (None, "")
        ]
        if missing_fields:
            row_result["error"] = f"Missing required value(s): {', '.join(sorted(missing_fields))}"
            item_name_raw = _get(row, "item_name")
            warnings.append({
                "row":       row_num,
                "item_name": str(item_name_raw).strip() if item_name_raw not in (None, "") else f"Row {row_num}",
                "message": (
                    f"Row {row_num} — skipped. Missing required value(s): "
                    f"{', '.join(sorted(missing_fields))}."
                ),
            })
            results.append(row_result)
            continue

        # ══════════════════════════════════════════════════════════════
        # VALIDATION — quantity_received must be a valid positive number
        # ══════════════════════════════════════════════════════════════
        qty_check = _opt_decimal(_get(row, "quantity_received"))
        if qty_check is None or qty_check <= 0:
            row_result["error"] = "quantity_received must be a valid number greater than 0"
            item_name_raw = _get(row, "item_name")
            warnings.append({
                "row":       row_num,
                "item_name": str(item_name_raw).strip() if item_name_raw not in (None, "") else f"Row {row_num}",
                "message": f"Row {row_num} — invalid quantity_received value.",
            })
            results.append(row_result)
            continue

        # ══════════════════════════════════════════════════════════════
        # VALIDATION — unit must map to a known UnitType
        # ══════════════════════════════════════════════════════════════
        raw_unit_check = _get(row, "unit")
        normalized_unit_check = UNIT_MAPPING.get(str(raw_unit_check).strip().lower().replace(" ", ""))
        if not normalized_unit_check:
            row_result["error"] = f"Unrecognized unit: '{raw_unit_check}'"
            item_name_raw = _get(row, "item_name")
            warnings.append({
                "row":       row_num,
                "item_name": str(item_name_raw).strip() if item_name_raw not in (None, "") else f"Row {row_num}",
                "message": f"Row {row_num} — unrecognized unit '{raw_unit_check}'.",
            })
            results.append(row_result)
            continue

        try:
            savepoint = db.begin_nested()

            # ── item_name → resolve to inventory item ──────────────────────
            item_name_raw = _get(row, "item_name")
            item_name = str(item_name_raw).strip() if item_name_raw not in (None, "") else None
            item_id = None
            item    = None

            if item_name:
                if "example" in item_name.lower() or "delete" in item_name.lower():
                    row_result["error"] = "Skipped example/placeholder row"
                    results.append(row_result)
                    continue

                matched_items = (
                    db.query(Inventory)
                    .filter(
                        Inventory.name.ilike(item_name),
                        Inventory.tenant_id == current_user.tenant_id,
                        Inventory.is_active == True,
                    )
                    .all()
                )

                if not matched_items:
                    clean_name = re.sub(r'[@+\[\]()#].*', '', item_name).strip()
                    if clean_name:
                        matched_items = (
                            db.query(Inventory)
                            .filter(
                                Inventory.name.ilike(f"%{clean_name}%"),
                                Inventory.tenant_id == current_user.tenant_id,
                                Inventory.is_active == True,
                            )
                            .all()
                        )

                if matched_items:
                    item    = matched_items[0]
                    item_id = item.id

            # ══════════════════════════════════════════════════════════════
            # AUTO-CREATE INVENTORY ITEM if item_name provided but not found
            # ══════════════════════════════════════════════════════════════
            if item_name and item_id is None:
                try:
                    # Resolve unit for the new item (reuse the unit column)
                    raw_unit_for_item = _get(row, "unit")
                    new_item_unit = None
                    if raw_unit_for_item:
                        normalized = UNIT_MAPPING.get(
                            str(raw_unit_for_item).strip().lower().replace(" ", "")
                        )
                        if normalized:
                            try:
                                new_item_unit = UnitType(normalized)
                            except ValueError:
                                new_item_unit = None

                    new_item = Inventory(
                        name      = item_name,
                        tenant_id = current_user.tenant_id,
                        user_id   = current_user.id,
                        unit      = new_item_unit,
                        is_active = True,
                        # Safe defaults — user can edit later in the UI
                        fresh_threshold_days       = 3,
                        near_expiry_threshold_days = 1,
                    )
                    db.add(new_item)
                    db.flush()  # get new_item.id without committing

                    item    = new_item
                    item_id = new_item.id

                    warnings.append({
                        "row":       row_num,
                        "item_name": item_name,
                        "message": (
                            f"Row {row_num} — '{item_name}' was not found in inventory "
                            "and has been AUTO-CREATED. Please review and complete its "
                            "details (category, thresholds, etc.) in the Inventory screen."
                        ),
                    })

                    logger.info(
                        f"[Bulk] Auto-created inventory item: '{item_name}' "
                        f"(id={item_id}, tenant={current_user.tenant_id})"
                    )

                except Exception as create_exc:
                    warnings.append({
                        "row":       row_num,
                        "item_name": item_name,
                        "message": (
                            f"Row {row_num} — '{item_name}' was not found and could not "
                            f"be auto-created: {create_exc}"
                        ),
                    })
                    row_result["error"] = f"Auto-create failed for '{item_name}': {create_exc}"
                    results.append(row_result)
                    savepoint.rollback()
                    continue

            # ── quantity_received ──────────────────────────────────────────
            raw_qty           = _get(row, "quantity_received")
            quantity_received = _opt_decimal(raw_qty) or Decimal("0")

            # ── unit ───────────────────────────────────────────────────────
            raw_unit = _get(row, "unit")
            unit     = None
            if raw_unit:
                normalized = UNIT_MAPPING.get(str(raw_unit).strip().lower().replace(" ", ""))
                if normalized:
                    try:
                        unit = UnitType(normalized)
                    except ValueError:
                        unit = None

            resolved_unit = unit or (item.unit if item else None)

            # ── date_added ─────────────────────────────────────────────────
            raw_date_added = _get(row, "date_added")
            date_added     = datetime.now(timezone.utc)
            if raw_date_added:
                if isinstance(raw_date_added, datetime):
                    date_added = raw_date_added.replace(tzinfo=timezone.utc) \
                        if raw_date_added.tzinfo is None else raw_date_added
                elif isinstance(raw_date_added, date):
                    date_added = datetime.combine(
                        raw_date_added, datetime.min.time()
                    ).replace(tzinfo=timezone.utc)
                else:
                    try:
                        parsed = datetime.fromisoformat(str(raw_date_added).strip())
                        date_added = parsed.replace(tzinfo=timezone.utc) \
                            if parsed.tzinfo is None else parsed
                    except ValueError:
                        pass

            # ✅ Always a plain date — safe for datetime.combine() and timedelta
            new_batch_date = date_added.date()

            # ══════════════════════════════════════════════════════════════
            # STEP 1 — Find next batch after this date for this item
            # ══════════════════════════════════════════════════════════════
            next_batch = None
            if item_id:
                next_batch = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == current_user.tenant_id,
                        InventoryBatch.inventory_item_id == item_id,
                        InventoryBatch.date_added > datetime.combine(
                            new_batch_date, datetime.max.time()
                        ).replace(tzinfo=timezone.utc),
                    )
                    .order_by(InventoryBatch.date_added.asc())
                    .first()
                )

            # ══════════════════════════════════════════════════════════════
            # STEP 2 — Resolve expiry_date
            # ══════════════════════════════════════════════════════════════
            raw_expiry   = _get(row, "expiry_date")
            expiry_date  = _to_plain_date(raw_expiry)

            # VALIDATION — if expiry_date cell had a value but couldn't parse, flag it
            if raw_expiry not in (None, "") and expiry_date is None:
                row_result["error"] = f"Invalid expiry_date value: '{raw_expiry}'"
                item_name_raw = _get(row, "item_name")
                warnings.append({
                    "row":       row_num,
                    "item_name": str(item_name_raw).strip() if item_name_raw not in (None, "") else f"Row {row_num}",
                    "message": f"Row {row_num} — could not parse expiry_date '{raw_expiry}'.",
                })
                results.append(row_result)
                savepoint.rollback()
                continue

            if expiry_date:
                new_batch_expiry = expiry_date
            elif next_batch:
                next_batch_date  = _to_plain_date(next_batch.date_added)
                new_batch_expiry = next_batch_date - timedelta(days=1)
            else:
                new_batch_expiry = None

            # ══════════════════════════════════════════════════════════════
            # STEP 3 — Close previous open-ended batches (DATE BOUNDARY ONLY)
            # ══════════════════════════════════════════════════════════════
            closed_batch_ids = []
            if item_id:
                previous_open_batches = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == current_user.tenant_id,
                        InventoryBatch.inventory_item_id == item_id,
                        InventoryBatch.expiry_date       == None,
                        InventoryBatch.date_added < datetime.combine(
                            new_batch_date, datetime.min.time()
                        ).replace(tzinfo=timezone.utc),
                    )
                    .all()
                )

                for old_batch in previous_open_batches:
                    old_batch.expiry_date = new_batch_date - timedelta(days=1)

                    if item:
                        old_days = calculate_days_until_expiry(old_batch.expiry_date)
                        old_batch.lifecycle_stage = determine_lifecycle_stage(
                            old_days,
                            item.fresh_threshold_days       or 3,
                            item.near_expiry_threshold_days or 1,
                        )

                    closed_batch_ids.append(old_batch.id)

                    logger.info(
                        f"[Bulk] Batch {old_batch.batch_number} closed: "
                        f"expiry={old_batch.expiry_date} | "
                        f"lifecycle={old_batch.lifecycle_stage} | "
                        f"qty_remaining={old_batch.quantity_remaining} (preserved)"
                    )

            # ══════════════════════════════════════════════════════════════
            # STEP 4 — Resolve lifecycle for new batch
            # ══════════════════════════════════════════════════════════════
            lifecycle         = None
            days_until_expiry = None
            if new_batch_expiry and item:
                days_until_expiry = calculate_days_until_expiry(new_batch_expiry)
                lifecycle         = determine_lifecycle_stage(
                    days_until_expiry,
                    item.fresh_threshold_days       or 3,
                    item.near_expiry_threshold_days or 1,
                )

            # ── Cost resolution ────────────────────────────────────────────
            unit_cost  = _opt_decimal(_get(row, "unit_cost"))
            total_cost = _opt_decimal(_get(row, "total_cost"))

            if unit_cost and total_cost:
                resolved_unit_cost  = unit_cost
                resolved_total_cost = total_cost
            elif unit_cost:
                resolved_unit_cost  = unit_cost
                resolved_total_cost = quantity_received * unit_cost if quantity_received else unit_cost
            elif total_cost and quantity_received:
                resolved_unit_cost  = total_cost / quantity_received
                resolved_total_cost = total_cost
            else:
                resolved_unit_cost  = unit_cost
                resolved_total_cost = total_cost

            # ── Optional packet/piece fields ───────────────────────────────
            packets = _opt_int(row, "packets")
            pieces  = _opt_int(row, "pieces")

            # ── total_pieces: from Excel → else calculate packets × pieces ─
            total_pieces = _opt_int(row, "total_pieces")
            if total_pieces is None and quantity_received and pieces:
                total_pieces = int(quantity_received * pieces)

            # ── price_per_packet: from Excel → else total_cost / packets ───
            price_per_packet = _opt_float(row, "price_per_packet")
            if price_per_packet is None and resolved_total_cost and packets:
                price_per_packet = float(resolved_total_cost / packets)

            # ── price_per_piece: from Excel → else total_cost / total_pieces
            price_per_piece = _opt_float(row, "price_per_piece")
            if price_per_piece is None and resolved_total_cost and total_pieces:
                price_per_piece = float(resolved_total_cost / total_pieces)

            # ══════════════════════════════════════════════════════════════
            # STEP 5 — Create the new batch
            # ══════════════════════════════════════════════════════════════
            batch_number = generate_batch_number_sequential(
                item_id=item_id, db=db, prefix="BATCH"
            )

            batch = InventoryBatch(
                user_id            = current_user.id,
                tenant_id          = current_user.tenant_id,
                inventory_item_id  = item_id,
                batch_number       = batch_number,
                expiry_date        = new_batch_expiry,
                quantity_received  = float(quantity_received),
                quantity_remaining = float(quantity_received),
                unit               = resolved_unit,
                packets            = packets,
                pieces             = pieces,
                total_pieces       = total_pieces,
                price_per_packet   = price_per_packet,
                price_per_piece    = price_per_piece,
                unit_cost          = resolved_unit_cost,
                total_cost         = resolved_total_cost,
                lifecycle_stage    = lifecycle,
                date_added         = date_added,
                is_active          = True,
            )
            db.add(batch)
            db.flush()

            # ══════════════════════════════════════════════════════════════
            # STEP 6 — Purchase transaction
            # ══════════════════════════════════════════════════════════════
            if item_id and quantity_received:
                db.add(InventoryTransaction(
                    tenant_id         = current_user.tenant_id,
                    inventory_item_id = item_id,
                    batch_id          = batch.id,
                    transaction_type  = TransactionType.PURCHASE,
                    quantity          = float(quantity_received),
                    unit_cost         = float(resolved_unit_cost) if resolved_unit_cost else None,
                    unit              = resolved_unit,
                    total_value       = float(resolved_total_cost) if resolved_total_cost else None,
                    reference_id      = f"Batch {batch.batch_number} received",
                    transaction_date  = date_added,
                ))
                db.flush()
                sync_inventory_totals(item_id, db)
                sync_dish_ingredient_costs(item_id, db, current_user.tenant_id)

            savepoint.commit()

            row_result.update(
                success            = True,
                batch_id           = batch.id,
                item_name          = item_name,
                item_id            = item_id,
                batch_number       = batch_number,
                date_added         = date_added.isoformat(),
                expiry_date        = new_batch_expiry.isoformat() if new_batch_expiry else None,
                lifecycle_stage    = lifecycle.value if lifecycle else None,
                days_until_expiry  = days_until_expiry,
                unit_cost          = float(resolved_unit_cost)  if resolved_unit_cost  else None,
                total_cost         = float(resolved_total_cost) if resolved_total_cost else None,
                total_pieces       = total_pieces,
                price_per_packet   = price_per_packet,
                price_per_piece    = price_per_piece,
                batches_closed     = len(closed_batch_ids),
                auto_created_item  = (item_id == new_item.id) if 'new_item' in dir() else False,
            )

        except Exception as exc:
            savepoint.rollback()
            row_result["error"] = str(exc)
            logger.error(f"[Bulk] Row {row_num} failed: {exc}")

            failed_name = str(item_name_raw).strip() if item_name_raw not in (None, "") else f"Row {row_num}"
            warnings.append({
                "row":       row_num,
                "item_name": failed_name,
                "message": (
                    f"Row {row_num} — '{failed_name}' failed to import. "
                    "Please check the spelling or ensure the item exists in Inventory."
                ),
            })

        results.append(row_result)

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Commit failed: {exc}")

    succeeded     = [r for r in results if r["success"]]
    failed        = [r for r in results if not r["success"]]
    auto_created  = [r for r in results if r.get("auto_created_item")]

    return {
        "total_rows":          len(results),
        "succeeded":           len(succeeded),
        "failed":              len(failed),
        "auto_created_items":  len(auto_created),
        "warnings":            warnings,
        "results":             results,
    }

@router.get("/filter/get-all-batches")
def get_all_batches(
    date_from: date | None = Query(default=None, description="Filter batches added from this date (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="Filter batches added up to this date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )

    try:
        query = (
            db.query(InventoryBatch)
            .filter(
                InventoryBatch.tenant_id == current_user.tenant_id,
                # InventoryBatch.is_active == True,
                # InventoryBatch.quantity_remaining > 0,
            )
        )

        if date_from:
            query = query.filter(InventoryBatch.date_added >= date_from)
        if date_to:
            query = query.filter(InventoryBatch.date_added <= date_to + timedelta(days=1))

        batches = query.order_by(InventoryBatch.expiry_date.asc()).all()

        return {
            "success": True,
            "count": len(batches),
            "data": batches
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch batches: {str(e)}"
        )

@router.get("/transactions/consumption")
def get_consumption_transactions(
    item_id: int | None = Query(default=None, description="Filter by inventory item ID"),
    date_from: date | None = Query(default=None, description="Filter from this date (YYYY-MM-DD)"),
    date_to: date | None = Query(default=None, description="Filter up to this date (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access required",
        )

    try:
        query = (
            db.query(InventoryTransaction)
            .join(Inventory, InventoryTransaction.inventory_item_id == Inventory.id)
            .join(InventoryBatch, InventoryTransaction.batch_id == InventoryBatch.id, isouter=True)
            .filter(
                InventoryTransaction.tenant_id == current_user.tenant_id,
                InventoryTransaction.transaction_type == TransactionType.CONSUMPTION
            )
        )

        if item_id:
            # Validate the item belongs to tenant
            item = (
                db.query(Inventory)
                .filter(
                    Inventory.id == item_id,
                    Inventory.tenant_id == current_user.tenant_id
                )
                .first()
            )
            if not item:
                raise HTTPException(status_code=404, detail="Inventory item not found")

            query = query.filter(InventoryTransaction.inventory_item_id == item_id)

        if date_from:
            query = query.filter(InventoryTransaction.transaction_date >= date_from)
        if date_to:
            query = query.filter(InventoryTransaction.transaction_date <= date_to)

        transactions = query.order_by(InventoryTransaction.transaction_date.desc()).all()

        data = [
            {
                "id": str(txn.id),
                "transaction_date": txn.transaction_date,
                "transaction_type": txn.transaction_type.value,
                "quantity": float(txn.quantity) if txn.quantity else None,
                "unit": txn.unit,
                "unit_cost": float(txn.unit_cost) if txn.unit_cost else None,
                "total_value": float(txn.total_value) if txn.total_value else None,
                "reference_id": txn.reference_id,
                # Inventory item details
                "inventory_item_id": txn.inventory_item_id,
                "inventory_item_name": txn.inventory.name if txn.inventory else None,
                # Batch details
                "batch_id": txn.batch_id,
                "batch_number": txn.batch.batch_number if txn.batch else None,
                "created_at": txn.created_at,
            }
            for txn in transactions
        ]

        return {
            "success": True,
            "transaction_type": TransactionType.CONSUMPTION.value,
            "count": len(data),
            "data": data
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch consumption transactions: {str(e)}"
        )