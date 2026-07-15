"""
app/api/v1/orders.py
Order Management API Routes
"""
from collections import OrderedDict, defaultdict
from decimal import Decimal
from io import BytesIO
from math import ceil

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, logger, status
import pandas as pd
from sqlalchemy import and_, func, not_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from datetime import date, datetime, timedelta, timezone

from app.db.session import get_db
from app.models.dish import Dish, DishIngredient, DishSale, SemiFinishedIngredient, SemiFinishedProduct , Combo , ComboItem
from app.models.inventory import Inventory, InventoryBatch, InventoryTransaction, TransactionType
from app.models.users import User
from app.models.wastage_model import Wastage, WastageType
from app.schemas.order import (
 OrderSaleRequest

)
from app.utils.auth_helper import get_current_user
from app.utils.common_unit_converter import _normalize_unit, convert_quantity_unit
from app.utils.inventory_batch_helper import _handle_post_upload_expiry, sync_dish_ingredient_costs, sync_inventory_totals
import logging
from enum import Enum as PyEnum
import re

from app.utils.unit_converter import are_units_compatible, convert_to_base_unit, normalize_unit
logger = logging.getLogger(__name__)

router = APIRouter()

EXPIRY_URGENCY_DAYS = 7

def _sort_batches_fifo_fefo_hybrid(batches: list, sale_date_only: date) -> list:
    """
    Hybrid FIFO/FEFO batch ordering.

    - "Urgent" batches (expiry within EXPIRY_URGENCY_DAYS of sale_date) are
      deducted first, soonest-expiry first, to avoid wastage.
    - All other batches drain in pure FIFO order (oldest date_added first),
      regardless of how their expiry dates compare to each other.

    This is the fix for batches whose expiry is far in the future: they no
    longer get reordered ahead of an older batch just because one happens
    to expire a bit sooner than another — both stay in FIFO order until
    either one is actually close to expiring.
    """
    def is_urgent(b) -> bool:
        if b.expiry_date is None:
            return False
        return (b.expiry_date - sale_date_only).days <= EXPIRY_URGENCY_DAYS

    urgent = sorted(
        (b for b in batches if is_urgent(b)),
        key=lambda b: (b.expiry_date, b.created_at),
    )
    normal = sorted(
        (b for b in batches if not is_urgent(b)),
        key=lambda b: (b.date_added, b.created_at),
    )
    return urgent + normal

def _parse_date_string(date_val) -> pd.Timestamp:
    """
    Robustly parse a date value that may be:
    - A real datetime object (from Excel numeric date cell)
    - A string like "12-04-2026", "12/04/2026", "2026-04-12", "2026/04/12"
    Always treats DD-MM-YYYY for ambiguous formats (Indian locale).
    """
    if pd.isna(date_val) or date_val is None:
        return pd.NaT

    # Already a proper datetime — just return it
    if hasattr(date_val, 'strftime'):
        return pd.Timestamp(date_val)

    s = str(date_val).strip()
    if not s or s.lower() in ("nan", "nat", "none", ""):
        return pd.NaT

    # If Excel serialized it as ISO: "2026-04-12" or "2026/04/12"
    # These are unambiguous — parse directly
    iso_match = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if iso_match:
        year, month, day = iso_match.groups()
        return pd.Timestamp(f"{year}-{month.zfill(2)}-{day.zfill(2)}")

    # Ambiguous formats: "12-04-2026" or "12/04/2026"
    # ALWAYS treat as DD-MM-YYYY (Indian format)
    ambiguous_match = re.match(r'^(\d{1,2})[-/](\d{1,2})[-/](\d{4})', s)
    if ambiguous_match:
        day, month, year = ambiguous_match.groups()
        return pd.Timestamp(f"{year}-{month.zfill(2)}-{day.zfill(2)}")

    # Fallback — let pandas try with dayfirst
    return pd.to_datetime(s, dayfirst=True, errors="coerce")

def _get_valid_batches(
    db: Session,
    tenant_id: int,
    inventory_item_id: int,
    sale_date_only: date,
) -> list:
    batches = (
        db.query(InventoryBatch)
        .filter(
            InventoryBatch.tenant_id         == tenant_id,
            InventoryBatch.inventory_item_id == inventory_item_id,
            InventoryBatch.is_active         == True,   # exclude deleted/deactivated batches
            InventoryBatch.quantity_remaining > 0,
            InventoryBatch.date_added <= datetime.combine(
                sale_date_only, datetime.max.time()
            ).replace(tzinfo=timezone.utc),
            or_(
                InventoryBatch.expiry_date == None,
                InventoryBatch.expiry_date >= sale_date_only,
            ),
        )
        .all()
    )
    return _sort_batches_fifo_fefo_hybrid(batches, sale_date_only)

def _accumulate(
    qty_needed_map: dict,
    ingredient_id: int,
    sale_date_only: date,
    unit: str,
    name: str,
    qty: Decimal,
) -> None:
    key = (ingredient_id, sale_date_only)
    if key not in qty_needed_map:
        qty_needed_map[key] = {
            "qty":       Decimal(0),
            "unit":      unit,
            "name":      name,
            "sale_date": sale_date_only,
        }
    qty_needed_map[key]["qty"] += qty

def _convert_or_error(
    qty: Decimal,
    from_unit: str,
    to_unit: str,
    first_batch,
    PIECE_UNITS: set,
    PACKET_UNITS: set,
    label: str,
    errors: list,
) -> Decimal | None:
    if from_unit in PIECE_UNITS and to_unit in PACKET_UNITS:
        pieces_per_packet = Decimal(str(first_batch.pieces)) if first_batch.pieces else Decimal("1")
        return qty / pieces_per_packet
    if from_unit == to_unit:
        return qty
    if not are_units_compatible(from_unit, to_unit):
        errors.append(
            f"{label}: incompatible units — cannot convert '{from_unit}' to '{to_unit}'"
        )
        return None
    try:
        return Decimal(str(convert_quantity_unit(value=qty, from_unit=from_unit, to_unit=to_unit)))
    except ValueError as e:
        errors.append(f"{label}: unit conversion failed — {e}")
        return None

def _accumulate_semi(
    db: Session,
    tenant_id: int,
    dish_ing,
    qty_sold,
    sale_date_only: date,
    qty_needed_map: dict,
    PIECE_UNITS: set,
    PACKET_UNITS: set,
    label: str,
) -> list[str]:
    errors = []
    semi = db.query(SemiFinishedProduct).filter(
        SemiFinishedProduct.id        == dish_ing.semi_finished_id,
        SemiFinishedProduct.tenant_id == tenant_id,
        SemiFinishedProduct.is_active == True,
    ).first()

    if not semi:
        errors.append(f"{label}: semi-finished id={dish_ing.semi_finished_id} not found")
        return errors

    dish_sfp_unit   = _normalize_unit(dish_ing.unit)
    semi_yield_unit = _normalize_unit(semi.unit)
    qty_sfp_needed  = Decimal(str(dish_ing.quantity_required)) * qty_sold

    if dish_sfp_unit != semi_yield_unit:
        try:
            qty_sfp_needed = Decimal(str(convert_quantity_unit(
                value=qty_sfp_needed, from_unit=dish_sfp_unit, to_unit=semi_yield_unit,
            )))
        except ValueError:
            errors.append(
                f"{label} → '{semi.name}': cannot convert '{dish_sfp_unit}' to '{semi_yield_unit}'"
            )
            return errors

    flat_ings = _resolve_semi_to_raw_ingredients(db, tenant_id, semi.id, qty_sfp_needed)
    if not flat_ings:
        errors.append(f"{label} → '{semi.name}' has no sub-ingredients configured")
        return errors

    for sub_ing in flat_ings:
        batches = _get_valid_batches(db, tenant_id, sub_ing["ingredient_id"], sale_date_only)
        if not batches:
            errors.append(
                f"{label} → '{semi.name}': no batch for '{sub_ing['ingredient_name']}' on {sale_date_only}"
            )
            continue

        batch_unit   = _normalize_unit(batches[0].unit)
        sub_ing_unit = _normalize_unit(sub_ing["unit"])
        qty_needed   = sub_ing["quantity_required"]

        if sub_ing["fixed_cost_amount"] is not None:
            batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
            qty_needed = (
                Decimal(str(sub_ing["fixed_cost_amount"])) / batch_unit_cost * qty_needed
                if batch_unit_cost > 0 else Decimal("0")
            )
            _accumulate(qty_needed_map, sub_ing["ingredient_id"], sale_date_only,
                        batch_unit, sub_ing["ingredient_name"], qty_needed)
            continue

        qty_needed = _convert_or_error(
            qty_needed, sub_ing_unit, batch_unit, batches[0],
            PIECE_UNITS, PACKET_UNITS,
            label=f"{label} → '{semi.name}' → '{sub_ing['ingredient_name']}'",
            errors=errors,
        )
        if qty_needed is None:
            continue

        _accumulate(qty_needed_map, sub_ing["ingredient_id"], sale_date_only,
                    batch_unit, sub_ing["ingredient_name"], qty_needed)

    return errors


UNIT_CONVERT = {
    "kg": Decimal("1000"),
    "gm": Decimal("1"),
    "mg": Decimal("0.001"),
    "liter": Decimal("1000"),
    "ml": Decimal("1"),
    "pcs": Decimal("1"),
    "packet": Decimal("1"),
    "box": Decimal("1"),
    "carton": Decimal("1"),
    "dozen": Decimal("12"),
    "bundle": Decimal("1"),
    "roll": Decimal("1"),
    "sheet": Decimal("1"),
    "sachet": Decimal("1"),
    "bottle": Decimal("1"),
    "can": Decimal("1"),
    "bag": Decimal("1"),
}


def _is_ciferon_format(df: pd.DataFrame) -> bool:
    cols_lower = [c.lower().strip() for c in df.columns]
    has_bar_total = "bar total" in cols_lower
    has_items_with_datetime = (
        "items" in cols_lower and
        "date" in cols_lower and
        "time" in cols_lower
    )
    return has_bar_total or has_items_with_datetime


def _clean_ciferon_excel(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()

    bar_col = next((c for c in df.columns if c.strip().lower() == "bar total"), None)
    if not bar_col:
        bar_col = next((c for c in df.columns if c.strip().lower() == "items"), None)
    if not bar_col:
        raise ValueError("No item column (Bar Total / Items) found in Ciferon export")

    date_col = next((c for c in df.columns if c.strip().lower() == "date"), None)
    time_col = next((c for c in df.columns if c.strip().lower() == "time"), None)

    df = df.dropna(subset=[bar_col])
    df = df[df[bar_col].astype(str).str.strip() != ""]

    # case-insensitive flag so "1X ..." and "1x ..." both match
    df = df[df[bar_col].astype(str).str.contains(r'\d+\s*[xX]\s*', regex=True)]

    def parse_date_safe(date_val, time_val):
        try:
            ts = _parse_date_string(date_val)          #  use robust helper
            if pd.isna(ts):
                return pd.NaT
            time_str = str(time_val).strip()
            return pd.to_datetime(
                f"{ts.strftime('%Y-%m-%d')} {time_str}",
                errors="coerce"
            )
        except:
            return pd.NaT

    def parse_date_only(date_val):
        return _parse_date_string(date_val)            #  use robust helper

    if date_col and time_col:
        df["sale_datetime"] = df.apply(
            lambda row: parse_date_safe(row[date_col], row[time_col]), axis=1
        )
    elif date_col:
        df["sale_datetime"] = df[date_col].apply(parse_date_only)
    else:
        df["sale_datetime"] = pd.NaT

    df = df.assign(items=df[bar_col].astype(str).str.split(","))
    df = df.explode("items")
    df["items"] = df["items"].str.strip()
    df = df[df["items"].str.len() > 0]

    # case-insensitive [xX] so "1X item" extracts qty correctly
    df["order_qty"] = (
        df["items"].str.extract(r'^(\d+)\s*[xX]\s*', expand=False)
        .fillna("1")
        .astype(int)
    )

    df["unit_qty"] = df["items"].str.extract(r'\((\d+)\)', expand=False)
    pcs = df["items"].str.extract(r'(\d+)\s*[Pp]cs', expand=False)
    df["unit_qty"] = df["unit_qty"].fillna(pcs)

    # case-insensitive strip of leading "1X " from item name
    df["item_name"] = (
        df["items"]
        .str.replace(r'^\d+\s*[xX]\s*', '', regex=True)
        .str.replace(r'@[\d.]+', '', regex=True)
        .str.replace(r'\(.*?\)', '', regex=True)
        .str.replace(r'\d+\s*[Pp]cs', '', regex=True)
        .str.strip()
    )

    df = df[df["item_name"].str.len() > 0]
    return df[["item_name", "order_qty", "unit_qty", "sale_datetime"]]

def _parse_sales_file(contents: bytes, filename: str = "") -> tuple:
    name = filename.lower()

    if name.endswith(".csv"):
        try:
            df = pd.read_csv(BytesIO(contents), dtype=str)
        except Exception:
            raise ValueError("Failed to parse CSV file. Please check the format")
    else:
        try:
            df = pd.read_excel(BytesIO(contents), sheet_name=0, dtype=str)
        except Exception:
            raise ValueError("Failed to parse Excel file. Please check the format")

    is_ciferon = _is_ciferon_format(df)

    if is_ciferon:
        df = _clean_ciferon_excel(df)
    else:
        df.columns = df.columns.str.strip().str.lower()
        missing = {"item_name", "order_qty"} - set(df.columns)
        if missing:
            raise ValueError(
                f"Missing required columns: {sorted(missing)}. "
                f"Expected either a Ciferon export (with 'Bar Total' or 'Items') "
                f"or a cleaned file with 'item_name' and 'order_qty' columns"
            )
        if "sale_date" in df.columns:
            df["sale_datetime"] = df["sale_date"].apply(_parse_date_string)

    return df, is_ciferon

def _get_sale_date_only(sale_date) -> date:
    if isinstance(sale_date, datetime):
        return sale_date.date()
    if isinstance(sale_date, date):
        return sale_date
    return date.today()

def _get_batches_for_sale_date(db, tenant_id, inventory_item_id, sale_date_only):
    """
    Fetch batches valid on the actual sale_date — core of backdated order support.
    Hybrid FIFO/FEFO: near-expiry batches (see EXPIRY_URGENCY_DAYS) are pulled
    first to avoid wastage; everything else drains oldest-received-first,
    regardless of how far apart their expiry dates are.
    """
    batches = (
        db.query(InventoryBatch)
        .filter(
            InventoryBatch.tenant_id == tenant_id,
            InventoryBatch.inventory_item_id == inventory_item_id,
            InventoryBatch.is_active == True,   # exclude deleted/deactivated batches
            InventoryBatch.quantity_remaining > 0,
            InventoryBatch.date_added <= datetime.combine(
                sale_date_only, datetime.max.time()
            ).replace(tzinfo=timezone.utc),
            or_(
                InventoryBatch.expiry_date == None,
                InventoryBatch.expiry_date >= sale_date_only,   # not expired ON that date
            )
        )
        .all()
    )
    return _sort_batches_fifo_fefo_hybrid(batches, sale_date_only)

def _resolve_semi_to_raw_ingredients(
    db: Session,
    tenant_id: int,
    semi_id: int,
    qty_sfp_needed: Decimal,
    visited: set = None,
) -> list[dict]:
    """
    Recursively expand a semi-finished product into a flat list of raw
    ingredient dicts (already scaled to qty_sfp_needed).

    Returned dict keys:
        ingredient_id, ingredient_name, quantity_required (scaled),
        unit, fixed_cost_amount

    FIX: Changed `elif sub.ingredient_id` to `else` block so that
    ZUKINI3's own raw ingredients (Pav, Aaloo, Ginger, Cylinder) are
    always collected — even when ZUKINI3 also contains nested semis
    (like UPMA 2.0). Previously the `elif` caused raw ingredients to
    be skipped whenever a nested semi was found in the same loop.
    """
    if visited is None:
        visited = set()
    if semi_id in visited:
        return []               # cycle guard
    visited = visited | {semi_id}

    semi = db.query(SemiFinishedProduct).filter(
        SemiFinishedProduct.id        == semi_id,
        SemiFinishedProduct.tenant_id == tenant_id,
        SemiFinishedProduct.is_active == True,
    ).first()
    if not semi:
        return []

    scale_factor = (
        qty_sfp_needed / Decimal(str(semi.yield_quantity))
        if semi.yield_quantity else Decimal(1)
    )

    sub_ingredients = db.query(SemiFinishedIngredient).filter(
        SemiFinishedIngredient.semi_finished_id == semi_id,
        SemiFinishedIngredient.tenant_id        == tenant_id,
    ).all()

    result = []
    for sub in sub_ingredients:

        # ── Nested semi-finished → recurse ────────────────────────────
        if getattr(sub, "is_semi_finished", False):
            nested_semi_id = sub.ingredient_id
            if not nested_semi_id:
                continue

            nested_qty = Decimal(str(sub.quantity_required)) * scale_factor

            # Convert units if sub.unit differs from nested semi's yield unit
            nested_semi = db.query(SemiFinishedProduct).filter(
                SemiFinishedProduct.id        == nested_semi_id,
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            ).first()

            if nested_semi:
                sub_unit    = _normalize_unit(sub.unit)
                nested_unit = _normalize_unit(nested_semi.unit)
                try:
                    if sub_unit != nested_unit:
                        nested_qty = Decimal(str(convert_quantity_unit(
                            value     = nested_qty,
                            from_unit = sub_unit,
                            to_unit   = nested_unit,
                        )))
                except Exception:
                    pass

            # Recurse — flatten nested semi into raw ingredients
            result.extend(_resolve_semi_to_raw_ingredients(
                db             = db,
                tenant_id      = tenant_id,
                semi_id        = nested_semi_id,
                qty_sfp_needed = nested_qty,
                visited        = visited,
            ))

        # ── Raw ingredient → add directly ─────────────────────────────
        # FIX: was `elif sub.ingredient_id` before — this caused raw
        # ingredients to be silently skipped in any semi that also had
        # a nested semi-ingredient. Now it's a clean else block so both
        # branches are always evaluated independently per sub-ingredient.
        else:
            if sub.ingredient_id:
                result.append({
                    "ingredient_id":     sub.ingredient_id,
                    "ingredient_name":   sub.ingredient_name,
                    "quantity_required": Decimal(str(sub.quantity_required)) * scale_factor,
                    "unit":              sub.unit,
                    "fixed_cost_amount": sub.fixed_cost_amount,
                })

    return result
     
def _deduct_ingredient_fifo(
    db: Session,
    tenant_id: int,
    dish_ing: DishIngredient,
    total_qty_needed_recipe: Decimal,
    inventory: Inventory,
    sale_date: datetime,
) -> dict:
    """
    Deducts ingredient stock FIFO/FEFO.

    BEHAVIOR CHANGE: this function never blocks a sale for insufficient
    stock. It always deducts min(needed, available) and reports the
    shortfall (if any) via the "shortfall" key on the returned dict.
    "success" is only False when there is genuinely nothing to act on
    (no batch exists at all) or when units are structurally incompatible
    (a config problem, not a stock problem).
    """

    dish_ing_unit  = _normalize_unit(dish_ing.unit)
    sale_date_only = _get_sale_date_only(sale_date)
 
    batches = _get_batches_for_sale_date(
        db, tenant_id, dish_ing.ingredient_id, sale_date_only
    )
 
    if not batches:
        return {
            "success":         False,
            "ingredient_name": dish_ing.ingredient_name,
            "warning":         f"No batch found for '{dish_ing.ingredient_name}' valid on {sale_date_only}",
            "cost":            0.0,
            "batches_used":    [],
            "batch_ids":       [],
        }
    
    if dish_ing.fixed_cost_amount is not None:
        latest_batch    = batches[0]
        batch_unit_cost = Decimal(str(latest_batch.unit_cost or 0))
 
        if batch_unit_cost > 0:
            qty_to_deduct = (
                Decimal(str(dish_ing.fixed_cost_amount)) / batch_unit_cost
            ) * Decimal(str(total_qty_needed_recipe))
        else:
            qty_to_deduct = Decimal("0")

        total_available = sum(Decimal(str(b.quantity_remaining)) for b in batches)
        shortfall_warning = None
        if total_available < qty_to_deduct:
            shortfall_warning = (
                f"Insufficient '{dish_ing.ingredient_name}': needed {float(qty_to_deduct):.4f} "
                f"{_normalize_unit(latest_batch.unit)}, only {float(total_available):.4f} "
                f"{_normalize_unit(latest_batch.unit)} available — deducted available amount only"
            )
            qty_to_deduct = total_available  # clamp — deduct whatever exists

        total_cost     = Decimal("0")
        batches_used   = []
        used_batch_ids = []
        qty_remaining  = qty_to_deduct
 
        for batch in batches:
            if qty_remaining <= 0:
                break
 
            batch_qty          = Decimal(str(batch.quantity_remaining))
            batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
            batch_total_cost   = Decimal(str(batch.total_cost))         if batch.total_cost         else Decimal("0")
            qty_from_batch     = min(batch_qty, qty_remaining)   # never deducts more than needed

            cost = (
                (qty_from_batch / batch_qty_received) * batch_total_cost
                if batch_qty_received > 0
                else Decimal("0")
            )
 
            batch.quantity_remaining = float(batch_qty - qty_from_batch)
            total_cost += cost
 
            if Decimal(str(batch.quantity_remaining)) <= 0:
                batch.is_active = False
 
            db.add(InventoryTransaction(
                tenant_id          = tenant_id,
                inventory_item_id  = dish_ing.ingredient_id,
                batch_id           = batch.id,
                transaction_type   = TransactionType.SALE,
                quantity           = float(qty_from_batch),
                unit_cost          = float(dish_ing.fixed_cost_amount),
                total_value        = float(cost),
                transaction_date   = sale_date,
                reference_id       = f"dish_sale:{dish_ing.dish_id}",
                dish_ingredient_id = dish_ing.id,
            ))
 
            batches_used.append(batch.batch_number)
            used_batch_ids.append(batch.id)
            qty_remaining -= qty_from_batch
 
        sync_inventory_totals(dish_ing.ingredient_id, db)
        sync_dish_ingredient_costs(dish_ing.ingredient_id, db, tenant_id)

        actually_deducted = qty_to_deduct - qty_remaining

        return {
            "success":         True,
            "ingredient_name": dish_ing.ingredient_name,
            "qty_deducted":    float(actually_deducted),
            "unit":            _normalize_unit(latest_batch.unit),
            "cost":            float(total_cost),
            "batches_used":    batches_used,
            "batch_ids":       used_batch_ids,
            "shortfall":       shortfall_warning,
        }
    
 
    batch_unit = _normalize_unit(batches[0].unit)
 
    if not batch_unit:
        return {
            "success":         False,
            "ingredient_name": dish_ing.ingredient_name,
            "warning":         f"No unit defined on batch for '{dish_ing.ingredient_name}'",
            "cost":            0.0,
            "batches_used":    [],
            "batch_ids":       [],
        }
    
    PIECE_UNITS  = {"pcs", "piece", "pieces"}
    PACKET_UNITS = {"packet", "packets", "pkt"}

    # ── Pieces needed, but batch tracked in packets ─────────────────────
    if dish_ing_unit in PIECE_UNITS and batch_unit in PACKET_UNITS:
        total_pieces_needed = total_qty_needed_recipe
 
        qty_remaining  = total_pieces_needed
        total_cost     = Decimal("0")
        batches_used   = []
        used_batch_ids = []
 
        for batch in batches:
            if qty_remaining <= 0:
                break
 
            pieces_per_packet  = Decimal(str(batch.pieces)) if batch.pieces else Decimal("1")
            batch_qty_packets  = Decimal(str(batch.quantity_remaining))
            batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
            batch_total_cost   = Decimal(str(batch.total_cost))        if batch.total_cost        else Decimal("0")
 
            pieces_in_batch    = batch_qty_packets * pieces_per_packet
            pieces_from_batch  = min(pieces_in_batch, qty_remaining)   # never more than needed
            packets_to_deduct  = pieces_from_batch / pieces_per_packet
 
            cost = (
                (packets_to_deduct / batch_qty_received) * batch_total_cost
                if batch_qty_received > 0
                else Decimal("0")
            )
 
            batch.quantity_remaining = float(batch_qty_packets - packets_to_deduct)
            total_cost += cost
 
            if Decimal(str(batch.quantity_remaining)) <= 0:
                batch.is_active = False
 
            db.add(InventoryTransaction(
                tenant_id          = tenant_id,
                inventory_item_id  = dish_ing.ingredient_id,
                batch_id           = batch.id,
                transaction_type   = TransactionType.SALE,
                quantity           = float(packets_to_deduct),
                unit_cost          = float(cost / pieces_from_batch) if pieces_from_batch > 0 else 0,
                total_value        = float(cost),
                transaction_date   = sale_date,
                reference_id       = f"dish_sale:{dish_ing.dish_id}",
                dish_ingredient_id = dish_ing.id,
            ))
 
            batches_used.append(batch.batch_number)
            used_batch_ids.append(batch.id)
            qty_remaining -= pieces_from_batch
 
        sync_inventory_totals(dish_ing.ingredient_id, db)
        sync_dish_ingredient_costs(dish_ing.ingredient_id, db, tenant_id)

        actually_deducted = total_pieces_needed - qty_remaining
        shortfall_warning = None
        if qty_remaining > 0:
            shortfall_warning = (
                f"Insufficient '{dish_ing.ingredient_name}': needed {float(total_pieces_needed)} pcs, "
                f"only {float(actually_deducted)} pcs available in batches — deducted available amount only"
            )

        return {
            "success":         True,
            "ingredient_name": dish_ing.ingredient_name,
            "qty_deducted":    float(actually_deducted),
            "unit":            "pcs",
            "cost":            float(total_cost),
            "batches_used":    batches_used,
            "batch_ids":       used_batch_ids,
            "shortfall":       shortfall_warning,
        }

    # ── Normal case: convert dish unit → batch unit if needed ──────────
    if dish_ing_unit and dish_ing_unit != batch_unit:
        if not are_units_compatible(dish_ing_unit, batch_unit):
            return {
                "success":         False,
                "ingredient_name": dish_ing.ingredient_name,
                "warning":         f"Incompatible units for '{dish_ing.ingredient_name}': cannot convert '{dish_ing_unit}' to '{batch_unit}'",
                "cost":            0.0,
                "batches_used":    [],
                "batch_ids":       [],
            }
        qty_in_batch_unit = Decimal(str(
            convert_to_base_unit(float(total_qty_needed_recipe), dish_ing_unit, batch_unit)
        ))
    else:
        qty_in_batch_unit = total_qty_needed_recipe

    total_available = sum(Decimal(str(b.quantity_remaining)) for b in batches)

    # ── CHANGED: never block the sale on insufficient stock.
    # Deduct min(needed, available) and report the shortfall instead
    # of failing the ingredient/sale.
    shortfall_warning = None
    if total_available < qty_in_batch_unit:
        shortfall_warning = (
            f"Insufficient '{dish_ing.ingredient_name}': needed {float(qty_in_batch_unit):.4f} {batch_unit}, "
            f"only {float(total_available):.4f} {batch_unit} available — deducted available amount only"
        )
        qty_in_batch_unit = total_available  # clamp to what actually exists

    if qty_in_batch_unit <= 0:
        return {
            "success":         True,
            "ingredient_name": dish_ing.ingredient_name,
            "qty_deducted":    0.0,
            "unit":            batch_unit,
            "cost":            0.0,
            "batches_used":    [],
            "batch_ids":       [],
            "shortfall":       shortfall_warning or (
                f"No stock available for '{dish_ing.ingredient_name}' — nothing deducted"
            ),
        }
 
    qty_remaining  = qty_in_batch_unit
    total_cost     = Decimal("0")
    batches_used   = []
    used_batch_ids = []
 
    for batch in batches:
        if qty_remaining <= 0:
            break
 
        batch_qty          = Decimal(str(batch.quantity_remaining))
        batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
        batch_total_cost   = Decimal(str(batch.total_cost)) if batch.total_cost else Decimal("0")
        qty_from_batch     = min(batch_qty, qty_remaining)   # never deducts more than needed

        cost = (qty_from_batch / batch_qty_received) * batch_total_cost if batch_qty_received > 0 else Decimal("0")
 
        batch.quantity_remaining = float(batch_qty - qty_from_batch)
        total_cost += cost
 
        if Decimal(str(batch.quantity_remaining)) <= 0:
            batch.is_active = False
 
        db.add(InventoryTransaction(
            tenant_id=tenant_id,
            inventory_item_id=dish_ing.ingredient_id,
            batch_id=batch.id,
            transaction_type=TransactionType.SALE,
            quantity=float(qty_from_batch),
            unit_cost=float(cost / qty_from_batch) if qty_from_batch > 0 else 0,
            total_value=float(cost),
            transaction_date=sale_date,
            reference_id=f"dish_sale:{dish_ing.dish_id}",
            dish_ingredient_id=dish_ing.id,
        ))
 
        batches_used.append(batch.batch_number)
        used_batch_ids.append(batch.id)
        qty_remaining -= qty_from_batch
 
    sync_inventory_totals(dish_ing.ingredient_id, db)
    sync_dish_ingredient_costs(dish_ing.ingredient_id, db, tenant_id)
 
    return {
        "success":         True,
        "ingredient_name": dish_ing.ingredient_name,
        "qty_deducted":    float(qty_in_batch_unit),
        "unit":            batch_unit,
        "cost":            float(total_cost),
        "batches_used":    batches_used,
        "batch_ids":       used_batch_ids,
        "shortfall":       shortfall_warning,
    }

def _deduct_semi_finished_fifo(
    db: Session,
    tenant_id: int,
    dish_ing: DishIngredient,
    qty_sold: int,
    sale_date: datetime,
) -> dict:
    """
    Resolves a semi-finished product into flat raw ingredients and deducts
    each one FIFO/FEFO.

    BEHAVIOR CHANGE: same as _deduct_ingredient_fifo — never blocks the
    sale for insufficient stock on any sub-ingredient. Deducts
    min(needed, available) per sub-ingredient and records a "shortfall"
    string per sub-ingredient when it ran short.
    """

    sale_date_only = _get_sale_date_only(sale_date)
 
    # ── Fetch top-level semi-finished product ─────────────────────────
    semi = db.query(SemiFinishedProduct).filter(
        SemiFinishedProduct.id        == dish_ing.semi_finished_id,
        SemiFinishedProduct.tenant_id == tenant_id,
        SemiFinishedProduct.is_active == True,
    ).first()
 
    if not semi:
        return {
            "success":         False,
            "ingredient_name": dish_ing.ingredient_name,
            "warning":         f"Semi-finished product not found for '{dish_ing.ingredient_name}'",
            "cost":            0.0,
            "sub_ingredients": [],
            "batch_ids":       [],
        }
 
    # ── How much of the semi is needed ───────────────────────────────
    dish_sfp_unit   = _normalize_unit(dish_ing.unit)
    semi_yield_unit = _normalize_unit(semi.unit)
    qty_sfp_needed  = Decimal(str(dish_ing.quantity_required)) * Decimal(str(qty_sold))
 
    if dish_sfp_unit != semi_yield_unit:
        try:
            qty_sfp_needed = Decimal(str(convert_quantity_unit(
                value     = qty_sfp_needed,
                from_unit = dish_sfp_unit,
                to_unit   = semi_yield_unit,
            )))
        except ValueError:
            return {
                "success":         False,
                "ingredient_name": dish_ing.ingredient_name,
                "warning":         f"Cannot convert '{dish_sfp_unit}' to '{semi_yield_unit}' for semi-finished '{semi.name}'",
                "cost":            0.0,
                "sub_ingredients": [],
                "batch_ids":       [],
            }
 
    scale_factor = qty_sfp_needed / Decimal(str(semi.yield_quantity))

    flat_ingredients = _resolve_semi_to_raw_ingredients(
        db             = db,
        tenant_id      = tenant_id,
        semi_id        = semi.id,
        qty_sfp_needed = qty_sfp_needed,
    )
 
    if not flat_ingredients:
        return {
            "success":         False,
            "ingredient_name": dish_ing.ingredient_name,
            "warning":         f"Semi-finished '{semi.name}' has no sub-ingredients configured",
            "cost":            0.0,
            "sub_ingredients": [],
            "batch_ids":       [],
        }
 
    total_cost     = Decimal("0")
    sub_results    = []
    used_batch_ids = []
 
    PIECE_UNITS  = {"pcs", "piece", "pieces"}
    PACKET_UNITS = {"packet", "packets", "pkt"}
 
    # ── Deduct each flat raw ingredient ──────────────────────────────
    for sub_ing in flat_ingredients:
 
        batches = _get_batches_for_sale_date(
            db, tenant_id, sub_ing["ingredient_id"], sale_date_only
        )
 
        if not batches:
            # No batches at all — if fixed cost, still count the cost
            # (matches original behavior); otherwise report a shortfall
            # with zero deducted instead of silently skipping.
            if sub_ing["fixed_cost_amount"] is not None:
                fixed_cost  = Decimal(str(sub_ing["fixed_cost_amount"])) * sub_ing["quantity_required"]
                total_cost += fixed_cost
                sub_results.append({
                    "sub_ingredient_name": sub_ing["ingredient_name"],
                    "qty_deducted":        0.0,
                    "unit":                sub_ing["unit"],
                    "cost":                float(fixed_cost),
                    "batches_used":        [],
                })
            else:
                sub_results.append({
                    "sub_ingredient_name": sub_ing["ingredient_name"],
                    "qty_deducted":        0.0,
                    "unit":                sub_ing["unit"],
                    "cost":                0.0,
                    "batches_used":        [],
                    "shortfall": (
                        f"No batch for '{sub_ing['ingredient_name']}' (via '{semi.name}') "
                        f"on {sale_date_only} — nothing deducted"
                    ),
                })
            continue
 
        batch_unit   = _normalize_unit(batches[0].unit)
        sub_ing_unit = _normalize_unit(sub_ing["unit"])
        total_qty_needed = sub_ing["quantity_required"]
 
        # ── Fixed-cost ingredient ─────────────────────────────────────
        if sub_ing["fixed_cost_amount"] is not None:
            batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
            qty_to_deduct   = (
                (Decimal(str(sub_ing["fixed_cost_amount"])) / batch_unit_cost) * total_qty_needed
                if batch_unit_cost > 0 else Decimal("0")
            )

            total_available = sum(Decimal(str(b.quantity_remaining)) for b in batches)
            shortfall_warning = None
            if total_available < qty_to_deduct:
                shortfall_warning = (
                    f"Insufficient '{sub_ing['ingredient_name']}' (via '{semi.name}'): "
                    f"needed {float(qty_to_deduct):.4f} {batch_unit}, "
                    f"only {float(total_available):.4f} {batch_unit} available — deducted available amount only"
                )
                qty_to_deduct = total_available

            ing_cost      = Decimal("0")
            batches_used  = []
            qty_remaining = qty_to_deduct
 
            for batch in batches:
                if qty_remaining <= 0:
                    break
                batch_qty          = Decimal(str(batch.quantity_remaining))
                batch_qty_received = Decimal(str(batch.quantity_received or 0))
                batch_total_cost   = Decimal(str(batch.total_cost or 0))
                qty_from_batch     = min(batch_qty, qty_remaining)
                cost = (
                    (qty_from_batch / batch_qty_received) * batch_total_cost
                    if batch_qty_received > 0 else Decimal("0")
                )
                batch.quantity_remaining = float(batch_qty - qty_from_batch)
                ing_cost += cost
                if Decimal(str(batch.quantity_remaining)) <= 0:
                    batch.is_active = False
                db.add(InventoryTransaction(
                    tenant_id          = tenant_id,
                    inventory_item_id  = sub_ing["ingredient_id"],
                    batch_id           = batch.id,
                    transaction_type   = TransactionType.SALE,
                    quantity           = float(qty_from_batch),
                    unit_cost          = float(sub_ing["fixed_cost_amount"]),
                    total_value        = float(cost),
                    transaction_date   = sale_date,
                    reference_id       = f"sfp_sale:{semi.id}:dish:{dish_ing.dish_id}",
                    dish_ingredient_id = dish_ing.id,
                ))
                batches_used.append(batch.batch_number)
                used_batch_ids.append(batch.id)
                qty_remaining -= qty_from_batch
 
            sync_inventory_totals(sub_ing["ingredient_id"], db)
            sync_dish_ingredient_costs(sub_ing["ingredient_id"], db, tenant_id)
 
            fixed_cost  = Decimal(str(sub_ing["fixed_cost_amount"])) * total_qty_needed
            total_cost += fixed_cost
            sub_results.append({
                "sub_ingredient_name": sub_ing["ingredient_name"],
                "qty_deducted":        float(qty_to_deduct - qty_remaining),
                "unit":                batch_unit,
                "cost":                float(fixed_cost),
                "batches_used":        batches_used,
                "shortfall":           shortfall_warning,
            })
            continue
 
        # ── Piece → Packet conversion ─────────────────────────────────
        if sub_ing_unit in PIECE_UNITS and batch_unit in PACKET_UNITS:
            qty_remaining = total_qty_needed
            ing_cost      = Decimal("0")
            batches_used  = []

            total_pieces_available = sum(
                Decimal(str(b.quantity_remaining)) * (Decimal(str(b.pieces)) if b.pieces else Decimal("1"))
                for b in batches
            )
            shortfall_warning = None
            if total_pieces_available < total_qty_needed:
                shortfall_warning = (
                    f"Insufficient '{sub_ing['ingredient_name']}' (via '{semi.name}'): "
                    f"needed {float(total_qty_needed)} pcs, only {float(total_pieces_available)} pcs "
                    f"available — deducted available amount only"
                )

            for batch in batches:
                if qty_remaining <= 0:
                    break
                pieces_per_packet  = Decimal(str(batch.pieces)) if batch.pieces else Decimal("1")
                batch_qty_packets  = Decimal(str(batch.quantity_remaining))
                batch_qty_received = Decimal(str(batch.quantity_received or 0))
                batch_total_cost   = Decimal(str(batch.total_cost or 0))
                pieces_in_batch    = batch_qty_packets * pieces_per_packet
                pieces_from_batch  = min(pieces_in_batch, qty_remaining)
                packets_to_deduct  = pieces_from_batch / pieces_per_packet
                cost = (
                    (packets_to_deduct / batch_qty_received) * batch_total_cost
                    if batch_qty_received > 0 else Decimal("0")
                )
                batch.quantity_remaining = float(batch_qty_packets - packets_to_deduct)
                ing_cost += cost
                if Decimal(str(batch.quantity_remaining)) <= 0:
                    batch.is_active = False
                db.add(InventoryTransaction(
                    tenant_id          = tenant_id,
                    inventory_item_id  = sub_ing["ingredient_id"],
                    batch_id           = batch.id,
                    transaction_type   = TransactionType.SALE,
                    quantity           = float(packets_to_deduct),
                    unit_cost          = float(cost / pieces_from_batch) if pieces_from_batch > 0 else 0,
                    total_value        = float(cost),
                    transaction_date   = sale_date,
                    reference_id       = f"sfp_sale:{semi.id}:dish:{dish_ing.dish_id}",
                    dish_ingredient_id = dish_ing.id,
                ))
                batches_used.append(batch.batch_number)
                used_batch_ids.append(batch.id)
                qty_remaining -= pieces_from_batch
 
            sync_inventory_totals(sub_ing["ingredient_id"], db)
            sync_dish_ingredient_costs(sub_ing["ingredient_id"], db, tenant_id)
            total_cost += ing_cost
            sub_results.append({
                "sub_ingredient_name": sub_ing["ingredient_name"],
                "qty_deducted":        float(total_qty_needed - qty_remaining),
                "unit":                "pcs",
                "cost":                float(ing_cost),
                "batches_used":        batches_used,
                "shortfall":           shortfall_warning,
            })
            continue
 
        # ── Normal unit conversion + FIFO deduction ───────────────────
        try:
            qty_in_batch_unit = (
                Decimal(str(convert_quantity_unit(
                    value     = total_qty_needed,
                    from_unit = sub_ing_unit,
                    to_unit   = batch_unit,
                )))
                if sub_ing_unit and sub_ing_unit != batch_unit
                else total_qty_needed
            )
        except ValueError:
            qty_in_batch_unit = total_qty_needed

        total_available_here = sum(Decimal(str(b.quantity_remaining)) for b in batches)
        shortfall_warning = None
        if total_available_here < qty_in_batch_unit:
            shortfall_warning = (
                f"Insufficient '{sub_ing['ingredient_name']}' (via '{semi.name}'): "
                f"needed {float(qty_in_batch_unit):.4f} {batch_unit}, "
                f"only {float(total_available_here):.4f} {batch_unit} available — "
                f"deducted available amount only"
            )
            # do NOT clamp qty_in_batch_unit here — the loop below already
            # naturally stops at total_available_here via per-batch min(),
            # we just needed the comparison to build the warning message.

        qty_remaining = qty_in_batch_unit
        ing_cost      = Decimal("0")
        batches_used  = []
 
        for batch in batches:
            if qty_remaining <= 0:
                break
            batch_qty          = Decimal(str(batch.quantity_remaining))
            batch_qty_received = Decimal(str(batch.quantity_received or 0))
            batch_total_cost   = Decimal(str(batch.total_cost or 0))
            qty_from_batch     = min(batch_qty, qty_remaining)   # never more than needed
            cost = (
                (qty_from_batch / batch_qty_received) * batch_total_cost
                if batch_qty_received > 0 else Decimal("0")
            )
            batch.quantity_remaining = float(batch_qty - qty_from_batch)
            ing_cost += cost
            if Decimal(str(batch.quantity_remaining)) <= 0:
                batch.is_active = False
            db.add(InventoryTransaction(
                tenant_id          = tenant_id,
                inventory_item_id  = sub_ing["ingredient_id"],
                batch_id           = batch.id,
                transaction_type   = TransactionType.SALE,
                quantity           = float(qty_from_batch),
                unit_cost          = float(cost / qty_from_batch) if qty_from_batch > 0 else 0,
                total_value        = float(cost),
                transaction_date   = sale_date,
                reference_id       = f"sfp_sale:{semi.id}:dish:{dish_ing.dish_id}",
                dish_ingredient_id = dish_ing.id,
            ))
            batches_used.append(batch.batch_number)
            used_batch_ids.append(batch.id)
            qty_remaining -= qty_from_batch
 
        sync_inventory_totals(sub_ing["ingredient_id"], db)
        sync_dish_ingredient_costs(sub_ing["ingredient_id"], db, tenant_id)
        total_cost += ing_cost
        sub_results.append({
            "sub_ingredient_name": sub_ing["ingredient_name"],
            "qty_deducted":        float(qty_in_batch_unit - qty_remaining),
            "unit":                batch_unit,
            "cost":                float(ing_cost),
            "batches_used":        batches_used,
            "shortfall":           shortfall_warning,
        })
 
    return {
        "success":            True,
        "ingredient_name":    dish_ing.ingredient_name,
        "semi_finished_name": semi.name,
        "scale_factor":       float(scale_factor),
        "qty_used":           float(qty_sfp_needed),
        "unit":               semi.unit,
        "cost":               float(total_cost),
        "sub_ingredients":    sub_results,
        "batch_ids":          used_batch_ids,
    }
 
@router.post("/upload-sales-excel", status_code=status.HTTP_201_CREATED)
def upload_sales_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        if not file.filename.endswith((".xlsx", ".xls", ".csv")):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only .xlsx, .xls or .csv allowed",
            )

        try:
            contents = file.file.read()
            df, is_ciferon = _parse_sales_file(contents, filename=file.filename)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        df = df[df["item_name"].notna() & df["order_qty"].notna()]
        if df.empty:
            raise HTTPException(status_code=400, detail="No valid rows found in file")

        if "sale_datetime" not in df.columns:
            df["sale_datetime"] = datetime.now(timezone.utc)

        df["item_name_lower"] = df["item_name"].str.strip().str.lower()
        df["sale_date_only"]  = df["sale_datetime"].apply(_get_sale_date_only)
        df["order_qty"]       = pd.to_numeric(df["order_qty"], errors="coerce").fillna(0).astype(int)

        # ── Fetch all dishes and combos upfront by name ───────────────
        all_names_lower = df["item_name_lower"].unique().tolist()

        dishes = (
            db.query(Dish)
            .filter(
                func.lower(Dish.name).in_(all_names_lower),
                Dish.tenant_id == tenant_id,
                Dish.is_active == True,
            )
            .all()
        )
        dish_map = {d.name.strip().lower(): d for d in dishes}

        combos = (
            db.query(Combo)
            .filter(
                func.lower(Combo.name).in_(all_names_lower),
                Combo.tenant_id == tenant_id,
            )
            .all()
        )
        combo_map = {c.name.strip().lower(): c for c in combos}

        # ── NEW: Fetch all inventory items upfront by name ────────────
        inventory_items = (
            db.query(Inventory)
            .filter(
                func.lower(Inventory.name).in_(all_names_lower),
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            )
            .all()
        )
        inventory_item_map = {i.name.strip().lower(): i for i in inventory_items}

        # ── Resolve each row as dish, combo, or inventory_item ────────
        def resolve_item_type(row):
            if "item_type" in df.columns and pd.notna(row.get("item_type")):
                t = str(row["item_type"]).strip().lower()
                if t in ("dish", "combo", "inventory_item"):
                    return t
            name = row["item_name_lower"]
            if name in dish_map:
                return "dish"
            if name in combo_map:
                return "combo"
            # ── NEW: fall through to inventory item check ─────────────
            if name in inventory_item_map:
                return "inventory_item"
            return "unknown"

        df["item_type"] = df.apply(resolve_item_type, axis=1)

        # ── Split into dish rows, combo rows, and inventory item rows ─
        dish_df  = df[df["item_type"] == "dish"].copy()
        combo_df = df[df["item_type"] == "combo"].copy()
        # ── NEW ───────────────────────────────────────────────────────
        inv_df   = df[df["item_type"] == "inventory_item"].copy()

        unknown_names = df[df["item_type"] == "unknown"]["item_name"].unique().tolist()

        # ── Group dishes by name + date ───────────────────────────────
        dish_grouped = (
            dish_df.groupby(["item_name_lower", "sale_date_only"])
            .agg(
                total_qty=("order_qty", "sum"),
                sale_datetime=("sale_datetime", "first"),
            )
            .reset_index()
        ) if not dish_df.empty else pd.DataFrame()

        # ── Group combos by name + date ───────────────────────────────
        combo_grouped = (
            combo_df.groupby(["item_name_lower", "sale_date_only"])
            .agg(
                total_qty=("order_qty", "sum"),
                sale_datetime=("sale_datetime", "first"),
            )
            .reset_index()
        ) if not combo_df.empty else pd.DataFrame()

        inv_grouped = (
            inv_df.groupby(["item_name_lower", "sale_date_only"])
            .agg(
                total_qty=("order_qty", "sum"),
                sale_datetime=("sale_datetime", "first"),
            )
            .reset_index()
        ) if not inv_df.empty else pd.DataFrame()

        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        def _calc_qty_in_batch_unit(
            qty_needed: Decimal,
            dish_ing_unit: str,
            batch_unit: str,
            batches: list,
            ingredient_name: str,
            dish_name: str,
        ) -> tuple[Decimal, str | None]:
            if dish_ing_unit in PIECE_UNITS and batch_unit in PACKET_UNITS:
                qty_remaining_pieces = qty_needed
                total_packets_needed = Decimal("0")
                for batch in batches:
                    if qty_remaining_pieces <= 0:
                        break
                    pieces_per_packet    = Decimal(str(batch.pieces)) if batch.pieces else Decimal("1")
                    batch_qty_packets    = Decimal(str(batch.quantity_remaining))
                    pieces_in_batch      = batch_qty_packets * pieces_per_packet
                    pieces_from_batch    = min(pieces_in_batch, qty_remaining_pieces)
                    packets_to_deduct    = pieces_from_batch / pieces_per_packet
                    total_packets_needed += packets_to_deduct
                    qty_remaining_pieces -= pieces_from_batch
                return total_packets_needed, None

            if dish_ing_unit != batch_unit:
                if not are_units_compatible(dish_ing_unit, batch_unit):
                    return Decimal("0"), (
                        f"'{dish_name}': incompatible units for '{ingredient_name}': "
                        f"cannot convert '{dish_ing_unit}' to '{batch_unit}'"
                    )
                try:
                    converted = Decimal(str(convert_quantity_unit(
                        value=qty_needed, from_unit=dish_ing_unit, to_unit=batch_unit,
                    )))
                    return converted, None
                except ValueError as e:
                    return Decimal("0"), (
                        f"'{dish_name}': unit conversion failed for '{ingredient_name}': {e}"
                    )
            return qty_needed, None

        # ══════════════════════════════════════════════════════════════
        # PHASE 1 — VALIDATE STRUCTURE (this phase is unchanged: it only
        # checks structural problems like missing dish/combo/ingredient
        # configuration. It does NOT pre-check stock quantities anymore —
        # see note where PHASE 2 used to be, below.)
        # ══════════════════════════════════════════════════════════════
        dish_data_map:     dict[tuple, dict] = {}
        combo_data_map:    dict[tuple, dict] = {}
        inv_data_map:      dict[tuple, dict] = {}
        warnings:          list[str]         = []
        structural_errors: list[str]         = []

        for name in unknown_names:
            warnings.append(f"'{name}' not found as dish or combo in system - skipped")

        for _, row in dish_grouped.iterrows():
            name_lower     = row["item_name_lower"]
            qty_sold       = int(row["total_qty"])
            sale_date_only = row["sale_date_only"]
            sale_datetime  = row["sale_datetime"]
            dish           = dish_map.get(name_lower)

            if not dish:
                warnings.append(f"Dish '{name_lower}' not found in system - skipped")
                continue

            dish_ingredients = (
                db.query(DishIngredient)
                .filter(
                    DishIngredient.dish_id   == dish.id,
                    DishIngredient.tenant_id == tenant_id,
                )
                .all()
            )

            if not dish_ingredients:
                warnings.append(f"'{dish.name}' has no ingredients configured - skipped")
                continue

            raw_ingredients  = [i for i in dish_ingredients if i.semi_finished_id is None]
            semi_ingredients = [i for i in dish_ingredients if i.semi_finished_id is not None]

            dish_key = (name_lower, sale_date_only)
            dish_data_map[dish_key] = {
                "dish":             dish,
                "qty_sold":         qty_sold,
                "sale_datetime":    sale_datetime,
                "sale_date_only":   sale_date_only,
                "raw_ingredients":  raw_ingredients,
                "semi_ingredients": semi_ingredients,
            }

            # Structural validation only — confirm ingredient_id/batch
            # existence so we know whether to warn about config issues.
            # Quantity sufficiency is no longer checked here (see Phase 3).
            for dish_ing in raw_ingredients:
                if not dish_ing.ingredient_id:
                    warnings.append(
                        f"'{dish.name}': raw ingredient '{dish_ing.ingredient_name}' has no ingredient_id"
                    )
                    continue

                inventory = db.query(Inventory).filter(
                    Inventory.id        == dish_ing.ingredient_id,
                    Inventory.tenant_id == tenant_id,
                    Inventory.is_active == True,
                ).first()

                if not inventory:
                    warnings.append(
                        f"'{dish.name}': inventory not found for '{dish_ing.ingredient_name}' - skipped"
                    )
                    continue

                batches = _get_batches_for_sale_date(db, tenant_id, dish_ing.ingredient_id, sale_date_only)
                if not batches:
                    warnings.append(
                        f"'{dish.name}': no batch found for '{dish_ing.ingredient_name}' "
                        f"valid on {sale_date_only} — will be deducted as 0 at sale time"
                    )
                    continue

        for _, row in combo_grouped.iterrows():
            name_lower     = row["item_name_lower"]
            qty_sold       = int(row["total_qty"])
            sale_date_only = row["sale_date_only"]
            sale_datetime  = row["sale_datetime"]
            combo          = combo_map.get(name_lower)

            if not combo:
                warnings.append(f"Combo '{name_lower}' not found in system — skipped")
                continue

            combo_items = (
                db.query(ComboItem)
                .filter(
                    ComboItem.combo_id  == combo.id,
                    ComboItem.tenant_id == tenant_id,
                )
                .all()
            )

            if not combo_items:
                warnings.append(f"Combo '{combo.name}' has no items configured  — skipped")
                continue

            combo_key = (name_lower, sale_date_only)
            combo_data_map[combo_key] = {
                "combo":          combo,
                "qty_sold":       qty_sold,
                "sale_datetime":  sale_datetime,
                "sale_date_only": sale_date_only,
                "combo_items":    combo_items,
            }

            for ci in combo_items:
                if ci.dish_id is None and ci.semi_finished_id is None and ci.ingredient_id is None:
                    structural_errors.append(
                        f"Combo '{combo.name}': item id={ci.id} has no dish/semi/ingredient reference"
                    )

        for _, row in inv_grouped.iterrows():
            name_lower     = row["item_name_lower"]
            qty_sold       = int(row["total_qty"])
            sale_date_only = row["sale_date_only"]
            sale_datetime  = row["sale_datetime"]
            inv_item       = inventory_item_map.get(name_lower)

            if not inv_item:
                warnings.append(f"Inventory item '{name_lower}' not found — skipped")
                continue

            inv_data_map[(name_lower, sale_date_only)] = {
                "inv_item":       inv_item,
                "qty_sold":       qty_sold,
                "sale_datetime":  sale_datetime,
                "sale_date_only": sale_date_only,
            }

        if structural_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Validation failed. No sales recorded, no inventory deducted.",
                    "errors":  structural_errors,
                },
            )

        # ══════════════════════════════════════════════════════════════
        # PHASE 2 — (REMOVED) pre-flight quantity sufficiency check.
        #
        # Previously this phase pre-computed total qty needed per
        # ingredient across the whole file and rejected/warned on
        # insufficient stock BEFORE any deduction happened.
        #
        # New behavior: stock sufficiency is no longer pre-checked here.
        # Every deduction function now deducts min(needed, available)
        # and reports its own accurate "shortfall" warning at the time
        # it actually deducts (see Phase 3). A sale is NEVER blocked for
        # insufficient stock — partial stock is consumed and the
        # shortfall is surfaced in the response's "warnings" list.
        # ══════════════════════════════════════════════════════════════

        # ══════════════════════════════════════════════════════════════
        # PHASE 3 — RECORD SALES + DEDUCT INVENTORY (partial-deduction aware)
        # ══════════════════════════════════════════════════════════════
        sales_recorded             = []
        total_dishes_sold          = 0
        total_combos_sold          = 0
        total_inv_items_sold       = 0
        total_inventory_deductions = 0
        affected_batch_ids         = set()

        # ── Phase 3: dishes ───────────────────────────────────────────
        for dish_key, data in dish_data_map.items():
            dish             = data["dish"]
            qty_sold         = data["qty_sold"]
            sale_datetime    = data["sale_datetime"]
            raw_ingredients  = data["raw_ingredients"]
            semi_ingredients = data["semi_ingredients"]
            total_dishes_sold += qty_sold

            sale = DishSale(
                tenant_id     = tenant_id,
                dish_id       = dish.id,
                combo_id      = None,
                quantity_sold = qty_sold,
                unit_price    = dish.selling_price,
                total_amount  = (
                    Decimal(str(dish.selling_price or 0)) * qty_sold
                    if dish.selling_price else None
                ),
                sale_date=(
                    sale_datetime
                    if pd.notna(sale_datetime)
                    else datetime.now(timezone.utc)
                ),
            )
            db.add(sale)
            db.flush()

            deduction_details = []

            for dish_ing in raw_ingredients:
                inventory = db.query(Inventory).filter(
                    Inventory.id        == dish_ing.ingredient_id,
                    Inventory.tenant_id == tenant_id,
                    Inventory.is_active == True,
                ).first()
                result = _deduct_ingredient_fifo(
                    db=db, tenant_id=tenant_id,
                    dish_ing=dish_ing,
                    total_qty_needed_recipe=Decimal(str(dish_ing.quantity_required)) * qty_sold,
                    inventory=inventory,
                    sale_date=sale_datetime,
                )
                if result["success"]:
                    affected_batch_ids.update(result["batch_ids"])
                    if result.get("shortfall"):
                        warnings.append(f"'{dish.name}' on {data['sale_date_only']}: {result['shortfall']}")
                    deduction_details.append({
                        "type":            "raw",
                        "ingredient_name": result["ingredient_name"],
                        "qty_deducted":    result["qty_deducted"],
                        "unit":            result["unit"],
                        "cost":            result["cost"],
                        "batches_used":    result["batches_used"],
                    })
                    total_inventory_deductions += 1
                else:
                    # Only genuinely structural failures land here now
                    # (no batch exists at all / incompatible units).
                    warnings.append(
                        f"'{dish.name}' on {data['sale_date_only']}: {result['warning']}"
                    )

            for dish_ing in semi_ingredients:
                result = _deduct_semi_finished_fifo(
                    db=db, tenant_id=tenant_id,
                    dish_ing=dish_ing,
                    qty_sold=qty_sold,
                    sale_date=sale_datetime,
                )
                if result["success"]:
                    affected_batch_ids.update(result["batch_ids"])
                    for sub in result["sub_ingredients"]:
                        if sub.get("shortfall"):
                            warnings.append(f"'{dish.name}' on {data['sale_date_only']}: {sub['shortfall']}")
                    deduction_details.append({
                        "type":               "semi_finished",
                        "ingredient_name":    result["ingredient_name"],
                        "semi_finished_name": result["semi_finished_name"],
                        "qty_used":           result["qty_used"],
                        "unit":               result["unit"],
                        "scale_factor":       result["scale_factor"],
                        "cost":               result["cost"],
                        "sub_ingredients":    result["sub_ingredients"],
                    })
                    total_inventory_deductions += len(result["sub_ingredients"])
                else:
                    warnings.append(
                        f"'{dish.name}' on {data['sale_date_only']}: {result['warning']}"
                    )

            sale.cogs_amount = float(sum(Decimal(str(d.get("cost", 0))) for d in deduction_details))
            db.add(sale)

            sales_recorded.append({
                "type":               "dish",
                "dish_id":            dish.id,
                "dish_name":          dish.name,
                "qty_sold":           qty_sold,
                "sale_date":          str(data["sale_date_only"]),
                "combo_id":           None,
                "combo_name":         None,
                "sale_recorded":      True,
                "inventory_deducted": True,
                "deduction_details":  deduction_details,
            })

        # ── Phase 3: combos ───────────────────────────────────────────
        for combo_key, data in combo_data_map.items():
            combo          = data["combo"]
            qty_sold       = data["qty_sold"]
            sale_datetime  = data["sale_datetime"]
            sale_date_only = data["sale_date_only"]
            combo_items    = data["combo_items"]
            total_combos_sold += qty_sold

            combo_sale = DishSale(
                tenant_id     = tenant_id,
                dish_id       = None,
                combo_id      = combo.id,
                quantity_sold = qty_sold,
                unit_price    = combo.selling_price,
                total_amount  = (
                    Decimal(str(combo.selling_price or 0)) * qty_sold
                    if combo.selling_price else None
                ),
                cogs_amount   = None,
                sale_date     = (
                    sale_datetime
                    if pd.notna(sale_datetime)
                    else datetime.now(timezone.utc)
                ),
            )
            db.add(combo_sale)
            db.flush()

            combo_deduction_details = []

            for ci in combo_items:
                ci_qty = Decimal(str(ci.quantity or 1)) * qty_sold

                # ── combo item is a DISH ──────────────────────────────
                if ci.dish_id is not None:
                    dish = db.query(Dish).filter(
                        Dish.id        == ci.dish_id,
                        Dish.tenant_id == tenant_id,
                    ).first()
                    if not dish:
                        continue

                    dish_ingredients = (
                        db.query(DishIngredient)
                        .filter(
                            DishIngredient.dish_id   == dish.id,
                            DishIngredient.tenant_id == tenant_id,
                        )
                        .all()
                    )

                    dish_sale = DishSale(
                        tenant_id     = tenant_id,
                        dish_id       = dish.id,
                        combo_id      = combo.id,
                        quantity_sold = int(ci_qty),
                        unit_price    = dish.selling_price,
                        total_amount  = None,
                        sale_date     = (
                            sale_datetime
                            if pd.notna(sale_datetime)
                            else datetime.now(timezone.utc)
                        ),
                    )
                    db.add(dish_sale)
                    db.flush()

                    dish_deductions = []

                    for dish_ing in [i for i in dish_ingredients if i.semi_finished_id is None]:
                        inventory = db.query(Inventory).filter(
                            Inventory.id        == dish_ing.ingredient_id,
                            Inventory.tenant_id == tenant_id,
                            Inventory.is_active == True,
                        ).first()
                        result = _deduct_ingredient_fifo(
                            db=db, tenant_id=tenant_id,
                            dish_ing=dish_ing,
                            total_qty_needed_recipe=Decimal(str(dish_ing.quantity_required)) * ci_qty,
                            inventory=inventory,
                            sale_date=sale_datetime,
                        )
                        if result["success"]:
                            affected_batch_ids.update(result["batch_ids"])
                            if result.get("shortfall"):
                                warnings.append(
                                    f"Combo '{combo.name}' → dish '{dish.name}': {result['shortfall']}"
                                )
                            dish_deductions.append({
                                "type":            "raw",
                                "ingredient_name": result["ingredient_name"],
                                "qty_deducted":    result["qty_deducted"],
                                "unit":            result["unit"],
                                "cost":            result["cost"],
                                "batches_used":    result["batches_used"],
                            })
                            total_inventory_deductions += 1
                        else:
                            warnings.append(
                                f"Combo '{combo.name}' → dish '{dish.name}': {result['warning']}"
                            )

                    for dish_ing in [i for i in dish_ingredients if i.semi_finished_id is not None]:
                        result = _deduct_semi_finished_fifo(
                            db=db, tenant_id=tenant_id,
                            dish_ing=dish_ing,
                            qty_sold=ci_qty,
                            sale_date=sale_datetime,
                        )
                        if result["success"]:
                            affected_batch_ids.update(result["batch_ids"])
                            for sub in result["sub_ingredients"]:
                                if sub.get("shortfall"):
                                    warnings.append(
                                        f"Combo '{combo.name}' → dish '{dish.name}': {sub['shortfall']}"
                                    )
                            dish_deductions.append({
                                "type":               "semi_finished",
                                "ingredient_name":    result["ingredient_name"],
                                "semi_finished_name": result["semi_finished_name"],
                                "qty_used":           result["qty_used"],
                                "unit":               result["unit"],
                                "scale_factor":       result["scale_factor"],
                                "cost":               result["cost"],
                                "sub_ingredients":    result["sub_ingredients"],
                            })
                            total_inventory_deductions += len(result["sub_ingredients"])
                        else:
                            warnings.append(
                                f"Combo '{combo.name}' → dish '{dish.name}': {result['warning']}"
                            )

                    dish_sale_cogs = float(
                        sum(Decimal(str(d.get("cost", 0))) for d in dish_deductions)
                    )
                    dish_sale.cogs_amount = dish_sale_cogs
                    db.add(dish_sale)

                    combo_deduction_details.append({
                        "item_type":  "dish",
                        "dish_id":    dish.id,
                        "dish_name":  dish.name,
                        "qty":        int(ci_qty),
                        "deductions": dish_deductions,
                        "cost":       dish_sale_cogs,
                    })

                # ── combo item is a SEMI-FINISHED ─────────────────────
                elif ci.semi_finished_id is not None:
                    class _SemiShim:
                        semi_finished_id  = ci.semi_finished_id
                        ingredient_name   = ci.item_name
                        unit              = ci.unit
                        quantity_required = ci.quantity
                        fixed_cost_amount = None
                        dish_id           = None
                        id                = None

                    result = _deduct_semi_finished_fifo(
                        db=db, tenant_id=tenant_id,
                        dish_ing=_SemiShim(),
                        qty_sold=qty_sold,
                        sale_date=sale_datetime,
                    )
                    if result["success"]:
                        affected_batch_ids.update(result["batch_ids"])
                        for sub in result["sub_ingredients"]:
                            if sub.get("shortfall"):
                                warnings.append(
                                    f"Combo '{combo.name}' → semi '{ci.item_name}': {sub['shortfall']}"
                                )
                        total_inventory_deductions += len(result["sub_ingredients"])
                        combo_deduction_details.append({
                            "item_type":       "semi_finished",
                            "item_name":       ci.item_name,
                            "qty":             float(ci_qty),
                            "cost":            result["cost"],
                            "sub_ingredients": result["sub_ingredients"],
                        })
                    else:
                        warnings.append(
                            f"Combo '{combo.name}' → semi '{ci.item_name}': {result['warning']}"
                        )

                # ── combo item is a RAW INGREDIENT ────────────────────
                elif ci.ingredient_id is not None:
                    inventory = db.query(Inventory).filter(
                        Inventory.id        == ci.ingredient_id,
                        Inventory.tenant_id == tenant_id,
                        Inventory.is_active == True,
                    ).first()

                    class _RawShim:
                        ingredient_id     = ci.ingredient_id
                        ingredient_name   = ci.item_name
                        unit              = ci.unit
                        quantity_required = ci.quantity
                        fixed_cost_amount = None
                        dish_id           = None
                        id                = None

                    result = _deduct_ingredient_fifo(
                        db=db, tenant_id=tenant_id,
                        dish_ing=_RawShim(),
                        total_qty_needed_recipe=Decimal(str(ci.quantity or 1)) * qty_sold,
                        inventory=inventory,
                        sale_date=sale_datetime,
                    )
                    if result["success"]:
                        affected_batch_ids.update(result["batch_ids"])
                        if result.get("shortfall"):
                            warnings.append(
                                f"Combo '{combo.name}' → ingredient '{ci.item_name}': {result['shortfall']}"
                            )
                        total_inventory_deductions += 1
                        combo_deduction_details.append({
                            "item_type":    "raw",
                            "item_name":    ci.item_name,
                            "qty_deducted": result["qty_deducted"],
                            "unit":         result["unit"],
                            "cost":         result["cost"],
                            "batches_used": result["batches_used"],
                        })
                    else:
                        warnings.append(
                            f"Combo '{combo.name}' → ingredient '{ci.item_name}': {result['warning']}"
                        )

                else:
                    structural_errors.append(
                        f"Combo '{combo.name}': item id={ci.id} has no dish/semi/ingredient reference"
                    )

            combo_sale.cogs_amount = float(
                sum(Decimal(str(d.get("cost", 0))) for d in combo_deduction_details)
            )
            db.add(combo_sale)

            sales_recorded.append({
                "type":               "combo",
                "combo_id":           combo.id,
                "combo_name":         combo.name,
                "qty_sold":           qty_sold,
                "sale_date":          str(sale_date_only),
                "sale_recorded":      True,
                "inventory_deducted": True,
                "deduction_details":  combo_deduction_details,
            })

        # ── Phase 3: direct inventory items ────────────────────────────
        for inv_key, data in inv_data_map.items():
            inv_item       = data["inv_item"]
            qty_sold       = data["qty_sold"]
            sale_datetime  = data["sale_datetime"]
            sale_date_only = data["sale_date_only"]
            total_inv_items_sold += qty_sold

            sale = DishSale(
                tenant_id     = tenant_id,
                dish_id       = None,
                combo_id      = None,
                quantity_sold = qty_sold,
                unit_price    = None,
                total_amount  = None,
                sale_date     = (
                    sale_datetime
                    if pd.notna(sale_datetime)
                    else datetime.now(timezone.utc)
                ),
            )
            db.add(sale)
            db.flush()

            class _InvShim:
                ingredient_id     = inv_item.id
                ingredient_name   = inv_item.name
                unit              = inv_item.unit
                quantity_required = Decimal("1")
                fixed_cost_amount = None
                dish_id           = None
                id                = None

            inventory = db.query(Inventory).filter(
                Inventory.id        == inv_item.id,
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).first()

            result = _deduct_ingredient_fifo(
                db=db, tenant_id=tenant_id,
                dish_ing=_InvShim(),
                total_qty_needed_recipe=Decimal(str(qty_sold)),
                inventory=inventory,
                sale_date=sale_datetime,
            )

            if result["success"]:
                affected_batch_ids.update(result["batch_ids"])
                if result.get("shortfall"):
                    warnings.append(
                        f"Inventory item '{inv_item.name}' on {sale_date_only}: {result['shortfall']}"
                    )
                total_inventory_deductions += 1
                sale.cogs_amount = result["cost"]
                db.add(sale)
                sales_recorded.append({
                    "type":                "inventory_item",
                    "inventory_item_id":   inv_item.id,
                    "inventory_item_name": inv_item.name,
                    "qty_sold":            qty_sold,
                    "sale_date":           str(sale_date_only),
                    "sale_recorded":       True,
                    "inventory_deducted":  True,
                    "deduction_details":   [{
                        "type":            "raw",
                        "ingredient_name": result["ingredient_name"],
                        "qty_deducted":    result["qty_deducted"],
                        "unit":            result["unit"],
                        "cost":            result["cost"],
                        "batches_used":    result["batches_used"],
                    }],
                })
            else:
                warnings.append(
                    f"Inventory item '{inv_item.name}' on {sale_date_only}: {result['warning']}"
                )

        db.commit()

        return {
            "success":                    True,
            "file_format_detected":       "ciferon_export" if is_ciferon else "cleaned_format",
            "total_rows_in_excel":        len(df),
            "total_unique_dishes":        len(dish_grouped),
            "total_unique_combos":        len(combo_grouped),
            "total_unique_inv_items":     len(inv_grouped),
            "total_dishes_sold":          total_dishes_sold,
            "total_combos_sold":          total_combos_sold,
            "total_inv_items_sold":       total_inv_items_sold,
            "total_inventory_deductions": total_inventory_deductions,
            "warnings":                   warnings,
            "sales":                      sales_recorded,
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"Database error during sales upload: {db_error}")
        raise HTTPException(status_code=500, detail="Database error during sales upload")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error during sales upload: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
@router.post("/add-ordered-dish", status_code=status.HTTP_201_CREATED)
def add_sold_dish(
    payload: OrderSaleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # ── Validate dishes ───────────────────────────────────────────
        dish_map = {}
        if payload.sales:
            dish_ids = [s.dish_id for s in payload.sales]
            dishes = (
                db.query(Dish)
                .filter(
                    Dish.id.in_(dish_ids),
                    Dish.tenant_id == tenant_id,
                    Dish.is_active == True,
                )
                .all()
            )
            dish_map = {d.id: d for d in dishes}
            missing_dish_ids = set(dish_ids) - set(dish_map.keys())
            if missing_dish_ids:
                raise HTTPException(
                    status_code=404,
                    detail=f"Dishes not found: {sorted(missing_dish_ids)}",
                )

        # ── Validate combos ───────────────────────────────────────────
        combo_map = {}
        if payload.combo_sales:
            combo_ids = [s.combo_id for s in payload.combo_sales]
            combos = (
                db.query(Combo)
                .filter(
                    Combo.id.in_(combo_ids),
                    Combo.tenant_id == tenant_id,
                )
                .all()
            )
            combo_map = {c.id: c for c in combos}
            missing_combo_ids = set(combo_ids) - set(combo_map.keys())
            if missing_combo_ids:
                raise HTTPException(
                    status_code=404,
                    detail=f"Combos not found: {sorted(missing_combo_ids)}",
                )

        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        # ══════════════════════════════════════════════════════════════
        # PHASE 1 — VALIDATE STRUCTURE + ACCUMULATE TOTAL QTY NEEDED
        # ══════════════════════════════════════════════════════════════

        qty_needed_map:    dict[tuple, dict] = {}
        dish_data_map:     dict[int, dict]   = {}
        combo_data_map:    dict[int, dict]   = {}
        warnings:          list[str]         = []
        structural_errors: list[str]         = []  # hard misconfig only

        # ── Phase 1: dishes ───────────────────────────────────────────
        for sale_item in payload.sales:
            dish     = dish_map[sale_item.dish_id]
            qty_sold = sale_item.qty_sold

            sale_dt = (
                sale_item.date
                or payload.sale_date
                or datetime.now(timezone.utc)
            )
            sale_date_only = sale_dt.date() if hasattr(sale_dt, "date") else date.today()

            dish_ingredients = (
                db.query(DishIngredient)
                .filter(
                    DishIngredient.dish_id   == dish.id,
                    DishIngredient.tenant_id == tenant_id,
                )
                .all()
            )

            if not dish_ingredients:
                warnings.append(f"'{dish.name}' has no ingredients configured — skipped")
                continue

            raw_ingredients  = [i for i in dish_ingredients if i.semi_finished_id is None]
            semi_ingredients = [i for i in dish_ingredients if i.semi_finished_id is not None]

            dish_data_map[dish.id] = {
                "dish":             dish,
                "qty_sold":         qty_sold,
                "sale_dt":          sale_dt,
                "sale_date_only":   sale_date_only,
                "raw_ingredients":  raw_ingredients,
                "semi_ingredients": semi_ingredients,
            }

            for dish_ing in raw_ingredients:
                if not dish_ing.ingredient_id:
                    warnings.append(
                        f"'{dish.name}': raw ingredient '{dish_ing.ingredient_name}' has no ingredient_id"
                    )
                    continue

                inventory = db.query(Inventory).filter(
                    Inventory.id        == dish_ing.ingredient_id,
                    Inventory.tenant_id == tenant_id,
                    Inventory.is_active == True,
                ).first()

                if not inventory:
                    warnings.append(
                        f"'{dish.name}': inventory not found for '{dish_ing.ingredient_name}' — skipped"
                    )
                    continue

                batches = _get_valid_batches(db, tenant_id, dish_ing.ingredient_id, sale_date_only)

                if not batches:
                    warnings.append(
                        f"'{dish.name}': no batch found for '{dish_ing.ingredient_name}' "
                        f"valid on {sale_date_only} — skipped"
                    )
                    continue

                batch_unit    = _normalize_unit(batches[0].unit)
                dish_ing_unit = _normalize_unit(dish_ing.unit)

                if dish_ing.fixed_cost_amount is not None:
                    batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
                    qty_recipe      = Decimal(str(dish_ing.quantity_required)) * Decimal(str(qty_sold))
                    qty_needed = (
                        Decimal(str(dish_ing.fixed_cost_amount)) / batch_unit_cost * qty_recipe
                        if batch_unit_cost > 0 else Decimal("0")
                    )
                    _accumulate(qty_needed_map, dish_ing.ingredient_id, sale_date_only,
                                batch_unit, dish_ing.ingredient_name, qty_needed)
                    continue

                qty_needed = Decimal(str(dish_ing.quantity_required)) * qty_sold
                qty_needed = _convert_or_error(
                    qty_needed, dish_ing_unit, batch_unit, batches[0],
                    PIECE_UNITS, PACKET_UNITS,
                    label=f"'{dish.name}' → '{dish_ing.ingredient_name}'",
                    errors=warnings,
                )
                if qty_needed is None:
                    continue

                _accumulate(qty_needed_map, dish_ing.ingredient_id, sale_date_only,
                            batch_unit, dish_ing.ingredient_name, qty_needed)

            for dish_ing in semi_ingredients:
                errs = _accumulate_semi(
                    db, tenant_id, dish_ing, qty_sold, sale_date_only,
                    qty_needed_map, PIECE_UNITS, PACKET_UNITS,
                    label=f"'{dish.name}'",
                )
                warnings.extend(errs)

        # ── Phase 1: combos ───────────────────────────────────────────
        for sale_item in payload.combo_sales:
            combo    = combo_map[sale_item.combo_id]
            qty_sold = sale_item.qty_sold

            sale_dt = (
                sale_item.date
                or payload.sale_date
                or datetime.now(timezone.utc)
            )
            sale_date_only = sale_dt.date() if hasattr(sale_dt, "date") else date.today()

            combo_items = (
                db.query(ComboItem)
                .filter(
                    ComboItem.combo_id  == combo.id,
                    ComboItem.tenant_id == tenant_id,
                )
                .all()
            )

            if not combo_items:
                warnings.append(f"Combo '{combo.name}' has no items configured — skipped")
                continue

            combo_data_map[combo.id] = {
                "combo":          combo,
                "qty_sold":       qty_sold,
                "sale_dt":        sale_dt,
                "sale_date_only": sale_date_only,
                "combo_items":    combo_items,
            }

            for ci in combo_items:
                ci_qty = Decimal(str(ci.quantity or 1)) * qty_sold

                # ── combo item is a DISH ──────────────────────────────
                if ci.dish_id is not None:
                    dish = db.query(Dish).filter(
                        Dish.id        == ci.dish_id,
                        Dish.tenant_id == tenant_id,
                        Dish.is_active == True,
                    ).first()

                    if not dish:
                        warnings.append(
                            f"Combo '{combo.name}': dish id={ci.dish_id} not found — skipped"
                        )
                        continue

                    dish_ingredients = (
                        db.query(DishIngredient)
                        .filter(
                            DishIngredient.dish_id   == dish.id,
                            DishIngredient.tenant_id == tenant_id,
                        )
                        .all()
                    )

                    if not dish_ingredients:
                        warnings.append(
                            f"Combo '{combo.name}' → dish '{dish.name}' has no ingredients configured — skipped"
                        )
                        continue

                    for dish_ing in [i for i in dish_ingredients if i.semi_finished_id is None]:
                        if not dish_ing.ingredient_id:
                            warnings.append(
                                f"Combo '{combo.name}' → dish '{dish.name}': "
                                f"raw ingredient '{dish_ing.ingredient_name}' has no ingredient_id"
                            )
                            continue

                        batches = _get_valid_batches(db, tenant_id, dish_ing.ingredient_id, sale_date_only)
                        if not batches:
                            warnings.append(
                                f"Combo '{combo.name}' → dish '{dish.name}': "
                                f"no batch for '{dish_ing.ingredient_name}' on {sale_date_only} — skipped"
                            )
                            continue

                        batch_unit    = _normalize_unit(batches[0].unit)
                        dish_ing_unit = _normalize_unit(dish_ing.unit)

                        if dish_ing.fixed_cost_amount is not None:
                            batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
                            qty_recipe      = Decimal(str(dish_ing.quantity_required)) * ci_qty
                            qty_needed = (
                                Decimal(str(dish_ing.fixed_cost_amount)) / batch_unit_cost * qty_recipe
                                if batch_unit_cost > 0 else Decimal("0")
                            )
                            _accumulate(qty_needed_map, dish_ing.ingredient_id, sale_date_only,
                                        batch_unit, dish_ing.ingredient_name, qty_needed)
                            continue

                        qty_needed = Decimal(str(dish_ing.quantity_required)) * ci_qty
                        qty_needed = _convert_or_error(
                            qty_needed, dish_ing_unit, batch_unit, batches[0],
                            PIECE_UNITS, PACKET_UNITS,
                            label=f"Combo '{combo.name}' → dish '{dish.name}' → '{dish_ing.ingredient_name}'",
                            errors=warnings,
                        )
                        if qty_needed is None:
                            continue

                        _accumulate(qty_needed_map, dish_ing.ingredient_id, sale_date_only,
                                    batch_unit, dish_ing.ingredient_name, qty_needed)

                    for dish_ing in [i for i in dish_ingredients if i.semi_finished_id is not None]:
                        errs = _accumulate_semi(
                            db, tenant_id, dish_ing, ci_qty, sale_date_only,
                            qty_needed_map, PIECE_UNITS, PACKET_UNITS,
                            label=f"Combo '{combo.name}' → dish '{dish.name}'",
                        )
                        warnings.extend(errs)

                # ── combo item is a SEMI-FINISHED ─────────────────────
                elif ci.semi_finished_id is not None:
                    semi = db.query(SemiFinishedProduct).filter(
                        SemiFinishedProduct.id        == ci.semi_finished_id,
                        SemiFinishedProduct.tenant_id == tenant_id,
                        SemiFinishedProduct.is_active == True,
                    ).first()

                    if not semi:
                        warnings.append(
                            f"Combo '{combo.name}': semi-finished id={ci.semi_finished_id} not found — skipped"
                        )
                        continue

                    ci_unit         = _normalize_unit(ci.unit)
                    semi_yield_unit = _normalize_unit(semi.unit)
                    qty_sfp_needed  = ci_qty

                    if ci_unit != semi_yield_unit:
                        try:
                            qty_sfp_needed = Decimal(str(convert_quantity_unit(
                                value=qty_sfp_needed, from_unit=ci_unit, to_unit=semi_yield_unit,
                            )))
                        except ValueError:
                            warnings.append(
                                f"Combo '{combo.name}' → semi '{semi.name}': "
                                f"cannot convert '{ci_unit}' to '{semi_yield_unit}' — skipped"
                            )
                            continue

                    flat_ings = _resolve_semi_to_raw_ingredients(db, tenant_id, semi.id, qty_sfp_needed)
                    if not flat_ings:
                        warnings.append(
                            f"Combo '{combo.name}' → semi '{semi.name}' has no sub-ingredients — skipped"
                        )
                        continue

                    for sub_ing in flat_ings:
                        batches = _get_valid_batches(db, tenant_id, sub_ing["ingredient_id"], sale_date_only)
                        if not batches:
                            warnings.append(
                                f"Combo '{combo.name}' → semi '{semi.name}': "
                                f"no batch for '{sub_ing['ingredient_name']}' on {sale_date_only} — skipped"
                            )
                            continue

                        batch_unit   = _normalize_unit(batches[0].unit)
                        sub_ing_unit = _normalize_unit(sub_ing["unit"])
                        qty_needed   = sub_ing["quantity_required"]

                        if sub_ing["fixed_cost_amount"] is not None:
                            batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
                            qty_needed = (
                                Decimal(str(sub_ing["fixed_cost_amount"])) / batch_unit_cost * qty_needed
                                if batch_unit_cost > 0 else Decimal("0")
                            )
                            _accumulate(qty_needed_map, sub_ing["ingredient_id"], sale_date_only,
                                        batch_unit, sub_ing["ingredient_name"], qty_needed)
                            continue

                        qty_needed = _convert_or_error(
                            qty_needed, sub_ing_unit, batch_unit, batches[0],
                            PIECE_UNITS, PACKET_UNITS,
                            label=f"Combo '{combo.name}' → semi '{semi.name}' → '{sub_ing['ingredient_name']}'",
                            errors=warnings,
                        )
                        if qty_needed is None:
                            continue

                        _accumulate(qty_needed_map, sub_ing["ingredient_id"], sale_date_only,
                                    batch_unit, sub_ing["ingredient_name"], qty_needed)

                # ── combo item is a RAW INGREDIENT ────────────────────
                elif ci.ingredient_id is not None:
                    batches = _get_valid_batches(db, tenant_id, ci.ingredient_id, sale_date_only)
                    if not batches:
                        warnings.append(
                            f"Combo '{combo.name}': no batch for ingredient "
                            f"id={ci.ingredient_id} on {sale_date_only} — skipped"
                        )
                        continue

                    batch_unit = _normalize_unit(batches[0].unit)
                    ci_unit    = _normalize_unit(ci.unit)
                    qty_needed = _convert_or_error(
                        ci_qty, ci_unit, batch_unit, batches[0],
                        PIECE_UNITS, PACKET_UNITS,
                        label=f"Combo '{combo.name}' → ingredient '{ci.item_name}'",
                        errors=warnings,
                    )
                    if qty_needed is None:
                        continue

                    _accumulate(qty_needed_map, ci.ingredient_id, sale_date_only,
                                batch_unit, ci.item_name or f"ingredient-{ci.ingredient_id}", qty_needed)

                else:
                    # FIX: hard structural error — combo item has no reference at all
                    structural_errors.append(
                        f"Combo '{combo.name}': item id={ci.id} has no dish/semi/ingredient reference"
                    )

        # FIX: only hard structural errors block execution; soft warnings accumulate
        if structural_errors:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Validation failed. No sales recorded, no inventory deducted.",
                    "errors":  structural_errors,
                },
            )

        # ══════════════════════════════════════════════════════════════
        # PHASE 2 — CHECK STOCK
        # ══════════════════════════════════════════════════════════════

        stock_errors: list[str] = []

        for (inv_id, _sale_date), needed in qty_needed_map.items():
            check_date = needed["sale_date"]
            batches    = _get_valid_batches(db, tenant_id, inv_id, check_date)
            total_available = sum(Decimal(str(b.quantity_remaining)) for b in batches)

            if total_available < needed["qty"]:
                stock_errors.append(
                    f"Insufficient stock for '{needed['name']}' on {check_date}: "
                    f"need {float(needed['qty']):.4f} {needed['unit']}, "
                    f"available {float(total_available):.4f} {needed['unit']}"
                )

        # FIX: stock errors are soft warnings, not a hard abort
        warnings.extend(stock_errors)

        # ══════════════════════════════════════════════════════════════
        # PHASE 3 — RECORD SALES + DEDUCT INVENTORY
        # ══════════════════════════════════════════════════════════════

        sales_recorded             = []
        total_dishes_sold          = 0
        total_combos_sold          = 0
        total_inventory_deductions = 0
        affected_batch_ids         = set()  # FIX: track affected batches

        # ── Phase 3: dishes ───────────────────────────────────────────
        for sale_item in payload.sales:
            dish     = dish_map[sale_item.dish_id]
            data     = dish_data_map.get(dish.id)
            qty_sold = sale_item.qty_sold

            if not data:
                continue

            sale_dt          = data["sale_dt"]
            sale_date_only   = data["sale_date_only"]
            raw_ingredients  = data["raw_ingredients"]
            semi_ingredients = data["semi_ingredients"]
            total_dishes_sold += qty_sold

            sale = DishSale(
                tenant_id     = tenant_id,
                dish_id       = dish.id,
                quantity_sold = qty_sold,
                unit_price    = dish.selling_price,
                total_amount  = (
                    Decimal(str(dish.selling_price or 0)) * qty_sold
                    if dish.selling_price else None
                ),
                sale_date = sale_dt,
                combo_id  = None,
            )
            db.add(sale)
            db.flush()

            deduction_details = []

            for dish_ing in raw_ingredients:
                inventory = db.query(Inventory).filter(
                    Inventory.id        == dish_ing.ingredient_id,
                    Inventory.tenant_id == tenant_id,
                    Inventory.is_active == True,
                ).first()

                result = _deduct_ingredient_fifo(
                    db=db, tenant_id=tenant_id,
                    dish_ing=dish_ing,
                    total_qty_needed_recipe=Decimal(str(dish_ing.quantity_required)) * qty_sold,
                    inventory=inventory,
                    sale_date=sale_dt,
                )
                if result["success"]:
                    affected_batch_ids.update(result["batch_ids"])  # FIX
                    deduction_details.append({
                        "type":            "raw",
                        "ingredient_name": result["ingredient_name"],
                        "qty_deducted":    result["qty_deducted"],
                        "unit":            result["unit"],
                        "cost":            result["cost"],
                        "batches_used":    result["batches_used"],
                    })
                    total_inventory_deductions += 1
                else:
                    warnings.append(
                        f"'{dish.name}': {result['warning']} — unexpected failure after validation"
                    )

            for dish_ing in semi_ingredients:
                result = _deduct_semi_finished_fifo(
                    db=db, tenant_id=tenant_id,
                    dish_ing=dish_ing,
                    qty_sold=qty_sold,
                    sale_date=sale_dt,
                )
                if result["success"]:
                    affected_batch_ids.update(result["batch_ids"])  # FIX
                    deduction_details.append({
                        "type":               "semi_finished",
                        "ingredient_name":    result["ingredient_name"],
                        "semi_finished_name": result["semi_finished_name"],
                        "qty_used":           result["qty_used"],
                        "unit":               result["unit"],
                        "scale_factor":       result["scale_factor"],
                        "cost":               result["cost"],
                        "sub_ingredients":    result["sub_ingredients"],
                    })
                    total_inventory_deductions += len(result["sub_ingredients"])
                else:
                    warnings.append(
                        f"'{dish.name}': {result['warning']} — unexpected failure after validation"
                    )

            sale.cogs_amount = float(sum(Decimal(str(d.get("cost", 0))) for d in deduction_details))
            db.add(sale)

            sales_recorded.append({
                "type":               "dish",
                "dish_id":            dish.id,
                "dish_name":          dish.name,
                "qty_sold":           qty_sold,
                "sale_date":          sale_date_only.isoformat(),
                "combo_id":           None,
                "combo_name":         None,
                "sale_recorded":      True,
                "inventory_deducted": True,
                "deduction_details":  deduction_details,
            })

        # ── Phase 3: combos ───────────────────────────────────────────
        for sale_item in payload.combo_sales:
            combo    = combo_map[sale_item.combo_id]
            data     = combo_data_map.get(combo.id)
            qty_sold = sale_item.qty_sold

            if not data:
                continue

            sale_dt        = data["sale_dt"]
            sale_date_only = data["sale_date_only"]
            combo_items    = data["combo_items"]
            total_combos_sold += qty_sold

            combo_sale = DishSale(
                tenant_id     = tenant_id,
                dish_id       = None,
                combo_id      = combo.id,
                quantity_sold = qty_sold,
                unit_price    = combo.selling_price if hasattr(combo, "selling_price") else None,
                total_amount  = (
                    Decimal(str(combo.selling_price or 0)) * qty_sold
                    if hasattr(combo, "selling_price") and combo.selling_price else None
                ),
                sale_date   = sale_dt,
                cogs_amount = None,  # updated after all items processed
            )
            db.add(combo_sale)
            db.flush()

            combo_deduction_details = []

            for ci in combo_items:
                ci_qty = Decimal(str(ci.quantity or 1)) * qty_sold

                # ── combo item is a DISH ──────────────────────────────
                if ci.dish_id is not None:
                    dish = db.query(Dish).filter(
                        Dish.id        == ci.dish_id,
                        Dish.tenant_id == tenant_id,
                    ).first()
                    if not dish:
                        continue

                    dish_ingredients = (
                        db.query(DishIngredient)
                        .filter(
                            DishIngredient.dish_id   == dish.id,
                            DishIngredient.tenant_id == tenant_id,
                        )
                        .all()
                    )

                    # Per-dish sale row inside the combo (inventory tracking only;
                    # revenue lives on combo_sale)
                    dish_sale = DishSale(
                        tenant_id     = tenant_id,
                        dish_id       = dish.id,
                        combo_id      = combo.id,
                        quantity_sold = int(ci_qty),
                        unit_price    = dish.selling_price,
                        total_amount  = None,  # revenue at combo level
                        sale_date     = sale_dt,
                    )
                    db.add(dish_sale)
                    db.flush()

                    dish_deductions = []

                    for dish_ing in [i for i in dish_ingredients if i.semi_finished_id is None]:
                        inventory = db.query(Inventory).filter(
                            Inventory.id        == dish_ing.ingredient_id,
                            Inventory.tenant_id == tenant_id,
                            Inventory.is_active == True,
                        ).first()

                        result = _deduct_ingredient_fifo(
                            db=db, tenant_id=tenant_id,
                            dish_ing=dish_ing,
                            total_qty_needed_recipe=Decimal(str(dish_ing.quantity_required)) * ci_qty,
                            inventory=inventory,
                            sale_date=sale_dt,
                        )
                        if result["success"]:
                            affected_batch_ids.update(result["batch_ids"])  # FIX
                            dish_deductions.append({
                                "type":            "raw",
                                "dish_name":       dish.name,
                                "ingredient_name": result["ingredient_name"],
                                "qty_deducted":    result["qty_deducted"],
                                "unit":            result["unit"],
                                "cost":            result["cost"],
                                "batches_used":    result["batches_used"],
                            })
                            total_inventory_deductions += 1
                        else:
                            warnings.append(
                                f"Combo '{combo.name}' → dish '{dish.name}': "
                                f"{result['warning']} — unexpected failure after validation"
                            )

                    for dish_ing in [i for i in dish_ingredients if i.semi_finished_id is not None]:
                        result = _deduct_semi_finished_fifo(
                            db=db, tenant_id=tenant_id,
                            dish_ing=dish_ing,
                            qty_sold=ci_qty,
                            sale_date=sale_dt,
                        )
                        if result["success"]:
                            affected_batch_ids.update(result["batch_ids"])  # FIX
                            dish_deductions.append({
                                "type":               "semi_finished",
                                "dish_name":          dish.name,
                                "ingredient_name":    result["ingredient_name"],
                                "semi_finished_name": result["semi_finished_name"],
                                "qty_used":           result["qty_used"],
                                "unit":               result["unit"],
                                "scale_factor":       result["scale_factor"],
                                "cost":               result["cost"],
                                "sub_ingredients":    result["sub_ingredients"],
                            })
                            total_inventory_deductions += len(result["sub_ingredients"])
                        else:
                            warnings.append(
                                f"Combo '{combo.name}' → dish '{dish.name}': "
                                f"{result['warning']} — unexpected failure after validation"
                            )

                    # FIX: write actual deduction cost onto the per-dish sale row
                    dish_sale_cogs = float(
                        sum(Decimal(str(d.get("cost", 0))) for d in dish_deductions)
                    )
                    dish_sale.cogs_amount = dish_sale_cogs
                    db.add(dish_sale)

                    combo_deduction_details.append({
                        "item_type":  "dish",
                        "dish_id":    dish.id,
                        "dish_name":  dish.name,
                        "qty":        int(ci_qty),
                        "deductions": dish_deductions,
                        "cost":       dish_sale_cogs,
                    })

                # ── combo item is a SEMI-FINISHED ─────────────────────
                elif ci.semi_finished_id is not None:
                    class _SemiShim:
                        semi_finished_id  = ci.semi_finished_id
                        ingredient_name   = ci.item_name
                        unit              = ci.unit
                        quantity_required = ci.quantity
                        fixed_cost_amount = None
                        dish_id = None
                        id = None

                    result = _deduct_semi_finished_fifo(
                        db=db, tenant_id=tenant_id,
                        dish_ing=_SemiShim(),
                        qty_sold=qty_sold,
                        sale_date=sale_dt,
                    )
                    if result["success"]:
                        affected_batch_ids.update(result["batch_ids"])  # FIX
                        total_inventory_deductions += len(result["sub_ingredients"])
                        combo_deduction_details.append({
                            "item_type":       "semi_finished",
                            "item_name":       ci.item_name,
                            "qty":             float(ci_qty),
                            "cost":            result["cost"],
                            "sub_ingredients": result["sub_ingredients"],
                        })
                    else:
                        warnings.append(
                            f"Combo '{combo.name}' → semi '{ci.item_name}': "
                            f"{result['warning']} — unexpected failure after validation"
                        )

                # ── combo item is a RAW INGREDIENT ────────────────────
                elif ci.ingredient_id is not None:
                    inventory = db.query(Inventory).filter(
                        Inventory.id        == ci.ingredient_id,
                        Inventory.tenant_id == tenant_id,
                        Inventory.is_active == True,
                    ).first()

                    class _RawShim:
                        ingredient_id     = ci.ingredient_id
                        ingredient_name   = ci.item_name
                        unit              = ci.unit
                        quantity_required = ci.quantity
                        fixed_cost_amount = None
                        dish_id = None
                        id = None

                    result = _deduct_ingredient_fifo(
                        db=db, tenant_id=tenant_id,
                        dish_ing=_RawShim(),
                        total_qty_needed_recipe=Decimal(str(ci.quantity or 1)) * qty_sold,
                        inventory=inventory,
                        sale_date=sale_dt,
                    )
                    if result["success"]:
                        affected_batch_ids.update(result["batch_ids"])  # FIX
                        total_inventory_deductions += 1
                        combo_deduction_details.append({
                            "item_type":    "raw",
                            "item_name":    ci.item_name,
                            "qty_deducted": result["qty_deducted"],
                            "unit":         result["unit"],
                            "cost":         result["cost"],
                            "batches_used": result["batches_used"],
                        })
                    else:
                        warnings.append(
                            f"Combo '{combo.name}' → ingredient '{ci.item_name}': "
                            f"{result['warning']} — unexpected failure after validation"
                        )

            combo_sale.cogs_amount = float(
                sum(Decimal(str(d.get("cost", 0))) for d in combo_deduction_details)
            )
            db.add(combo_sale)

            sales_recorded.append({
                "type":               "combo",
                "combo_sale_id":      combo_sale.id,
                "dish_id":            None,
                "dish_name":          None,
                "qty_sold":           qty_sold,
                "sale_date":          sale_date_only.isoformat(),
                "combo_id":           combo.id,
                "combo_name":         combo.name,
                "sale_recorded":      True,
                "inventory_deducted": True,
                "deduction_details":  combo_deduction_details,
            })

        db.commit()

        return {
            "success":                    True,
            "total_dishes_sold":          total_dishes_sold,
            "total_combos_sold":          total_combos_sold,
            "total_inventory_deductions": total_inventory_deductions,
            "warnings":                   warnings,
            "sales":                      sales_recorded,
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"Database error during sale: {db_error}")
        raise HTTPException(status_code=500, detail="Database error during sale")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error during sale: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
@router.get("/sales-history", status_code=status.HTTP_200_OK)
def get_sales_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    search: Optional[str] = Query(None, description="Search by dish or combo name"),
    sale_type: Optional[str] = Query(None, description="Filter by type: 'dish' or 'combo'"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=100, description="Rows per page"),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # ── Top-level rows only ───────────────────────────────────────
        # Standalone dish : dish_id SET,  combo_id NULL
        # Combo header    : dish_id NULL, combo_id SET
        # Combo child     : dish_id SET,  combo_id SET  ← always excluded
        TOP_LEVEL = not_(
            and_(
                DishSale.dish_id  != None,
                DishSale.combo_id != None,
            )
        )

        query = (
            db.query(DishSale)
            .filter(
                DishSale.tenant_id == tenant_id,
                TOP_LEVEL,
            )
        )

        # ── Date filters ──────────────────────────────────────────────
        if date_from:
            query = query.filter(
                DishSale.sale_date >= datetime.combine(
                    date_from, datetime.min.time()
                ).replace(tzinfo=timezone.utc)
            )
        if date_to:
            query = query.filter(
                DishSale.sale_date <= datetime.combine(
                    date_to, datetime.max.time()
                ).replace(tzinfo=timezone.utc)
            )

        # ── Type filter ───────────────────────────────────────────────
        if sale_type == "dish":
            # Standalone dish rows only
            query = query.filter(
                DishSale.dish_id  != None,
                DishSale.combo_id == None,
            )
        elif sale_type == "combo":
            # Combo header rows only
            query = query.filter(
                DishSale.dish_id  == None,
                DishSale.combo_id != None,
            )

        # ── Search filter ─────────────────────────────────────────────
        if search:
            query = (
                query
                .outerjoin(Dish,  DishSale.dish_id  == Dish.id)
                .outerjoin(Combo, DishSale.combo_id == Combo.id)
                .filter(
                    or_(
                        Dish.name.ilike(f"%{search}%"),
                        Combo.name.ilike(f"%{search}%"),
                    )
                )
            )

        # ── Fetch top-level rows ──────────────────────────────────────
        all_sales = query.order_by(DishSale.sale_date.desc()).all()

        # ── Collect ids for batch lookups ─────────────────────────────
        all_dish_ids  = list({s.dish_id  for s in all_sales if s.dish_id})
        all_combo_ids = list({s.combo_id for s in all_sales if s.combo_id})

        # ── Batch load dishes ─────────────────────────────────────────
        dishes = (
            db.query(Dish)
            .options(joinedload(Dish.type))
            .filter(Dish.id.in_(all_dish_ids), Dish.tenant_id == tenant_id)
            .all()
        ) if all_dish_ids else []
        dish_map = {d.id: d for d in dishes}

        # ── Batch load combos ─────────────────────────────────────────
        combos = (
            db.query(Combo)
            .options(joinedload(Combo.type))
            .filter(Combo.id.in_(all_combo_ids), Combo.tenant_id == tenant_id)
            .all()
        ) if all_combo_ids else []
        combo_map = {c.id: c for c in combos}

        # ── Batch load combo items ────────────────────────────────────
        combo_items_all = (
            db.query(ComboItem)
            .filter(
                ComboItem.combo_id.in_(all_combo_ids),
                ComboItem.tenant_id == tenant_id,
            )
            .all()
        ) if all_combo_ids else []

        combo_items_map: dict[int, list] = defaultdict(list)
        for ci in combo_items_all:
            combo_items_map[ci.combo_id].append(ci)

        # ── Batch load dish ingredients ───────────────────────────────
        dish_ingredients_all = (
            db.query(DishIngredient)
            .filter(
                DishIngredient.dish_id.in_(all_dish_ids),
                DishIngredient.tenant_id == tenant_id,
            )
            .all()
        ) if all_dish_ids else []

        raw_map:  dict[int, list] = defaultdict(list)
        semi_map: dict[int, list] = defaultdict(list)
        for di in dish_ingredients_all:
            if di.semi_finished_id is not None:
                semi_map[di.dish_id].append(di)
            else:
                raw_map[di.dish_id].append(di)

        semi_finished_ids = list({
            di.semi_finished_id
            for dis in semi_map.values()
            for di in dis
            if di.semi_finished_id
        })

        semi_products = (
            db.query(SemiFinishedProduct)
            .filter(
                SemiFinishedProduct.id.in_(semi_finished_ids),
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            )
            .all()
        ) if semi_finished_ids else []
        semi_product_map = {s.id: s for s in semi_products}

        semi_ingredients_all = (
            db.query(SemiFinishedIngredient)
            .filter(
                SemiFinishedIngredient.semi_finished_id.in_(semi_finished_ids),
                SemiFinishedIngredient.tenant_id == tenant_id,
            )
            .all()
        ) if semi_finished_ids else []

        sub_ing_map: dict[int, list] = defaultdict(list)
        for sub in semi_ingredients_all:
            sub_ing_map[sub.semi_finished_id].append(sub)

        # ── Helper: ingredients used for a standalone dish ────────────
        def build_ingredients_used(dish, qty_sold: Decimal) -> list:
            if not dish:
                return []
            ingredients_used = []

            for di in raw_map.get(dish.id, []):
                total_consumed = Decimal(str(di.quantity_required)) * qty_sold
                ingredients_used.append({
                    "type":              "raw",
                    "ingredient_name":   di.ingredient_name,
                    "quantity_consumed": float(total_consumed),
                    "unit":              di.unit,
                })

            for di in semi_map.get(dish.id, []):
                semi = semi_product_map.get(di.semi_finished_id)
                if not semi:
                    continue

                dish_sfp_unit   = _normalize_unit(di.unit)
                semi_yield_unit = _normalize_unit(semi.unit)
                qty_sfp_needed  = Decimal(str(di.quantity_required)) * qty_sold

                if dish_sfp_unit != semi_yield_unit:
                    try:
                        qty_sfp_needed = Decimal(str(convert_quantity_unit(
                            value=qty_sfp_needed,
                            from_unit=dish_sfp_unit,
                            to_unit=semi_yield_unit,
                        )))
                    except ValueError:
                        qty_sfp_needed = Decimal(str(di.quantity_required)) * qty_sold

                scale_factor = qty_sfp_needed / Decimal(str(semi.yield_quantity))

                sub_ingredients_entry = []
                for sub_ing in sub_ing_map.get(semi.id, []):
                    total_consumed = Decimal(str(sub_ing.quantity_required)) * scale_factor
                    sub_ingredients_entry.append({
                        "sub_ingredient_name": sub_ing.ingredient_name,
                        "quantity_consumed":   float(total_consumed),
                        "unit":                sub_ing.unit,
                    })

                ingredients_used.append({
                    "type":               "semi_finished",
                    "ingredient_name":    di.ingredient_name,
                    "semi_finished_name": semi.name,
                    "qty_used":           float(qty_sfp_needed),
                    "unit":               semi_yield_unit,
                    "scale_factor":       float(scale_factor),
                    "sub_ingredients":    sub_ingredients_entry,
                })

            return ingredients_used

        # ── Helper: build combo items list ────────────────────────────
        def build_combo_items(combo_id: int) -> list:
            items = []
            for ci in combo_items_map.get(combo_id, []):
                item = {
                    "item_name":     ci.item_name,
                    "quantity":      float(ci.quantity or 1),
                    "unit":          ci.unit,
                    "cost_per_unit": float(ci.cost_per_unit) if ci.cost_per_unit else None,
                }
                if ci.dish_id is not None:
                    item["type"]    = "dish"
                    item["dish_id"] = ci.dish_id
                elif ci.semi_finished_id is not None:
                    item["type"]             = "semi_finished"
                    item["semi_finished_id"] = ci.semi_finished_id
                elif ci.ingredient_id is not None:
                    item["type"]          = "ingredient"
                    item["ingredient_id"] = ci.ingredient_id
                else:
                    item["type"] = "unknown"
                items.append(item)
            return items

        # ── Build result — no grouping needed anymore ─────────────────
        # Each top-level row IS one logical order entry.
        result = []

        for sale in all_sales:
            is_combo = sale.dish_id is None and sale.combo_id is not None

            if is_combo:
                combo = combo_map.get(sale.combo_id)
                result.append({
                    "type":          "combo",
                    "sale_id":       str(sale.id),
                    "combo_id":      sale.combo_id,
                    "combo_name":    combo.name if combo else None,
                    "category":      combo.type.name if combo and combo.type else None,
                    "selling_price": float(combo.selling_price) if combo and combo.selling_price else None,
                    # ← quantity now comes directly from the header row
                    "quantity":      sale.quantity_sold,
                    "total_amount":  float(sale.total_amount) if sale.total_amount else None,
                    # ← cogs now included, was missing entirely before
                    "cogs":          float(sale.cogs_amount) if sale.cogs_amount is not None else None,
                    "date":          sale.sale_date.strftime("%d-%m-%Y") if sale.sale_date else None,
                    "combo_items":   build_combo_items(sale.combo_id),
                })

            else:
                # Standalone dish row
                dish     = dish_map.get(sale.dish_id)
                qty_sold = Decimal(str(sale.quantity_sold))
                result.append({
                    "type":             "dish",
                    "sale_id":          str(sale.id),
                    "dish_name":        dish.name if dish else None,
                    "category":         dish.type.name if dish and dish.type else None,
                    "price":            float(sale.unit_price) if sale.unit_price else None,
                    "quantity":         sale.quantity_sold,
                    "cogs":             float(sale.cogs_amount) if sale.cogs_amount is not None else None,
                    "date":             sale.sale_date.strftime("%d-%m-%Y") if sale.sale_date else None,
                    "combo_id":         None,
                    "combo_name":       None,
                    "ingredients_used": build_ingredients_used(dish, qty_sold),
                })

        # ── Paginate after building result ────────────────────────────
        total            = len(result)
        start            = (page - 1) * page_size
        paginated_result = result[start : start + page_size]

        return {
            "success": True,
            "meta": {
                "total":       total,
                "page":        page,
                "page_size":   page_size,
                "total_pages": ceil(total / page_size) if total else 1,
                "search":      search,
                "sale_type":   sale_type,
            },
            "total_count": len(paginated_result),
            "sales":       paginated_result,
        }

    except SQLAlchemyError as db_error:
        logger.exception(f"Database error fetching sales history: {db_error}")
        raise HTTPException(
            status_code=500,
            detail="Database error fetching sales history",
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"Unexpected error fetching sales history: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
@router.get("/sales-dashboard", status_code=status.HTTP_200_OK)
def get_sales_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    filter_type: str = Query("daily", regex="^(daily|weekly|monthly|custom)$"),
    date: Optional[date] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # ── Validate & resolve date ───────────────────────────────────
        today = datetime.now(timezone.utc).date()
        MIN_DATE = today.replace(year=today.year - 10)

        if filter_type in ("daily", "weekly", "monthly"):
            if date is not None:
                if date > today:
                    raise HTTPException(
                        status_code=400,
                        detail=f"'date' cannot be in the future (got {date})"
                    )
                if date < MIN_DATE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"'date' is too far in the past (minimum allowed: {MIN_DATE})"
                    )
            today = date or today

        # ── Build start_dt / end_dt ───────────────────────────────────
        if filter_type == "daily":
            start_dt = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt   = datetime.combine(today, datetime.max.time()).replace(tzinfo=timezone.utc)

        elif filter_type == "weekly":
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week   = start_of_week + timedelta(days=6)
            start_dt = datetime.combine(start_of_week, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt   = datetime.combine(end_of_week,   datetime.max.time()).replace(tzinfo=timezone.utc)

        elif filter_type == "monthly":
            start_of_month = today.replace(day=1)
            if today.month == 12:
                end_of_month = today.replace(day=31)
            else:
                end_of_month = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
            start_dt = datetime.combine(start_of_month, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt   = datetime.combine(end_of_month,   datetime.max.time()).replace(tzinfo=timezone.utc)

        elif filter_type == "custom":
            if not start_date and not end_date:
                raise HTTPException(
                    status_code=400,
                    detail="'start_date' and 'end_date' are required for custom filter"
                )
            if not start_date:
                raise HTTPException(
                    status_code=400,
                    detail="'start_date' is required for custom filter"
                )
            if not end_date:
                raise HTTPException(
                    status_code=400,
                    detail="'end_date' is required for custom filter"
                )
            if start_date > end_date:
                raise HTTPException(
                    status_code=400,
                    detail=f"'start_date' ({start_date}) must not be after 'end_date' ({end_date})"
                )
            MAX_RANGE_DAYS = 366
            if (end_date - start_date).days > MAX_RANGE_DAYS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Custom date range cannot exceed {MAX_RANGE_DAYS} days"
                )
            if end_date > today:
                raise HTTPException(
                    status_code=400,
                    detail=f"'end_date' cannot be in the future (got {end_date})"
                )
            if start_date < MIN_DATE:
                raise HTTPException(
                    status_code=400,
                    detail=f"'start_date' is too far in the past (minimum allowed: {MIN_DATE})"
                )
            start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_dt   = datetime.combine(end_date,   datetime.max.time()).replace(tzinfo=timezone.utc)

        if filter_type != "custom" and (start_date or end_date):
            logger.warning(
                f"'start_date'/'end_date' provided but filter_type is '{filter_type}' — ignoring them"
            )

        # ── Fetch ONLY top-level sale rows in range ───────────────────
        #
        # Row classification in DishSale:
        #   Standalone dish  → dish_id SET,  combo_id NULL   (top-level ✓)
        #   Combo header     → dish_id NULL, combo_id SET    (top-level ✓)
        #   Combo child dish → dish_id SET,  combo_id SET    (child — exclude ✗)
        #
        # Excluding child rows prevents double-counting orders and COGS.
        # Revenue is safe either way (child rows have total_amount=None)
        # but being explicit here makes every aggregate correct by default.

        all_sales = (
            db.query(DishSale)
            .filter(
                DishSale.tenant_id == tenant_id,
                DishSale.sale_date >= start_dt,
                DishSale.sale_date <= end_dt,
            )
            .all()
        )

        # Partition into top-level vs child rows once; reuse everywhere
        top_level_sales = [
            s for s in all_sales
            if not (s.dish_id is not None and s.combo_id is not None)
        ]
        # (kept separate in case you ever need child rows for breakdown queries)

        # ── Total orders ──────────────────────────────────────────────
        # Count distinct logical orders, not DB rows.
        # Each top-level row represents one logical order line.
        total_orders = sum(s.quantity_sold for s in top_level_sales)

        # ── Total revenue ─────────────────────────────────────────────
        # total_amount is set only on top-level rows (combo children have
        # total_amount=None intentionally), so filtering top_level_sales
        # makes this both correct and explicit.
        total_revenue = sum(
            Decimal(str(s.total_amount))
            for s in top_level_sales
            if s.total_amount is not None
        )

        # ── COGS ──────────────────────────────────────────────────────
        #
        # Row types and where COGS lives:
        #
        #   Standalone dish  (dish_id SET,  combo_id NULL):
        #       cogs_amount holds the full COGS for that dish sale.
        #
        #   Combo header     (dish_id NULL, combo_id SET):
        #       cogs_amount holds the rolled-up COGS across all combo items.
        #       This is the single source of truth for combo COGS.
        #
        # For legacy rows where cogs_amount is NULL (recorded before the
        # snapshot was added), fall back to DishIngredient-based derivation
        # for standalone dish rows only — combo legacy rows are skipped
        # as there's no safe way to reconstruct them without re-running
        # the deduction logic.

        # Rows with a stored COGS snapshot (both standalone dishes + combo headers)
        rows_with_cogs = [
            s for s in top_level_sales
            if s.cogs_amount is not None
        ]

        # Legacy standalone dish rows only (combo headers without cogs_amount
        # cannot be reconstructed safely)
        legacy_dish_rows = [
            s for s in top_level_sales
            if s.dish_id is not None
            and s.combo_id is None
            and s.cogs_amount is None
        ]

        total_cogs = sum(Decimal(str(s.cogs_amount)) for s in rows_with_cogs)

        if legacy_dish_rows:
            legacy_dish_ids = {s.dish_id for s in legacy_dish_rows}

            dish_ingredients = (
                db.query(DishIngredient)
                .filter(DishIngredient.dish_id.in_(legacy_dish_ids))
                .all()
            )

            raw_map: dict[int, list] = {}
            for di in dish_ingredients:
                raw_map.setdefault(di.dish_id, []).append(di)

            for sale in legacy_dish_rows:
                qty_sold = Decimal(str(sale.quantity_sold))
                for di in raw_map.get(sale.dish_id, []):
                    cost_per_unit     = Decimal(str(di.cost_per_unit or 0))
                    quantity_required = Decimal(str(di.quantity_required or 0))
                    total_cogs       += cost_per_unit * quantity_required * qty_sold

        # ── Profit ────────────────────────────────────────────────────
        profit = total_revenue - total_cogs

        # ── Wastage ───────────────────────────────────────────────────
        wastage_records = (
            db.query(Wastage)
            .filter(
                and_(
                    Wastage.tenant_id == tenant_id,
                    Wastage.wastage_date >= start_dt,
                    Wastage.wastage_date <= end_dt,
                    Wastage.wastage_type == WastageType.DISH,
                )
            )
            .all()
        )
        total_wastage_cost = sum(
            Decimal(str(w.cost_value or 0)) for w in wastage_records
        )

        net_profit = profit - total_wastage_cost

        # ── Response ──────────────────────────────────────────────────
        return {
            "success":     True,
            "filter_type": filter_type,
            "date_range": {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to":   end_dt.strftime("%d-%m-%Y"),
            },
            "total_orders":       total_orders,
            "total_revenue":      float(total_revenue),
            "total_cogs":         float(total_cogs),
            "profit":             float(profit),
            "total_wastage_cost": float(total_wastage_cost),
            "net_profit":         float(net_profit),
        }

    except HTTPException:
        raise

    except SQLAlchemyError as db_error:
        logger.exception(f"Database error fetching sales dashboard: {db_error}")
        raise HTTPException(
            status_code=500,
            detail="Database error fetching sales dashboard",
        )

    except Exception as e:
        logger.exception(f"Unexpected error fetching sales dashboard: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
 
class PeriodFilter(str, PyEnum):
    daily   = "daily"
    weekly  = "weekly"
    monthly = "monthly"
    custom  = "custom"

# ── helper (shared date resolver — same pattern as your existing code) ────────

def _resolve_report_date_range(
    period    : str,
    start_date: Optional[date],
    end_date  : Optional[date],
) -> tuple[datetime, datetime]:
    today = datetime.utcnow().date()  #  use utcnow().date() not timezone.utc

    if period == "daily":
        s = datetime.combine(today, datetime.min.time())   #  naive datetime
        e = datetime.combine(today, datetime.max.time())

    elif period == "weekly":
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        s = datetime.combine(monday, datetime.min.time())
        e = datetime.combine(sunday, datetime.max.time())

    elif period == "monthly":
        first = today.replace(day=1)
        if today.month == 12:
            last = today.replace(day=31)
        else:
            last = (today.replace(month=today.month + 1, day=1) - timedelta(days=1))
        s = datetime.combine(first, datetime.min.time())
        e = datetime.combine(last, datetime.max.time())

    else:  # custom
        if not start_date or not end_date:
            raise ValueError("start_date and end_date are required for period=custom")
        if start_date > end_date:
            raise ValueError("start_date must be <= end_date")
        s = datetime.combine(start_date, datetime.min.time())
        e = datetime.combine(end_date, datetime.max.time())

    return s, e

@router.get("/reports/order-volume-trends", status_code=status.HTTP_200_OK)
def get_order_volume_trends(
    period    : str           = Query("daily", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    db        : Session       = Depends(get_db),
    current_user: User        = Depends(get_current_user),
):
    """
    Returns order count + revenue grouped by day.
    - daily   → hourly breakdown for today
    - weekly  → one entry per day (Mon–Sun)
    - monthly → one entry per day of the month
    - custom  → one entry per day in range
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_report_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        sales = (
            db.query(DishSale)
            .filter(
                and_(
                    DishSale.tenant_id == current_user.tenant_id,
                    DishSale.sale_date >= start_dt,
                    DishSale.sale_date <= end_dt,
                )
            )
            .all()
        )

        # Group by day (or hour for daily view)
        from collections import defaultdict
        buckets: dict = defaultdict(lambda: {"order_count": 0, "revenue": 0.0})

        for sale in sales:
            if not sale.sale_date:
                continue

            # Skip combo CHILD rows (both dish_id and combo_id set). Their
            # quantity/revenue is already represented on the combo header row
            # (combo_id set, dish_id NULL) — counting both double-counts every
            # combo sale, inflating order_count and revenue per bucket.
            if sale.dish_id is not None and sale.combo_id is not None:
                continue

            if period == "daily":
                key = sale.sale_date.strftime("%H:00")   # "09:00", "14:00" etc.
            else:
                key = sale.sale_date.strftime("%a")      # "Mon", "Tue" etc. for weekly
                if period in ("monthly", "custom"):
                    key = sale.sale_date.strftime("%d %b") # "06 Mar"

            buckets[key]["order_count"] += sale.quantity_sold
            buckets[key]["revenue"]     += float(sale.total_amount or 0)

        # Build ordered list
        if period == "daily":
            # All 24 hours, fill missing with 0
            all_keys = [f"{h:02d}:00" for h in range(24)]
        elif period == "weekly":
            all_keys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        else:
            # Generate all days in range
            delta = (end_dt.date() - start_dt.date()).days + 1
            all_keys = [
                (start_dt + timedelta(days=i)).strftime("%d %b")
                for i in range(delta)
            ]

        trends = [
            {
                "label"      : key,
                "order_count": buckets[key]["order_count"],
                "revenue"    : round(buckets[key]["revenue"], 2),
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
        logger.exception(f"Error fetching order volume trends: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch order volume trends")
    
@router.get("/reports/sales-by-category", status_code=status.HTTP_200_OK)
def get_sales_by_category(
    period    : str            = Query("daily", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    db        : Session        = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    Returns revenue and order count grouped by dish/combo category.
    Percentages are calculated automatically.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_report_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # Pull both standalone dish rows AND combo header rows.
        # Combo CHILD rows (dish_id + combo_id both set) are fetched too,
        # but explicitly skipped below to avoid double-counting revenue
        # that already lives on the combo header row.
        sales = (
            db.query(DishSale)
            .filter(
                and_(
                    DishSale.tenant_id == current_user.tenant_id,
                    DishSale.sale_date >= start_dt,
                    DishSale.sale_date <= end_dt,
                    or_(
                        DishSale.dish_id.isnot(None),
                        DishSale.combo_id.isnot(None),
                    ),
                )
            )
            .all()
        )

        # Fetch all dishes with category (type) in one query
        dish_ids = list({s.dish_id for s in sales if s.dish_id is not None})
        dishes = (
            db.query(Dish)
            .options(joinedload(Dish.type))
            .filter(
                Dish.id.in_(dish_ids),
                Dish.tenant_id == current_user.tenant_id,
            )
            .all()
            if dish_ids else []
        )
        dish_map = {d.id: d for d in dishes}

        # Fetch all combos with category (type) in one query
        combo_ids = list({s.combo_id for s in sales if s.combo_id is not None})
        combos = (
            db.query(Combo)
            .options(joinedload(Combo.type))
            .filter(
                Combo.id.in_(combo_ids),
                Combo.tenant_id == current_user.tenant_id,
            )
            .all()
            if combo_ids else []
        )
        combo_map = {c.id: c for c in combos}

        # Group by category
        category_buckets: dict = defaultdict(lambda: {"revenue": Decimal(0), "order_count": 0})

        for sale in sales:
            # Skip combo CHILD rows (both dish_id and combo_id set) —
            # their revenue is already represented on the combo header row.
            if sale.dish_id is not None and sale.combo_id is not None:
                continue

            if sale.combo_id is not None:
                combo = combo_map.get(sale.combo_id)
                category = combo.type.name if combo and combo.type else "Uncategorized Combo"
            else:
                dish = dish_map.get(sale.dish_id)
                category = dish.type.name if dish and dish.type else "Uncategorized"

            category_buckets[category]["revenue"]     += Decimal(str(sale.total_amount or 0))
            category_buckets[category]["order_count"] += sale.quantity_sold or 0

        total_revenue = sum(v["revenue"] for v in category_buckets.values()) or Decimal(1)

        categories = [
            {
                "category"   : cat,
                "revenue"    : float(round(data["revenue"], 2)),
                "order_count": data["order_count"],
                "percentage" : float(round((data["revenue"] / total_revenue) * 100, 1)),
            }
            for cat, data in sorted(
                category_buckets.items(),
                key=lambda x: x[1]["revenue"],
                reverse=True,
            )
        ]

        return {
            "success"   : True,
            "period"    : period,
            "date_range": {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to"  : end_dt.strftime("%d-%m-%Y"),
            },
            "total_revenue": float(round(total_revenue, 2)),
            "categories"   : categories,
        }

    except Exception as e:
        logger.exception(f"Error fetching sales by category: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sales by category")

@router.get("/reports/top-dishes", status_code=status.HTTP_200_OK)
def get_top_dishes(
    period    : str            = Query("daily", regex="^(daily|weekly|monthly|custom)$"),
    start_date: Optional[date] = Query(None),
    end_date  : Optional[date] = Query(None),
    limit     : int            = Query(10, ge=1, le=50),
    db        : Session        = Depends(get_db),
    current_user: User         = Depends(get_current_user),
):
    """
    Returns top N dishes/combos ranked by revenue.
    Each item shows units sold, revenue, and rank.
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")

    try:
        start_dt, end_dt = _resolve_report_date_range(period, start_date, end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # --- Standalone dish sales (exclude combo child rows) ---
        # A combo child row has BOTH dish_id and combo_id set — its revenue
        # already lives on the combo header row, so it must be excluded here
        # or that revenue gets double-counted as a "dish" sale too.
        dish_rows = (
            db.query(
                DishSale.dish_id,
                func.sum(DishSale.quantity_sold).label("total_units_sold"),
                func.sum(DishSale.total_amount).label("total_revenue"),
            )
            .filter(
                and_(
                    DishSale.tenant_id == current_user.tenant_id,
                    DishSale.sale_date >= start_dt,
                    DishSale.sale_date <= end_dt,
                    DishSale.dish_id.isnot(None),
                    DishSale.combo_id.is_(None),
                )
            )
            .group_by(DishSale.dish_id)
            .all()
        )

        # --- Combo sales (header rows only — combo_id set, dish_id NULL) ---
        combo_rows = (
            db.query(
                DishSale.combo_id,
                func.sum(DishSale.quantity_sold).label("total_units_sold"),
                func.sum(DishSale.total_amount).label("total_revenue"),
            )
            .filter(
                and_(
                    DishSale.tenant_id == current_user.tenant_id,
                    DishSale.sale_date >= start_dt,
                    DishSale.sale_date <= end_dt,
                    DishSale.combo_id.isnot(None),
                )
            )
            .group_by(DishSale.combo_id)
            .all()
        )

        # Fetch dish details in one query
        dish_ids = [r.dish_id for r in dish_rows]
        dishes = (
            db.query(Dish)
            .options(joinedload(Dish.type))
            .filter(
                Dish.id.in_(dish_ids),
                Dish.tenant_id == current_user.tenant_id,
            )
            .all()
            if dish_ids else []
        )
        dish_map = {d.id: d for d in dishes}

        # Fetch combo details in one query
        combo_ids = [r.combo_id for r in combo_rows]
        combos = (
            db.query(Combo)
            .options(joinedload(Combo.type))
            .filter(
                Combo.id.in_(combo_ids),
                Combo.tenant_id == current_user.tenant_id,
            )
            .all()
            if combo_ids else []
        )
        combo_map = {c.id: c for c in combos}

        # Merge both into a single list of items, tagged by type
        merged_items = []

        for row in dish_rows:
            dish = dish_map.get(row.dish_id)
            merged_items.append({
                "item_type"     : "dish",
                "item_id"       : row.dish_id,
                "name"          : dish.name if dish else "Unknown",
                "category"      : dish.type.name if dish and dish.type else "Uncategorized",
                "units_sold"    : int(row.total_units_sold or 0),
                "total_revenue" : Decimal(str(row.total_revenue or 0)),
            })

        for row in combo_rows:
            combo = combo_map.get(row.combo_id)
            merged_items.append({
                "item_type"     : "combo",
                "item_id"       : row.combo_id,
                "name"          : combo.name if combo else "Unknown",
                "category"      : combo.type.name if combo and combo.type else "Uncategorized Combo",
                "units_sold"    : int(row.total_units_sold or 0),
                "total_revenue" : Decimal(str(row.total_revenue or 0)),
            })

        # Re-rank the merged list by revenue, then slice to limit
        merged_items.sort(key=lambda x: x["total_revenue"], reverse=True)
        merged_items = merged_items[:limit]

        top_dishes = []
        for rank, item in enumerate(merged_items, start=1):
            top_dishes.append({
                "rank"          : rank,
                "item_type"     : item["item_type"],
                "item_id"       : item["item_id"],
                "dish_name"     : item["name"],
                "category"      : item["category"],
                "units_sold"    : item["units_sold"],
                "total_revenue" : float(round(item["total_revenue"], 2)),
            })

        return {
            "success"   : True,
            "period"    : period,
            "date_range": {
                "from": start_dt.strftime("%d-%m-%Y"),
                "to"  : end_dt.strftime("%d-%m-%Y"),
            },
            "top_dishes": top_dishes,
        }

    except Exception as e:
        logger.exception(f"Error fetching top dishes: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch top dishes")