"""
app/api/v1/endpoints/dishes.py
Dish management endpoints
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, logger,status
from fastapi.responses import JSONResponse
import openpyxl
import pandas as pd
from sqlalchemy import and_, extract, func, or_,text
from sqlalchemy.orm import Session,joinedload
from typing import List, Optional
import logging

from app.api.deps import get_db
from app.models.dish import Combo, ComboItem, Dish, DishSale,DishType, DishIngredient, DishPreparationBatch , PrePreparedMaterial, PreparationBatchStatus,PreparationIngredientHistory,PrePreparedMaterialStock,IngredientForPrePreparedIngredients,DishPreparationBatchLog, SemiFinishedIngredient, SemiFinishedProduct
from app.models.inventory import Inventory, InventoryBatch, UnitType
from app.models.users import User
from app.schemas.dish import ComboCreate, ComboUpdate, CreateDishWithIngredientsRequest, CreateSemiFinishedRequest,DishCreate, DishIngredientOut,DishIngredientResponse, DishIngredientType, DishOut, DishTypeCreate, DishTypeOut,DishTypeUpdate,DishUpdate,AddDishIngredient,PreparationResult, ProduceSemiFinished,SemiFinishedProductCreate, SemiFinishedProductUpdate, SingleDishPreparation, UpdateDishWithIngredientsRequest, UpdateSemiFinishedRequest
from app.services.dish_service import DishIngredientService, DishPreparationService, SemiFinishedService
from app.utils.auth_helper import get_current_user
from app.utils.common_unit_converter import _normalize_unit, convert_quantity_unit
from app.utils.inventory_batch_helper import calc_weighted_avg_cost, sync_inventory_totals
from app.utils.response_helper import handle_db_exception
from uuid import UUID
from sqlalchemy.exc import SQLAlchemyError
from collections import defaultdict

logger = logging.getLogger(__name__)
router = APIRouter()

import math

def _resolve_item(
    db: Session,
    tenant_id: int,
    dish_id, semi_finished_id, ingredient_id,
    user_unit: str | None = None,
) -> dict:

    # ── DISH ─────────────────────────────────────────────────────────────────
    if dish_id is not None:
        obj = db.query(Dish).filter(
            Dish.id == dish_id,
            Dish.tenant_id == tenant_id,
            Dish.is_active == True,
        ).options(joinedload(Dish.dish_ingredient)).first()

        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": f"Dish {dish_id} not found."},
            )

        # ── fetch batches for all raw ingredients in this dish ────────────────
        raw_ingredient_ids = [
            ing.ingredient_id
            for ing in obj.dish_ingredient
            if ing.ingredient_id is not None
        ]

        batches_by_ingredient = defaultdict(list)
        inventory_batch_map   = {}

        if raw_ingredient_ids:
            all_batches = db.query(InventoryBatch).filter(
                InventoryBatch.inventory_item_id.in_(raw_ingredient_ids),
                InventoryBatch.tenant_id == tenant_id,
                InventoryBatch.quantity_remaining > 0,
            ).all()

            for batch in all_batches:
                batches_by_ingredient[batch.inventory_item_id].append(batch)

            inventories = db.query(Inventory).filter(
                Inventory.id.in_(raw_ingredient_ids),
                Inventory.tenant_id == tenant_id,
            ).all()

            inventory_unit_map = {
                inv.id: (inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit))
                for inv in inventories
            }

            for ingredient_id_key, batches in batches_by_ingredient.items():
                item_unit      = inventory_unit_map.get(ingredient_id_key, "gm")
                total_qty      = Decimal("0")
                total_cost     = Decimal("0")

                for batch in batches:
                    batch_unit     = batch.unit.value if hasattr(batch.unit, "value") else str(batch.unit)
                    qty_remaining  = Decimal(str(batch.quantity_remaining or 0))
                    qty_received   = Decimal(str(batch.quantity_received  or 0))
                    batch_cost     = Decimal(str(batch.total_cost         or 0))

                    remaining_cost = (qty_remaining / qty_received * batch_cost) if qty_received > 0 else Decimal("0")

                    try:
                        qty_converted = convert_quantity_unit(qty_remaining, batch_unit, item_unit)
                    except ValueError:
                        qty_converted = qty_remaining

                    total_qty  += qty_converted
                    total_cost += remaining_cost

                inventory_batch_map[ingredient_id_key] = {
                    "item_unit":              item_unit,
                    "avg_cost_per_item_unit": total_cost / total_qty if total_qty > 0 else Decimal("0"),
                }

        # ── fetch semi-finished costs used in this dish ───────────────────────
        semi_finished_ids = list({
            ing.semi_finished_id
            for ing in obj.dish_ingredient
            if ing.semi_finished_id is not None
        })

        semi_finished_cost_map = {}
        semi_finished_unit_map = {}

        if semi_finished_ids:
            sfps = db.query(SemiFinishedProduct).filter(
                SemiFinishedProduct.id.in_(semi_finished_ids),
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            ).all()
            for sfp in sfps:
                sfp_unit = (sfp.unit.value if hasattr(sfp.unit, "value") else str(sfp.unit or "")).lower().strip()
                semi_finished_cost_map[sfp.id] = Decimal(str(sfp.unit_cost or 0))
                semi_finished_unit_map[sfp.id] = sfp_unit

        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        # ── calc each ingredient line cost (mirrors your dish GET api exactly) ─
        def calc_ing_cost(ing) -> Decimal:
            if ing.fixed_cost_amount is not None:
                return Decimal(str(ing.fixed_cost_amount))

            qty       = Decimal(str(ing.quantity_required or 0))
            dish_unit = str(ing.unit or "").lower().strip()

            # semi-finished
            if ing.semi_finished_id is not None:
                live_cpu = semi_finished_cost_map.get(ing.semi_finished_id, Decimal("0"))
                sfp_unit = semi_finished_unit_map.get(ing.semi_finished_id, "")
                if not sfp_unit or not dish_unit or sfp_unit == dish_unit:
                    cost_per_unit = live_cpu
                else:
                    try:
                        factor        = convert_quantity_unit(Decimal("1"), dish_unit, sfp_unit)
                        cost_per_unit = live_cpu * factor
                    except (ValueError, ZeroDivisionError):
                        cost_per_unit = live_cpu
                return cost_per_unit * qty

            # no inventory link
            if ing.ingredient_id is None:
                return Decimal(str(ing.cost_per_unit or 0)) * qty

            batch_info = inventory_batch_map.get(ing.ingredient_id)
            item_unit  = (batch_info["item_unit"] if batch_info else "").lower().strip()

            # pcs vs packet
            if dish_unit in PIECE_UNITS and item_unit in PACKET_UNITS:
                batches      = batches_by_ingredient.get(ing.ingredient_id, [])
                total_pieces = Decimal("0")
                total_cost   = Decimal("0")
                for b in batches:
                    qty_rem           = Decimal(str(b.quantity_remaining or 0))
                    qty_rec           = Decimal(str(b.quantity_received  or 0))
                    b_cost            = Decimal(str(b.total_cost         or 0))
                    pieces_per_packet = Decimal(str(b.pieces             or 1))
                    remaining_cost    = (qty_rem / qty_rec * b_cost) if qty_rec > 0 else Decimal("0")
                    total_pieces     += qty_rem * pieces_per_packet
                    total_cost       += remaining_cost
                if total_pieces > 0:
                    return (total_cost / total_pieces) * qty

            # standard unit conversion
            if batch_info and batch_info["avg_cost_per_item_unit"] > 0:
                try:
                    factor = convert_quantity_unit(Decimal("1"), dish_unit, item_unit)
                    return batch_info["avg_cost_per_item_unit"] * factor * qty
                except ValueError:
                    pass

            # fallback: stored cost
            return Decimal(str(ing.cost_per_unit or 0)) * qty

        # sum all ingredient line costs = real production cost per dish
        production_cost = sum(calc_ing_cost(ing) for ing in obj.dish_ingredient)

        return {
            "dish_id":       dish_id,
            "item_name":     obj.name,
            "unit":          "piece",
            "cost_per_unit": round(float(production_cost), 4),
        }

    # ── SEMI-FINISHED ─────────────────────────────────────────────────────────
    if semi_finished_id is not None:
        obj = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.id == semi_finished_id,
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).first()
        if not obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error_code": "NOT_FOUND", "message": f"Semi-finished {semi_finished_id} not found."},
            )

        base_unit  = (obj.unit.value if hasattr(obj.unit, "value") else str(obj.unit or "gm")).lower().strip()
        input_unit = (user_unit or base_unit).lower().strip()

        cost_per_base_unit = Decimal(str(obj.unit_cost or 0))

        try:
            factor = convert_quantity_unit(Decimal("1"), input_unit, base_unit)
        except ValueError:
            factor = Decimal("1")

        cost_per_input_unit = cost_per_base_unit * factor

        return {
            "semi_finished_id": semi_finished_id,
            "item_name":        obj.name,
            "unit":             input_unit,
            "cost_per_unit":    round(float(cost_per_input_unit), 4),
        }

    # ── INVENTORY ITEM ────────────────────────────────────────────────────────
    obj = db.query(Inventory).filter(
        Inventory.id == ingredient_id,
        Inventory.tenant_id == tenant_id,
        Inventory.is_active == True,
    ).first()
    if not obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": f"Inventory item {ingredient_id} not found."},
        )

    base_unit  = (obj.unit.value if hasattr(obj.unit, "value") else str(obj.unit or "gm")).lower().strip()
    input_unit = (user_unit or base_unit).lower().strip()

    PIECE_UNITS  = {"pcs", "piece", "pieces"}
    PACKET_UNITS = {"packet", "packets", "pkt"}

    # use weighted avg from batches — same as dish GET api
    batches = db.query(InventoryBatch).filter(
        InventoryBatch.inventory_item_id == ingredient_id,
        InventoryBatch.tenant_id == tenant_id,
        InventoryBatch.quantity_remaining > 0,
    ).all()

    if input_unit in PIECE_UNITS and base_unit in PACKET_UNITS:
        total_pieces = Decimal("0")
        total_cost   = Decimal("0")
        for batch in batches:
            qty_rem           = Decimal(str(batch.quantity_remaining or 0))
            qty_rec           = Decimal(str(batch.quantity_received  or 0))
            b_cost            = Decimal(str(batch.total_cost         or 0))
            pieces_per_packet = Decimal(str(batch.pieces             or 1))
            remaining_cost    = (qty_rem / qty_rec * b_cost) if qty_rec > 0 else Decimal("0")
            total_pieces     += qty_rem * pieces_per_packet
            total_cost       += remaining_cost

        cost_per_piece = total_cost / total_pieces if total_pieces > 0 else Decimal("0")
        return {
            "ingredient_id": ingredient_id,
            "item_name":     obj.name,
            "unit":          input_unit,
            "cost_per_unit": round(float(cost_per_piece), 4),
        }

    total_qty  = Decimal("0")
    total_cost = Decimal("0")

    for batch in batches:
        batch_unit     = (batch.unit.value if hasattr(batch.unit, "value") else str(batch.unit)).lower().strip()
        qty_remaining  = Decimal(str(batch.quantity_remaining or 0))
        qty_received   = Decimal(str(batch.quantity_received  or 0))
        batch_cost     = Decimal(str(batch.total_cost         or 0))

        remaining_cost = (qty_remaining / qty_received * batch_cost) if qty_received > 0 else Decimal("0")

        try:
            qty_converted = convert_quantity_unit(qty_remaining, batch_unit, base_unit)
        except ValueError:
            qty_converted = qty_remaining

        total_qty  += qty_converted
        total_cost += remaining_cost

    if total_qty > 0:
        avg_cost_per_base_unit = total_cost / total_qty
    else:
        # fallback to stored unit_cost if no batches
        avg_cost_per_base_unit = Decimal(str(obj.unit_cost or 0))

    try:
        factor = convert_quantity_unit(Decimal("1"), input_unit, base_unit)
    except ValueError:
        factor = Decimal("1")

    cost_per_input_unit = avg_cost_per_base_unit * factor

    return {
        "ingredient_id": ingredient_id,
        "item_name":     obj.name,
        "unit":          input_unit,
        "cost_per_unit": round(float(cost_per_input_unit), 4),
    }

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

def safe_float(value, default=0.0) -> float:
    try:
        result = float(value) if value is not None else default
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default
    
@router.post("/add_dish_type",status_code=status.HTTP_201_CREATED)
def add_dish_type(
    data: DishTypeCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant access required",
            )
    try:
        existing = db.query(DishType).filter(
            func.lower(DishType.name) == data.name.lower(),
            DishType.tenant_id == current_user.tenant_id
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Dish type with this name already exists.")

        obj = DishType(
            name=data.name,
            tenant_id=current_user.tenant_id
            )
        db.add(obj)
        db.commit()
        db.refresh(obj)
    
        return {
            "success": True,
            "message": "Dish type added successfully",
            "data": obj
        }
    except HTTPException:
        raise
    except Exception as e:
        handle_db_exception(db, e, "Failed to create dish type")

@router.get("/get_dish_types",status_code=status.HTTP_200_OK )
def list_dish_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
    ):

    if not current_user.tenant_id:
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant access required",
            )
    try:
         data = db.query(DishType).filter(DishType.tenant_id == current_user.tenant_id).order_by(DishType.id.asc()).all()

         return {
            "success": True,
            "message": "Dishes added successfully",
            "data": data
         }
    except Exception as e:
        handle_db_exception(db, e, "Failed to list dish types")

@router.put("/update_dish_types/{dish_type_id}", status_code=status.HTTP_200_OK)
def update_dish_type(
    dish_type_id: int, 
    data: DishTypeUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.tenant_id:
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant access required",
            )
    
    try:
        obj = db.query(DishType).filter(DishType.id == dish_type_id).first()
        if not obj:
            raise HTTPException(status_code=404, detail="Dish type not found.")

        if data.name:
            existing = (
                db.query(DishType)
                .filter(func.lower(DishType.name) == data.name.lower(), DishType.id != dish_type_id)
                .first()
            )
            if existing:
                raise HTTPException(status_code=409, detail="Dish type with this name already exists.")
            obj.name = data.name

        db.commit()
        db.refresh(obj)
        
        return {
            "data" :obj
        }

    except HTTPException:
        raise
    except Exception as e:
        handle_db_exception(db, e, "Failed to update dish type")

@router.delete("/delete_dish_type/{dish_type_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dish_type(
    dish_type_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)    
):
    if not current_user.tenant_id:
        raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant access required",
            )
    try:
        obj = db.query(DishType).filter(DishType.id == dish_type_id).first()
        if not obj:
            raise HTTPException(status_code=404, detail="Dish type not found.")

        in_use = db.query(Dish).filter(Dish.type_id == dish_type_id).first()
        if in_use:
            raise HTTPException(status_code=400, detail="Dish type is used by dishes.")

        db.delete(obj)
        db.commit()
        return {
                "success": True,
                "message": "Item category deleted successfully",
            }
    except HTTPException:
        raise
    except Exception as e:
        handle_db_exception(db, e, "Failed to delete dish type")      

@router.get("/get-dishes-with-ingredients")
def get_dishes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    type_id: Optional[int] = Query(default=None),
    search: Optional[str] = Query(default=None, description="Search by dish name"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=5, ge=1, le=100, description="Rows per page"),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        query = (
            db.query(Dish)
            .filter(Dish.tenant_id == tenant_id, Dish.is_active == True)
            .options(joinedload(Dish.dish_ingredient), joinedload(Dish.type))
        )

        if type_id is not None:
            query = query.filter(Dish.type_id == type_id)

        if search:
            query = query.filter(Dish.name.ilike(f"%{search}%"))

        dishes = query.order_by(Dish.created_at.desc()).all()

        seen = {}
        deduplicated_dishes = []
        for dish in dishes:
            category = dish.type.name if dish.type else None
            key = (dish.name.strip().lower(), category)
            if key not in seen:
                seen[key] = True
                deduplicated_dishes.append(dish)
        dishes = deduplicated_dishes

        total = len(dishes)
        start = (page - 1) * page_size
        dishes = dishes[start : start + page_size]

        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        def safe_float(value, default=0.0) -> float:
            try:
                result = float(value) if value is not None else default
                if math.isnan(result) or math.isinf(result):
                    return default
                return result
            except (TypeError, ValueError):
                return default

        direct_ingredient_ids = {
            ing.ingredient_id
            for dish in dishes
            for ing in dish.dish_ingredient
            if ing.ingredient_id is not None
        }

        all_semi_finished_ids = {
            ing.semi_finished_id
            for dish in dishes
            for ing in dish.dish_ingredient
            if ing.semi_finished_id is not None
        }

        sfp_rows_by_id         = defaultdict(list)
        sfp_raw_ingredient_ids = set()

        if all_semi_finished_ids:
            sfp_ingredient_rows = (
                db.query(SemiFinishedIngredient)
                .filter(
                    SemiFinishedIngredient.semi_finished_id.in_(all_semi_finished_ids),
                    SemiFinishedIngredient.tenant_id == tenant_id,
                )
                .all()
            )

            for row in sfp_ingredient_rows:
                sfp_rows_by_id[row.semi_finished_id].append(row)
                if (
                    not row.is_semi_finished
                    and row.fixed_cost_amount is None
                    and row.ingredient_id is not None
                ):
                    sfp_raw_ingredient_ids.add(row.ingredient_id)

        all_ingredient_ids = list(direct_ingredient_ids | sfp_raw_ingredient_ids)

        inventory_batch_map   = {}
        inventory_name_map    = {}
        batches_by_ingredient = defaultdict(list)

        if all_ingredient_ids:
            all_batches = (
                db.query(
                    InventoryBatch.inventory_item_id,
                    InventoryBatch.unit,
                    InventoryBatch.total_cost,
                    InventoryBatch.quantity_received,
                    InventoryBatch.quantity_remaining,
                    InventoryBatch.pieces,
                )
                .filter(
                    InventoryBatch.inventory_item_id.in_(all_ingredient_ids),
                    InventoryBatch.tenant_id == tenant_id,
                    InventoryBatch.quantity_remaining > 0,
                    InventoryBatch.is_active == True,   # ← Case 1 fix
                )
                .all()
            )

            for batch in all_batches:
                batches_by_ingredient[batch.inventory_item_id].append(batch)

            inventories = db.query(Inventory).filter(
                Inventory.id.in_(all_ingredient_ids),
                Inventory.tenant_id == tenant_id,
            ).all()

            inventory_unit_map = {
                inv.id: _normalize_unit(inv.unit)
                for inv in inventories
            }

            inventory_name_map = {
                inv.id: inv.name
                for inv in inventories
            }

            for ingredient_id, batches in batches_by_ingredient.items():
                item_unit = inventory_unit_map.get(ingredient_id, "gm")

                total_qty_in_item_unit = Decimal("0")
                total_cost             = Decimal("0")

                for batch in batches:
                    batch_unit       = _normalize_unit(batch.unit)
                    qty_remaining    = Decimal(str(batch.quantity_remaining)) if batch.quantity_remaining else Decimal("0")
                    qty_received     = Decimal(str(batch.quantity_received))  if batch.quantity_received  else Decimal("0")
                    batch_total_cost = Decimal(str(batch.total_cost))         if batch.total_cost         else Decimal("0")

                    if qty_received > 0:
                        remaining_cost = (qty_remaining / qty_received) * batch_total_cost
                    else:
                        remaining_cost = Decimal("0")

                    try:
                        qty_in_item_unit = convert_quantity_unit(qty_remaining, batch_unit, item_unit)
                    except ValueError:
                        qty_in_item_unit = qty_remaining

                    total_qty_in_item_unit += qty_in_item_unit
                    total_cost             += remaining_cost

                avg_cost_per_item_unit = (
                    total_cost / total_qty_in_item_unit
                    if total_qty_in_item_unit > 0
                    else Decimal("0")
                )

                inventory_batch_map[ingredient_id] = {
                    "item_unit":              item_unit,
                    "avg_cost_per_item_unit": avg_cost_per_item_unit,
                }

        def calc_raw_ingredient_line(ingredient_id, unit_str, qty: Decimal, stored_cpu=None) -> tuple[Decimal, Decimal]:
            """Returns (cost_per_unit, line_cost) as Decimal, live batch costs + pcs/packet.
            Out-of-stock (no usable active batch) → (0, 0)."""
            ing_unit   = _normalize_unit(unit_str)
            batch_info = inventory_batch_map.get(ingredient_id)
            item_unit  = (batch_info["item_unit"] if batch_info else "").lower().strip()

            if ing_unit in PIECE_UNITS and item_unit in PACKET_UNITS:
                batches      = batches_by_ingredient.get(ingredient_id, [])
                total_pieces = Decimal("0")
                total_cost   = Decimal("0")

                for b in batches:
                    b_qty_remaining   = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
                    b_qty_received    = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
                    b_total_cost      = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")
                    pieces_per_packet = Decimal(str(b.pieces))             if b.pieces             else Decimal("1")

                    if b_qty_received > Decimal("0"):
                        remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
                    else:
                        remaining_cost = Decimal("0")

                    total_pieces += b_qty_remaining * pieces_per_packet
                    total_cost   += remaining_cost

                if total_pieces > Decimal("0"):
                    cost_per_piece = total_cost / total_pieces
                    return cost_per_piece, cost_per_piece * qty

            if batch_info and batch_info["avg_cost_per_item_unit"] > Decimal("0"):
                avg_cost = batch_info["avg_cost_per_item_unit"]
                try:
                    one_unit_in_item_unit = convert_quantity_unit(Decimal("1"), ing_unit, item_unit)
                    cpu = avg_cost * one_unit_in_item_unit
                    return cpu, cpu * qty
                except ValueError:
                    pass

            # Out of stock — zero cost (Case 2 fix)
            return Decimal("0"), Decimal("0")

        semi_finished_cost_map = {}
        semi_finished_unit_map = {}

        if all_semi_finished_ids:
            sfps = (
                db.query(SemiFinishedProduct)
                .filter(
                    SemiFinishedProduct.id.in_(all_semi_finished_ids),
                    SemiFinishedProduct.tenant_id == tenant_id,
                    SemiFinishedProduct.is_active == True,
                )
                .all()
            )

            for sfp in sfps:
                rows = sfp_rows_by_id.get(sfp.id, [])
                production_cost = Decimal("0")

                for row in rows:
                    if row.fixed_cost_amount is not None:
                        production_cost += Decimal(str(row.fixed_cost_amount))
                        continue

                    qty = Decimal(str(row.quantity_required)) if row.quantity_required else Decimal("0")

                    if row.is_semi_finished:
                        cpu = Decimal(str(row.cost_per_unit or 0))
                        production_cost += qty * cpu
                    elif row.ingredient_id is not None:
                        _, line_cost = calc_raw_ingredient_line(row.ingredient_id, row.unit, qty, row.cost_per_unit)
                        production_cost += line_cost
                    else:
                        cpu = Decimal(str(row.cost_per_unit or 0))
                        production_cost += qty * cpu

                yield_qty = Decimal(str(safe_float(sfp.yield_quantity))) if sfp.yield_quantity else Decimal("0")
                semi_finished_cost_map[sfp.id] = (
                    production_cost / yield_qty if yield_qty > 0 else Decimal("0")
                )
                semi_finished_unit_map[sfp.id] = _normalize_unit(sfp.unit)

        def calc_ingredient_costs(ing) -> tuple[float, float]:
            if ing.fixed_cost_amount is not None:
                return 0.0, safe_float(ing.fixed_cost_amount)

            qty       = Decimal(str(ing.quantity_required)) if ing.quantity_required else Decimal("0")
            dish_unit = _normalize_unit(ing.unit)

            if ing.semi_finished_id is not None:
                live_cpu = semi_finished_cost_map.get(ing.semi_finished_id, Decimal("0"))
                sfp_unit = semi_finished_unit_map.get(ing.semi_finished_id, "")

                if not sfp_unit or not dish_unit or sfp_unit == dish_unit:
                    cost_per_dish_unit = live_cpu
                else:
                    try:
                        sfp_units_per_dish_unit = convert_quantity_unit(Decimal("1"), dish_unit, sfp_unit)
                        cost_per_dish_unit = live_cpu * sfp_units_per_dish_unit
                    except (ValueError, ZeroDivisionError):
                        cost_per_dish_unit = live_cpu

                total = cost_per_dish_unit * qty
                return safe_float(round(cost_per_dish_unit, 6)), safe_float(round(total, 6))

            if ing.ingredient_id is None:
                stored_cpu = Decimal(str(ing.cost_per_unit)) if ing.cost_per_unit else Decimal("0")
                total      = qty * stored_cpu
                return safe_float(round(stored_cpu, 6)), safe_float(round(total, 6))

            cpu, total = calc_raw_ingredient_line(ing.ingredient_id, ing.unit, qty, ing.cost_per_unit)
            return safe_float(round(cpu, 6)), safe_float(round(total, 6))

        ingredient_cost_cache = {}

        def get_ingredient_costs(ing) -> tuple[float, float]:
            if ing.id not in ingredient_cost_cache:
                ingredient_cost_cache[ing.id] = calc_ingredient_costs(ing)
            return ingredient_cost_cache[ing.id]

        return {
            "success": True,
            "count": len(dishes),
            "meta": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": math.ceil(total / page_size) if total else 1,
                "search": search,
            },
            "dishes": [
                {
                    "id":            dish.id,
                    "name":          dish.name,
                    "category_name": dish.type.name if dish.type else None,
                    "selling_price": safe_float(dish.selling_price),
                    "is_active":     dish.is_active,
                    "created_at":    dish.created_at,
                    "total_dish_cost": round(
                        sum(get_ingredient_costs(ing)[1] for ing in dish.dish_ingredient), 4
                    ),
                    "ingredients": [
                        {
                            "id":                    ing.id,
                            "ingredient_id":         ing.ingredient_id,
                            "semi_finished_id":      ing.semi_finished_id,
                            "is_semi_finished":      ing.is_semi_finished,
                            "ingredient_name":       inventory_name_map.get(ing.ingredient_id, ing.ingredient_name),
                            "quantity_required":     None if ing.fixed_cost_amount is not None else safe_float(ing.quantity_required),
                            "unit":                  ing.unit,
                            "cost_per_unit":         None if ing.fixed_cost_amount is not None else get_ingredient_costs(ing)[0],
                            "fixed_cost_amount":     float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None else None,
                            "ingredient_total_cost": get_ingredient_costs(ing)[1],
                        }
                        for ing in dish.dish_ingredient
                    ],
                }
                for dish in dishes
            ],
        }

    except SQLAlchemyError as db_error:
        logger.exception(f"Database error while fetching dishes: {db_error}")
        raise HTTPException(status_code=500, detail="Database error while fetching dishes")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while fetching dishes: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
@router.put("/update_dish/{dish_id}")
def update_dish_with_ingredients(
    dish_id: int,
    payload: UpdateDishWithIngredientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # 1. Fetch the dish (tenant-scoped)
        dish = db.query(Dish).filter(
            Dish.id == dish_id,
            Dish.tenant_id == tenant_id,
        ).first()
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")

        # 2. Update scalar fields only when provided
        if payload.dish_name is not None:
            dish.name = payload.dish_name
        if payload.selling_price is not None:
            dish.selling_price = payload.selling_price
        if payload.is_active is not None:
            dish.is_active = payload.is_active

        if payload.type_id is not None:
            dish_type = db.query(DishType).filter(
                DishType.id == payload.type_id,
                DishType.tenant_id == tenant_id,
            ).first()
            if not dish_type:
                raise HTTPException(status_code=404, detail="Dish type not found")
            dish.type_id = payload.type_id

        # 3. Replace ingredients only when a new list is provided
        if payload.ingredients is not None:
            # Validate all incoming inventory IDs
            requested_ids = [item.ingredient_id for item in payload.ingredients]
            inventory_items = db.query(Inventory).filter(
                Inventory.id.in_(requested_ids),
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).all()
            inventory_map = {inv.id: inv for inv in inventory_items}

            missing = set(requested_ids) - set(inventory_map.keys())
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"Inventory IDs not found: {sorted(missing)}",
                )

            # Delete existing ingredients and replace with new ones
            db.query(DishIngredient).filter(
                DishIngredient.dish_id == dish_id,
                DishIngredient.tenant_id == tenant_id,
            ).delete(synchronize_session=False)

            new_ingredients = []
            total_dish_cost = 0.0
            zero_cost_items = []

            for item in payload.ingredients:
                inv = inventory_map[item.ingredient_id]
                cost_per_unit = float(inv.unit_cost or 0)
                ingredient_total_cost = round(cost_per_unit * item.quantity_required, 2)
                total_dish_cost += ingredient_total_cost

                if cost_per_unit == 0:
                    zero_cost_items.append(inv.name)

                new_ingredients.append(
                    DishIngredient(
                        dish_id=dish.id,
                        ingredient_id=item.ingredient_id,
                        ingredient_name=inv.name,
                        quantity_required=item.quantity_required,
                        unit=item.unit,
                        cost_per_unit=cost_per_unit,
                        is_semi_finished=False,
                        tenant_id=tenant_id,
                    )
                )

            db.add_all(new_ingredients)
        else:
            # Recompute cost from existing ingredients (no ingredient change)
            existing_ingredients = db.query(DishIngredient).filter(
                DishIngredient.dish_id == dish_id,
                DishIngredient.tenant_id == tenant_id,
            ).all()
            new_ingredients = existing_ingredients
            total_dish_cost = round(
                sum(
                    float(ing.cost_per_unit or 0) * float(ing.quantity_required or 0)
                    for ing in existing_ingredients
                ),
                2,
            )
            zero_cost_items = []

        db.commit()
        db.refresh(dish)

        return {
            "success": True,
            "dish_id": dish.id,
            "dish_name": dish.name,
            "type_id": dish.type_id,
            "selling_price": float(dish.selling_price or 0),
            "is_active": dish.is_active,
            "total_dish_cost": round(total_dish_cost, 2),
            "updated_count": len(new_ingredients),
            "warnings": (
                [f"No batch found for: {', '.join(zero_cost_items)} — cost defaulted to 0"]
                if zero_cost_items else []
            ),
            "ingredients": [
                {
                    "id": ing.id,
                    "ingredient_name": ing.ingredient_name,
                    "quantity_required": float(ing.quantity_required or 0),
                    "unit": ing.unit,
                    "cost_per_unit": float(ing.cost_per_unit or 0),
                    "ingredient_total_cost": round(
                        float(ing.cost_per_unit or 0) * float(ing.quantity_required or 0), 2
                    ),
                    "created_at": ing.created_at,
                }
                for ing in new_ingredients
            ],
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"Database error while updating dish {dish_id}: {db_error}")
        raise HTTPException(status_code=500, detail="Database error while updating dish")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while updating dish {dish_id}: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")

@router.delete("/delete_dish/{dish_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_dish(
    dish_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        dish = db.query(Dish).filter(
            Dish.id == dish_id,
            Dish.tenant_id == current_user.tenant_id,
        ).first()

        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")

        if not dish.is_active:
            raise HTTPException(status_code=400, detail="Dish is already inactive")

        dish.is_active = False
        db.commit()

        return {
            "success": True,
            "message": f"Dish '{dish.name}' deactivated successfully",
            "dish_id": dish_id,
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"Database error while soft-deleting dish {dish_id}: {db_error}")
        raise HTTPException(status_code=500, detail="Database error while deactivating dish")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while soft-deleting dish {dish_id}: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")     

@router.post("/add_dish_types_via_excel", status_code=status.HTTP_201_CREATED)
def add_dish_types_via_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Auth ──────────────────────────────────────────────────────────────────
    if not current_user or not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user session",
        )

    tenant_id = current_user.tenant_id  # ← assign once, use everywhere below

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

    if "name" not in df.columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required column: name",
        )

    validated_rows = []
    errors         = []

    for index, row in df.iterrows():
        row_number = index + 2
        name       = None
        try:
            name = str(row.get("name", "")).strip()
            if not name or name.lower() == "nan":
                raise ValueError("Dish type name is required")

            # ── Tenant-scoped duplicate check ─────────────────────────────────
            existing = db.query(DishType).filter(
                func.lower(DishType.name) == name.lower(),
                DishType.tenant_id == tenant_id,
            ).first()
            if existing:
                raise ValueError(f"Dish type '{name}' already exists for this tenant")

            validated_rows.append({"name": name})

        except (ValueError, TypeError) as e:
            errors.append({
                "row":             row_number,
                "dish_type_name":  name if name and name.lower() != "nan" else None,
                "error":           str(e),
            })

    if errors:
        return {
            "success": False,
            "message": "Excel validation failed. No data saved.",
            "summary": {
                "total_rows":   len(df),
                "failed_count": len(errors),
            },
            "failed_rows": errors,
        }

    try:
        for row_data in validated_rows:
            db.add(DishType(
                name=row_data["name"],
                tenant_id=tenant_id,   # ← uses tenant_id variable
            ))

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error while saving dish types",
        )

    return {
        "success": True,
        "message": "All dish types uploaded successfully",
        "summary": {
            "total_rows":  len(validated_rows),
            "saved_count": len(validated_rows),
        },
    }
    
# Apis for add semi-finished ingredients in the system/application
@router.post("/add-semi-finished-ingredients", status_code=status.HTTP_201_CREATED)
def create_semi_finished_product(
    payload: CreateSemiFinishedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # 1. Validate all inventory IDs
        requested_ids = [item.ingredient_id for item in payload.ingredients if item.ingredient_id]
        inventory_items = db.query(Inventory).filter(
            Inventory.id.in_(requested_ids),
            Inventory.tenant_id == tenant_id,
            Inventory.is_active == True,
        ).all()
        inventory_map = {inv.id: inv for inv in inventory_items}

        missing_ids = set(requested_ids) - set(inventory_map.keys())
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Inventory IDs not found: {sorted(missing_ids)}",
            )

        # 1b. Auto-create inventory for name-only ingredients (no ingredient_id)
        auto_created = []
        for item in payload.ingredients:
            if item.ingredient_id:
                continue  # already resolved above

            if not item.ingredient_name:
                raise HTTPException(
                    status_code=400,
                    detail="ingredient_name is required when ingredient_id is not provided.",
                )

            name_lower = item.ingredient_name.strip().lower()

            existing = db.query(Inventory).filter(
                func.lower(Inventory.name) == name_lower,
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).first()

            if existing:
                item.ingredient_id = existing.id
                inventory_map[existing.id] = existing
            else:
                new_inv = Inventory(
                    name=item.ingredient_name.strip(),
                    unit=item.unit,
                    unit_cost=0,
                    is_active=True,
                    tenant_id=tenant_id,
                )
                db.add(new_inv)
                db.flush()
                item.ingredient_id = new_inv.id
                inventory_map[new_inv.id] = new_inv
                auto_created.append(item.ingredient_name.strip())

        # 2. Fetch ALL active batches per ingredient (grouped)

        all_ingredient_ids = [item.ingredient_id for item in payload.ingredients]

        all_batches = db.query(InventoryBatch).filter(
            InventoryBatch.inventory_item_id.in_(all_ingredient_ids),
            InventoryBatch.tenant_id == tenant_id,
            InventoryBatch.quantity_remaining > 0,
        ).all()

        batches_by_ingredient = defaultdict(list)
        for batch in all_batches:
            batches_by_ingredient[batch.inventory_item_id].append(batch)

        # Keep latest batch map as fallback only
        all_batches_fallback = db.query(InventoryBatch).filter(
            InventoryBatch.inventory_item_id.in_(all_ingredient_ids),
            InventoryBatch.tenant_id == tenant_id,
        ).order_by(InventoryBatch.date_added.desc()).all()

        batch_map = {}
        for batch in all_batches_fallback:
            if batch.inventory_item_id not in batch_map:
                batch_map[batch.inventory_item_id] = batch

        # 3. Calculate total cost of all ingredients
        total_cost = 0.0
        zero_cost_items = []
        ingredients_to_insert = []
        line_costs = {}

        for item in payload.ingredients:
            inv = inventory_map[item.ingredient_id]

            # Fixed cost item (Cylinder, Electricity, Charcoal)
            if inv.is_fixed_cost:
                fixed_amt  = float(item.fixed_cost_amount or 0)
                line_cost  = fixed_amt
                total_cost += line_cost
                line_costs[item.ingredient_id] = line_cost

                if fixed_amt == 0:
                    zero_cost_items.append(inv.name)

                ingredients_to_insert.append({
                    "ingredient_id":     item.ingredient_id,
                    "ingredient_name":   inv.name,
                    "quantity_required": 1,
                    "unit":              item.unit,
                    "cost_per_unit":     0.0,
                    "fixed_cost_amount": fixed_amt,
                })
                continue

            # Normal item — Weighted Average Cost
            PIECE_UNITS  = {"pcs", "piece", "pieces"}
            PACKET_UNITS = {"packet", "packets", "pkt"}

            item_unit_str        = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit or "")
            dish_unit_normalized = str(item.unit).lower().strip() if item.unit else ""
            item_unit_normalized = item_unit_str.lower().strip()

            ingredient_batches = batches_by_ingredient.get(item.ingredient_id, [])
            fallback_cost      = Decimal(str(
                batch_map[item.ingredient_id].unit_cost
                if item.ingredient_id in batch_map else inv.unit_cost or 0
            ))

            # pcs vs packet — derive cost from total_cost + pieces_per_packet
            if dish_unit_normalized in PIECE_UNITS and item_unit_normalized in PACKET_UNITS:
                total_pieces   = Decimal("0")
                total_cost_val = Decimal("0")

                for b in ingredient_batches:
                    b_qty_remaining   = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
                    b_qty_received    = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
                    b_total_cost      = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")
                    pieces_per_packet = Decimal(str(b.pieces))             if b.pieces             else Decimal("1")

                    if b_qty_received > Decimal("0"):
                        remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
                    else:
                        remaining_cost = Decimal("0")

                    total_pieces   += b_qty_remaining * pieces_per_packet
                    total_cost_val += remaining_cost

                if total_pieces > Decimal("0"):
                    cost_per_unit_converted = float(total_cost_val / total_pieces)
                else:
                    cost_per_unit_converted = float(fallback_cost)

                is_zero = cost_per_unit_converted == 0

            else:
                cost_per_unit_converted, is_zero = calc_weighted_avg_cost(
                    ingredient_batches=ingredient_batches,
                    dish_unit=item.unit,
                    item_unit=item_unit_str,
                    fallback_cost=fallback_cost,
                )
                cost_per_unit_converted = float(cost_per_unit_converted)

            if is_zero:
                zero_cost_items.append(inv.name)

            line_cost   = round(cost_per_unit_converted * float(item.quantity_required), 2)
            total_cost += line_cost
            line_costs[item.ingredient_id] = line_cost

            ingredients_to_insert.append({
                "ingredient_id":     item.ingredient_id,
                "ingredient_name":   inv.name,
                "quantity_required": item.quantity_required,
                "unit":              item.unit,
                "cost_per_unit":     round(cost_per_unit_converted, 6),
                "fixed_cost_amount": None,
            })

        # 4. unit_cost = total ingredient cost / yield quantity
        unit_cost = round(total_cost / float(payload.yield_quantity), 4) if payload.yield_quantity else 0.0

        existing_semi = db.query(SemiFinishedProduct).filter(
            func.lower(SemiFinishedProduct.name) == payload.name.strip().lower(),
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).first()

        if existing_semi:
            raise HTTPException(
                status_code=409,
                detail=f"A semi-finished product named '{payload.name}' already exists.",
            )

        # 5. Create the semi-finished product
        semi = SemiFinishedProduct(
            name=payload.name,
            unit=payload.yield_unit,
            yield_quantity=payload.yield_quantity,
            unit_cost=unit_cost,
            is_active=True,
            tenant_id=tenant_id,
        )
        db.add(semi)
        db.flush()

        # 6. Bulk insert ingredients
        sfp_ingredients = [
            SemiFinishedIngredient(
                semi_finished_id=semi.id,
                tenant_id=tenant_id,
                **ing_data,
            )
            for ing_data in ingredients_to_insert
        ]
        db.add_all(sfp_ingredients)
        db.commit()
        db.refresh(semi)

        return {
            "success": True,
            "semi_finished_id": semi.id,
            "name": semi.name,
            "yield_quantity": float(semi.yield_quantity),
            "yield_unit": semi.unit,
            "total_batch_cost": round(total_cost, 2),
            "unit_cost": unit_cost,
            "ingredient_count": len(sfp_ingredients),
            "auto_created_inventory": auto_created,
            "warnings": (
                [f"No batch found for: {', '.join(zero_cost_items)} — cost defaulted to 0"]
                if zero_cost_items else []
            ),
            "ingredients": [
                {
                    "id":                ing.id,
                    "ingredient_id":     ing.ingredient_id,
                    "ingredient_name":   ing.ingredient_name,
                    "quantity_required": None if ing.fixed_cost_amount is not None else float(ing.quantity_required),
                    "unit":              ing.unit,
                    "cost_per_unit":     None if ing.fixed_cost_amount is not None else ing.cost_per_unit,
                    "fixed_cost_amount": float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None else None,
                    "line_cost":         float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None
                                         else line_costs.get(ing.ingredient_id, 0),
                }
                for ing in sfp_ingredients
            ],
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"DB error creating semi-finished product: {db_error}")
        raise HTTPException(status_code=500, detail="Database error")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error creating semi-finished product: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
EXPECTED_HEADERS = [
    "name",
    "yield_quantity",
    "yield_unit",
    "ingredient_name",
    "quantity_required",
    "unit",
]

OPTIONAL_SEMI_HEADERS = [
    "quantity_required",
    "fixed_cost_amount",  # ← for cylinder/electricity/charcoal
]
 
def _parse_excel(file_bytes: bytes) -> list[dict]:
    try:
        wb = openpyxl.load_workbook(filename=BytesIO(file_bytes), data_only=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_FILE",
                "message": "Could not read the uploaded file. Make sure it is a valid .xlsx file.",
                "detail": str(e),
            },
        )
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "EMPTY_FILE", "message": "Excel file is empty."},
        )

    # Row 1 = headers, Row 2+ = data
    header_row = [str(h).strip().lower() if h else "" for h in rows[0]]

    missing = [col for col in EXPECTED_HEADERS if col not in header_row]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "MISSING_COLUMNS",
                "message": f"Required column(s) not found in row 1: {missing}",
                "expected_columns": EXPECTED_HEADERS,
                "found_columns": [h for h in header_row if h],
            },
        )

    col_idx = {col: header_row.index(col) for col in EXPECTED_HEADERS}

    for col in OPTIONAL_SEMI_HEADERS:
        if col in header_row:
            col_idx[col] = header_row.index(col)

    parsed = []
    for row_num, row in enumerate(rows[1:], start=2):
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue

        # safely read optional columns
        def get_optional(col):
            idx = col_idx.get(col)
            return row[idx] if idx is not None and idx < len(row) else None

        parsed.append({
            "row_num":          row_num,
            "name":             str(row[col_idx["name"]]).strip() if row[col_idx["name"]] else "",
            "yield_quantity":   row[col_idx["yield_quantity"]],
            "yield_unit":       str(row[col_idx["yield_unit"]]).strip() if row[col_idx["yield_unit"]] else "",
            "ingredient_name":  str(row[col_idx["ingredient_name"]]).strip() if row[col_idx["ingredient_name"]] else "",
            "quantity_required": get_optional("quantity_required"),
            "fixed_cost_amount": get_optional("fixed_cost_amount"),
            "unit":              str(row[col_idx["unit"]]).strip() if row[col_idx["unit"]] else "",
        })
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "NO_DATA",
                "message": "No data rows found. Data must start from row 2 (row 1 is headers).",
            },
        )

    return parsed
 
def _group_rows(rows: list[dict]) -> dict[str, dict]:
    """
    Group rows by semi-finished product name.
    Carry-forward: if name/yield_quantity/yield_unit is blank, inherit from the previous row.
    """
    grouped: dict[str, dict] = {}
    last_name = last_yield_qty = last_yield_unit = None
 
    for row in rows:
        name = row["name"] or last_name
        yield_qty = row["yield_quantity"] if row["yield_quantity"] not in (None, "") else last_yield_qty
        yield_unit = row["yield_unit"] or last_yield_unit
 
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "MISSING_NAME",
                    "message": f"Row {row['row_num']}: 'name' is blank and cannot be inherited — no product name in any previous row.",
                    "row": row["row_num"],
                },
            )
 
        last_name, last_yield_qty, last_yield_unit = name, yield_qty, yield_unit
 
        if name not in grouped:
            grouped[name] = {
                "yield_quantity": yield_qty,
                "yield_unit": yield_unit,
                "ingredients": [],
            }
 
        if row["ingredient_name"]:
            ing_name_lower = row["ingredient_name"].lower()
            already_seen = {
                ing["ingredient_name"].lower()
                for ing in grouped[name]["ingredients"]
            }
            if ing_name_lower in already_seen:
                # Track duplicate so we can warn the caller; skip inserting it
                grouped[name].setdefault("skipped_duplicates", []).append({
                    "row_num": row["row_num"],
                    "ingredient_name": row["ingredient_name"],
                })
            else:
                grouped[name]["ingredients"].append({
                    "row_num":           row["row_num"],
                    "ingredient_name":   row["ingredient_name"],
                    "quantity_required": row["quantity_required"],
                    "unit":              row["unit"],
                    "fixed_cost_amount": row.get("fixed_cost_amount"),  # ← ADD
                })
 
    return grouped
 
@router.post("/add-semi-finished-ingredients-via-excel", status_code=status.HTTP_201_CREATED)
def create_semi_finished_products_via_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user or not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "Invalid or expired user session."},
        )

    tenant_id = current_user.tenant_id

    # ── 1. Parse Excel ──────────────────────────────────────────────────────
    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "EMPTY_UPLOAD", "message": "Uploaded file is empty."},
        )

    raw_rows = _parse_excel(file_bytes)
    grouped  = _group_rows(raw_rows)

    # ── 2. Resolve all ingredient names → Inventory ─────────────────────────
    all_ingredient_names = {
        ing["ingredient_name"].lower()
        for product_data in grouped.values()
        for ing in product_data["ingredients"]
        if ing["ingredient_name"]
    }

    inventory_items = db.query(Inventory).filter(
        Inventory.tenant_id == tenant_id,
        Inventory.is_active == True,
    ).all()
    inventory_name_map = {inv.name.lower(): inv for inv in inventory_items}

    # ── 3. Auto-create any missing inventory items ───────────────────────────
    auto_created_inventory = []
    for ing_name_lower in all_ingredient_names - set(inventory_name_map.keys()):
        original_name = next(
            ing["ingredient_name"]
            for product_data in grouped.values()
            for ing in product_data["ingredients"]
            if ing["ingredient_name"].lower() == ing_name_lower
        )
        ing_unit = next(
            (ing["unit"] for product_data in grouped.values()
             for ing in product_data["ingredients"]
             if ing["ingredient_name"].lower() == ing_name_lower and ing["unit"]),
            "unit"
        )
        new_inv = Inventory(
            name=original_name,
            unit=ing_unit,
            unit_cost=0,
            is_active=True,
            tenant_id=tenant_id,
        )
        db.add(new_inv)
        db.flush()
        inventory_name_map[ing_name_lower] = new_inv
        auto_created_inventory.append(original_name)

    # ── 4. Fetch ALL active non-expired batches ───────────────────────────────
    from collections import defaultdict

    resolved_inv_ids = [inventory_name_map[n].id for n in all_ingredient_names]

    all_batches = db.query(InventoryBatch).filter(
        InventoryBatch.inventory_item_id.in_(resolved_inv_ids),
        InventoryBatch.tenant_id == tenant_id,
        # InventoryBatch.is_active == True,
        InventoryBatch.quantity_remaining > 0,
    ).all() if resolved_inv_ids else []

    #  Sare batches group karo by inventory_item_id
    batches_by_inv_id: dict[int, list] = defaultdict(list)
    for batch in all_batches:
        batches_by_inv_id[batch.inventory_item_id].append(batch)

    # ── 5. Skip already existing semi-finished products ──────────────────────
    incoming_names_lower = [name.lower() for name in grouped.keys()]

    existing_semi = db.query(SemiFinishedProduct.name).filter(
        func.lower(SemiFinishedProduct.name).in_(incoming_names_lower),
        SemiFinishedProduct.tenant_id == tenant_id,
        SemiFinishedProduct.is_active == True,
    ).all()

    existing_names_lower = {row.name.strip().lower() for row in existing_semi}

    skipped_products = []
    grouped = {
        product_name: product_data
        for product_name, product_data in grouped.items()
        if product_name.lower() not in existing_names_lower
        or skipped_products.append(product_name)
    }

    if not grouped:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ALL_DUPLICATES",
                "committed": False,
                "message": "All semi-finished products in this file already exist.",
                "skipped": skipped_products,
            },
        )

    # ── 6. Build and insert all semi-finished products ────────────────────────
    try:
        created = []

        for product_name, product_data in grouped.items():
            yield_quantity = Decimal(str(product_data["yield_quantity"] or 1))
            yield_unit     = product_data["yield_unit"] or "unit"

            total_cost            = Decimal("0")
            ingredients_to_insert = []
            seen_ingredient_ids: set[int] = set()

            for ing in product_data["ingredients"]:
                if not ing["ingredient_name"]:
                    continue

                ing_name_lower = ing["ingredient_name"].lower()
                inv = inventory_name_map.get(ing_name_lower)
                if not inv:
                    continue

                if inv.id in seen_ingredient_ids:
                    continue
                seen_ingredient_ids.add(inv.id)

                unit = ing["unit"] or (
                    inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit)
                )

                #  Fixed cost item (Cylinder, Electricity, Charcoal)
                if inv.is_fixed_cost:
                    fixed_amt   = Decimal(str(ing.get("fixed_cost_amount") or 0))
                    total_cost += fixed_amt

                    ingredients_to_insert.append({
                        "ingredient_id":     inv.id,
                        "ingredient_name":   inv.name,
                        "quantity_required": 1,           # dummy
                        "unit":              unit,
                        "cost_per_unit":     Decimal("0"),
                        "fixed_cost_amount": fixed_amt,   # ← ₹ stored here
                        "line_cost":         fixed_amt,
                    })
                    continue  # ← skip normal cost calculation

                #  Normal item — weighted avg cost from batch
                qty           = Decimal(str(ing["quantity_required"] or 0))
                item_unit     = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit)
                fallback_cost = Decimal(str(inv.unit_cost or 0))

                ingredient_batches = batches_by_inv_id.get(inv.id, [])

                cost_per_unit_converted, _ = calc_weighted_avg_cost(
                    ingredient_batches=ingredient_batches,
                    dish_unit=unit,
                    item_unit=item_unit,
                    fallback_cost=fallback_cost,
                )

                line_cost   = cost_per_unit_converted * qty
                total_cost += line_cost

                ingredients_to_insert.append({
                    "ingredient_id":     inv.id,
                    "ingredient_name":   inv.name,
                    "quantity_required": float(qty),
                    "unit":              unit,
                    "cost_per_unit":     cost_per_unit_converted,
                    "fixed_cost_amount": None,   # ← not a fixed cost item
                    "line_cost":         line_cost,
                })

            #  unit_cost = total_cost / yield_quantity — Decimal division
            unit_cost = total_cost / yield_quantity if yield_quantity > 0 else Decimal("0")

            semi = SemiFinishedProduct(
                name=product_name,
                unit=yield_unit,
                yield_quantity=float(yield_quantity),
                unit_cost=unit_cost,   #  Decimal — exact
                is_active=True,
                tenant_id=tenant_id,
            )
            db.add(semi)
            db.flush()

            db.add_all([
                SemiFinishedIngredient(
                    semi_finished_id=semi.id,
                    tenant_id=tenant_id,
                    ingredient_id=ing["ingredient_id"],
                    ingredient_name=ing["ingredient_name"],
                    quantity_required=ing["quantity_required"],
                    unit=ing["unit"],
                    cost_per_unit=ing["cost_per_unit"], 
                    fixed_cost_amount = ing.get("fixed_cost_amount"),
                )
                for ing in ingredients_to_insert
            ])

            created.append({
                "semi_finished_id": semi.id,
                "name":             semi.name,
                "unit_cost":        float(unit_cost),
                "total_batch_cost": float(total_cost),
                "ingredient_count": len(ingredients_to_insert),
            })

        db.commit()

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "committed":              True,
                "message":                f"All {len(created)} semi-finished product(s) created successfully.",
                "total_products":         len(created),
                "total_products_skipped": len(skipped_products),
                "skipped_duplicates":     skipped_products,
                "auto_created_inventory": auto_created_inventory,
                "results":                created,
            },
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error during Excel semi-finished upload: {e}")
        cause = getattr(e, "orig", None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DATABASE_ERROR",
                "committed": False,
                "message":   "Database error while saving. No data was saved.",
                "cause":     str(cause) if cause else str(e),
            },
        )

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error during Excel semi-finished upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "committed":   False,
                "message":     "Unexpected server error. No data was saved.",
                "error_type":  type(e).__name__,
                "error":       str(e),
            },
        )
    
@router.get("/semi-finished-ingredients", status_code=status.HTTP_200_OK)
def get_semi_finished_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    is_active: Optional[bool] = Query(default=True),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=100, description="Rows per page"),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        query = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.tenant_id == tenant_id,
        )

        if is_active is not None:
            query = query.filter(SemiFinishedProduct.is_active == is_active)

        if search:
            query = query.filter(SemiFinishedProduct.name.ilike(f"%{search}%"))

        total = query.count()
        semi_finished_list = (
            query
            .order_by(SemiFinishedProduct.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .execution_options(populate_existing=True)
            .all()
        )

        all_semis = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).execution_options(populate_existing=True).all()
        semi_map = {s.id: s for s in all_semis}

        semi_ids = [s.id for s in semi_finished_list]

        all_ingredient_rows = (
            db.query(SemiFinishedIngredient)
            .filter(
                SemiFinishedIngredient.semi_finished_id.in_(semi_ids),
                SemiFinishedIngredient.tenant_id == tenant_id,
            )
            .all()
        )

        raw_ingredient_ids = list({
            row.ingredient_id
            for row in all_ingredient_rows
            if not row.is_semi_finished
            and row.fixed_cost_amount is None
            and row.ingredient_id is not None
        })

        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        inventory_batch_map   = {}
        batches_by_ingredient = defaultdict(list)

        if raw_ingredient_ids:
            all_batches = (
                db.query(
                    InventoryBatch.inventory_item_id,
                    InventoryBatch.unit,
                    InventoryBatch.quantity_received,
                    InventoryBatch.quantity_remaining,
                    InventoryBatch.total_cost,
                    InventoryBatch.pieces,
                )
                .filter(
                    InventoryBatch.inventory_item_id.in_(raw_ingredient_ids),
                    InventoryBatch.tenant_id == tenant_id,
                    InventoryBatch.quantity_remaining > 0,
                    InventoryBatch.is_active == True,   # ← Case 1 fix
                )
                .all()
            )

            for batch in all_batches:
                batches_by_ingredient[batch.inventory_item_id].append(batch)

            inventories = (
                db.query(Inventory)
                .filter(
                    Inventory.id.in_(raw_ingredient_ids),
                    Inventory.tenant_id == tenant_id,
                )
                .all()
            )

            inventory_unit_map = {
                inv.id: _normalize_unit(inv.unit)
                for inv in inventories
            }

            for ingredient_id, batches in batches_by_ingredient.items():
                item_unit = inventory_unit_map.get(ingredient_id, "gm")

                total_qty_in_item_unit = Decimal("0")
                total_cost             = Decimal("0")

                for batch in batches:
                    batch_unit       = _normalize_unit(batch.unit)
                    qty_remaining    = Decimal(str(batch.quantity_remaining)) if batch.quantity_remaining else Decimal("0")
                    qty_received     = Decimal(str(batch.quantity_received))  if batch.quantity_received  else Decimal("0")
                    batch_total_cost = Decimal(str(batch.total_cost))         if batch.total_cost         else Decimal("0")

                    if qty_received > 0:
                        remaining_cost = (qty_remaining / qty_received) * batch_total_cost
                    else:
                        remaining_cost = Decimal("0")

                    try:
                        qty_in_item_unit = convert_quantity_unit(qty_remaining, batch_unit, item_unit)
                    except ValueError:
                        qty_in_item_unit = qty_remaining

                    total_qty_in_item_unit += qty_in_item_unit
                    total_cost             += remaining_cost

                avg_cost_per_item_unit = (
                    total_cost / total_qty_in_item_unit
                    if total_qty_in_item_unit > 0
                    else Decimal("0")
                )

                inventory_batch_map[ingredient_id] = {
                    "item_unit":              item_unit,
                    "avg_cost_per_item_unit": avg_cost_per_item_unit,
                }

        rows_by_semi = defaultdict(list)
        for row in all_ingredient_rows:
            rows_by_semi[row.semi_finished_id].append(row)

        def calc_ingredient_cost(row) -> tuple[float, float]:
            """Returns (cost_per_unit, line_cost)"""

            if row.fixed_cost_amount is not None:
                return None, float(row.fixed_cost_amount)

            qty      = Decimal(str(row.quantity_required)) if row.quantity_required else Decimal("0")
            ing_unit = _normalize_unit(row.unit)

            # Nested SFP — use stored cost_per_unit (not stock-based, unaffected)
            if row.is_semi_finished:
                stored_cpu = Decimal(str(row.cost_per_unit or 0))
                total      = qty * stored_cpu
                return safe_float(round(stored_cpu, 6)), safe_float(round(total, 6))

            # No inventory link — use stored cost (not stock-based, unaffected)
            if row.ingredient_id is None:
                stored_cpu = Decimal(str(row.cost_per_unit or 0))
                total      = qty * stored_cpu
                return safe_float(round(stored_cpu, 6)), safe_float(round(total, 6))

            # Raw ingredient — live weighted avg with unit conversion
            batch_info = inventory_batch_map.get(row.ingredient_id)
            item_unit  = (batch_info["item_unit"] if batch_info else "").lower().strip()

            # pcs vs packet
            if ing_unit in PIECE_UNITS and item_unit in PACKET_UNITS:
                batches      = batches_by_ingredient.get(row.ingredient_id, [])
                total_pieces = Decimal("0")
                total_cost   = Decimal("0")

                for b in batches:
                    b_qty_remaining   = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
                    b_qty_received    = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
                    b_total_cost      = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")
                    pieces_per_packet = Decimal(str(b.pieces))             if b.pieces             else Decimal("1")

                    if b_qty_received > Decimal("0"):
                        remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
                    else:
                        remaining_cost = Decimal("0")

                    total_pieces += b_qty_remaining * pieces_per_packet
                    total_cost   += remaining_cost

                if total_pieces > Decimal("0"):
                    cost_per_piece = total_cost / total_pieces
                    total          = cost_per_piece * qty
                    return safe_float(round(cost_per_piece, 6)), safe_float(round(total, 6))

            # Standard unit conversion
            if batch_info and batch_info["avg_cost_per_item_unit"] > Decimal("0"):
                avg_cost = batch_info["avg_cost_per_item_unit"]

                try:
                    one_ing_unit_in_item_unit = convert_quantity_unit(Decimal("1"), ing_unit, item_unit)
                    cost_per_ing_unit = avg_cost * one_ing_unit_in_item_unit
                    total             = cost_per_ing_unit * qty
                    return (
                        safe_float(round(cost_per_ing_unit, 6)),
                        safe_float(round(total, 6)),
                    )
                except ValueError:
                    pass

            # Out of stock — no active batches with usable cost → zero cost (Case 2 fix)
            return 0.0, 0.0

        results = []
        for semi in semi_finished_list:
            rows = rows_by_semi[semi.id]

            ingredient_list = []
            production_cost = Decimal("0")

            for row in rows:
                is_semi   = bool(row.is_semi_finished)
                has_fixed = row.fixed_cost_amount is not None

                cost_per_unit, line_cost = calc_ingredient_cost(row)
                production_cost += Decimal(str(line_cost))

                if is_semi:
                    linked_semi   = semi_map.get(row.ingredient_id)
                    resolved_name = linked_semi.name if linked_semi else row.ingredient_name
                else:
                    resolved_name = row.ingredient_name

                ingredient_list.append({
                    "id":                row.id,
                    "ingredient_id":     row.ingredient_id,
                    "ingredient_name":   resolved_name,
                    "is_semi_finished":  is_semi,
                    "quantity_required": None if has_fixed else safe_float(row.quantity_required),
                    "unit":              row.unit,
                    "cost_per_unit":     cost_per_unit,
                    "fixed_cost_amount": float(row.fixed_cost_amount) if has_fixed else None,
                    "line_cost":         round(line_cost, 4),
                })

            yield_qty = (
                Decimal(str(safe_float(semi.yield_quantity)))
                if semi.yield_quantity
                else Decimal("0")
            )

            live_unit_cost = (
                production_cost / yield_qty
                if yield_qty > 0
                else Decimal("0")
            )

            results.append({
                "semi_finished_id": semi.id,
                "name":             semi.name,
                "yield_quantity":   safe_float(semi.yield_quantity),
                "yield_unit":       semi.unit,
                "unit_cost":        safe_float(round(live_unit_cost, 4)),
                "production_cost":  float(round(production_cost, 4)),
                "is_active":        semi.is_active,
                "ingredient_count": len(rows),
                "ingredients":      ingredient_list,
            })

        return {
            "success": True,
            "meta": {
                "total":       total,
                "page":        page,
                "page_size":   page_size,
                "total_pages": math.ceil(total / page_size) if total else 1,
                "search":      search,
            },
            "data": results,
        }

    except HTTPException:
        raise

    except SQLAlchemyError as db_error:
        logger.exception(f"DB error fetching semi-finished products: {db_error}")
        raise HTTPException(status_code=500, detail="Database error")

    except Exception as e:
        logger.exception(f"Unexpected error fetching semi-finished products: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")

@router.get("/semi-finished-ingredients/{semi_finished_id}", status_code=status.HTTP_200_OK)
def get_semi_finished_product_by_id(
    semi_finished_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        semi = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.id == semi_finished_id,
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).first()

        if not semi:
            raise HTTPException(status_code=404, detail="Semi-finished product not found")

        ingredients = db.query(SemiFinishedIngredient).filter(
            SemiFinishedIngredient.semi_finished_id == semi.id,
            SemiFinishedIngredient.tenant_id == tenant_id,
        ).all()

        total_batch_cost = round(
            sum(
                float(ing.fixed_cost_amount)
                if ing.fixed_cost_amount is not None
                else float(ing.cost_per_unit) * float(ing.quantity_required)
                for ing in ingredients
            ), 2
        )

        return {
            "success": True,
            "semi_finished_id": semi.id,
            "name": semi.name,
            "yield_quantity": float(semi.yield_quantity),
            "yield_unit": semi.unit,
            "unit_cost": float(semi.unit_cost),
            "total_batch_cost": total_batch_cost,
            "is_active": semi.is_active,
            "ingredient_count": len(ingredients),
            "ingredients": [
                {
                    "id":                ing.id,
                    "ingredient_id":     ing.ingredient_id,
                    "ingredient_name":   ing.ingredient_name,
                    "quantity_required": None if ing.fixed_cost_amount is not None else float(ing.quantity_required),
                    "unit":              ing.unit,
                    "cost_per_unit":     None if ing.fixed_cost_amount is not None else float(ing.cost_per_unit),
                    "fixed_cost_amount": float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None else None,
                    "line_cost":         round(
                        float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None
                        else float(ing.cost_per_unit) * float(ing.quantity_required), 2
                    ),
                }
                for ing in ingredients
            ],
        }

    except HTTPException:
        raise

    except SQLAlchemyError as db_error:
        logger.exception(f"DB error fetching semi-finished product {semi_finished_id}: {db_error}")
        raise HTTPException(status_code=500, detail="Database error")

    except Exception as e:
        logger.exception(f"Unexpected error fetching semi-finished product {semi_finished_id}: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")

# ── Endpoint ─────────────────────────────────────────────────────────────────
@router.patch("/update-semi-finished-ingredients/{semi_id}", status_code=status.HTTP_200_OK)
def update_semi_finished_product(
    semi_id: int,
    payload: UpdateSemiFinishedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # ── 1. Fetch existing semi-finished product ──────────────────────────
        semi = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.id == semi_id,
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).first()

        if not semi:
            raise HTTPException(status_code=404, detail="Semi-finished product not found")

        # ── Circular reference guard ─────────────────────────────────────────
        for item in (payload.ingredients or []):
            if item.is_semi_finished and item.ingredient_id == semi_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add a semi-finished product as an ingredient of itself (id={semi_id})",
                )

        sent_fields = payload.model_dump(exclude_unset=True)

        # ── 2. Update name ───────────────────────────────────────────────────
        if "name" in sent_fields:
            semi.name = payload.name

        # ── 3. Update yield fields ───────────────────────────────────────────
        if "yield_quantity" in sent_fields:
            semi.yield_quantity = payload.yield_quantity

        if "yield_unit" in sent_fields:
            semi.unit = payload.yield_unit

        # ── 4. Update ingredients ────────────────────────────────────────────
        if "ingredients" in sent_fields and payload.ingredients:

            auto_created_inventory = []

            # ── Step A: Resolve ingredient_id + unit-converted cost ──────────
            for idx, item in enumerate(payload.ingredients):
                print(f"\n  [Item {idx}] ingredient_id={item.ingredient_id}, name={item.ingredient_name!r}, "
                      f"is_semi={item.is_semi_finished}, qty={item.quantity_required}, unit={item.unit!r}")

                # ── Semi-finished ingredient ─────────────────────────────────
                if item.is_semi_finished:
                    if item.ingredient_id:
                        semi_ing = db.query(SemiFinishedProduct).filter(
                            SemiFinishedProduct.id == item.ingredient_id,
                            SemiFinishedProduct.tenant_id == tenant_id,
                            SemiFinishedProduct.is_active == True,
                        ).first()
                        if not semi_ing:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Semi-finished product with id={item.ingredient_id} not found",
                            )
                    elif item.ingredient_name:
                        semi_ing = db.query(SemiFinishedProduct).filter(
                            func.lower(SemiFinishedProduct.name) == item.ingredient_name.strip().lower(),
                            SemiFinishedProduct.tenant_id == tenant_id,
                            SemiFinishedProduct.is_active == True,
                        ).first()
                        if not semi_ing:
                            raise HTTPException(
                                status_code=404,
                                detail=f"Semi-finished product '{item.ingredient_name}' not found. "
                                       f"Please create it first before using it as an ingredient.",
                            )
                        item.ingredient_id = semi_ing.id
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="Provide ingredient_id or ingredient_name for semi-finished ingredient",
                        )

                    semi_yield_unit = (
                        semi_ing.unit.value
                        if hasattr(semi_ing.unit, "value")
                        else str(semi_ing.unit or "gm")
                    )
                    requested_unit = str(item.unit) if item.unit else semi_yield_unit
                    raw_unit_cost  = Decimal(str(semi_ing.unit_cost or 0))

                    try:
                        units_per_yield = convert_quantity_unit(
                            Decimal("1"),
                            from_unit=semi_yield_unit,
                            to_unit=requested_unit,
                        )

                        converted_cost = (
                            raw_unit_cost / units_per_yield
                            if units_per_yield > 0
                            else raw_unit_cost
                        )
                    except ValueError as ve:
                        logger.warning(
                            "Cannot convert unit cost from '%s' to '%s' for semi-finished "
                            "id=%s. Using raw unit_cost. Check ingredient units.",
                            semi_yield_unit, requested_unit, semi_ing.id,
                        )
                        converted_cost = raw_unit_cost

                    item._semi_unit_cost = converted_cost
                    item._semi_name      = semi_ing.name
                    continue  # ID resolved, skip inventory lookup

                # ── Normal ingredient: resolve by name if no id given ────────
                if item.ingredient_id is not None:
                    continue

                if not item.ingredient_name:
                    raise HTTPException(
                        status_code=400,
                        detail="ingredient_name is required when ingredient_id is not provided",
                    )

                matched_inv = db.query(Inventory).filter(
                    func.lower(Inventory.name) == item.ingredient_name.strip().lower(),
                    Inventory.tenant_id == tenant_id,
                ).first()

                if matched_inv:
                    if not matched_inv.is_active:
                        matched_inv.is_active = True
                        db.flush()
                        auto_created_inventory.append({
                            "id": matched_inv.id, "name": matched_inv.name, "action": "reactivated",
                        })
                    item.ingredient_id = matched_inv.id
                else:
                    new_inv = Inventory(
                        name      = item.ingredient_name.strip(),
                        unit      = str(item.unit) if item.unit else "unit",
                        unit_cost = 0,
                        is_active = True,
                        tenant_id = tenant_id,
                    )
                    db.add(new_inv)
                    db.flush()
                    item.ingredient_id = new_inv.id
                    auto_created_inventory.append({
                        "id": new_inv.id, "name": new_inv.name, "action": "created",
                    })

            # ── Step B: Build composite keys AFTER all IDs are resolved ──────
            payload_keys = [
                (item.ingredient_id, bool(item.is_semi_finished))
                for item in payload.ingredients
            ]

            # ── Step C: Delete rows NOT in payload using composite key ───────
            # FIX: Use bulk delete with synchronize_session="fetch" so SQLAlchemy's
            # identity map is updated immediately — prevents ghost rows in Step F.
            existing_all = db.query(SemiFinishedIngredient).filter(
                SemiFinishedIngredient.semi_finished_id == semi_id,
                SemiFinishedIngredient.tenant_id == tenant_id,
            ).all()

            ids_to_delete = [
                existing.id
                for existing in existing_all
                if (
                    existing.ingredient_id,
                    bool(getattr(existing, "is_semi_finished", False)),
                ) not in payload_keys
            ]

            if ids_to_delete:
                db.query(SemiFinishedIngredient).filter(
                    SemiFinishedIngredient.id.in_(ids_to_delete)
                ).delete(synchronize_session="fetch")   # ← FIX 1: keeps session cache in sync

            db.flush()
            db.expire_all()   # ← FIX 2: evict all cached objects so Step F re-queries fresh from DB

            # ── Step D: Fetch active inventory for normal ingredients ─────────
            normal_ids = [
                item.ingredient_id for item in payload.ingredients
                if not item.is_semi_finished
            ]

            inventory_items = db.query(Inventory).filter(
                Inventory.id.in_(normal_ids),
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).all() if normal_ids else []
            inventory_map = {inv.id: inv for inv in inventory_items}

            # Handle any still-missing normal IDs
            missing_ids = set(normal_ids) - set(inventory_map.keys())
            if missing_ids:
                for item in payload.ingredients:
                    if item.is_semi_finished or item.ingredient_id not in missing_ids:
                        continue

                    existing_inactive = db.query(Inventory).filter(
                        Inventory.id == item.ingredient_id,
                        Inventory.tenant_id == tenant_id,
                        Inventory.is_active == False,
                    ).first()

                    if existing_inactive:
                        existing_inactive.is_active = True
                        db.flush()
                        inventory_map[existing_inactive.id] = existing_inactive
                        auto_created_inventory.append({
                            "id": existing_inactive.id, "name": existing_inactive.name, "action": "reactivated",
                        })
                    else:
                        new_inv = Inventory(
                            name      = item.ingredient_name or f"Ingredient-{item.ingredient_id}",
                            unit      = str(item.unit) if item.unit else "unit",
                            unit_cost = 0,
                            is_active = True,
                            tenant_id = tenant_id,
                        )
                        db.add(new_inv)
                        db.flush()
                        item.ingredient_id = new_inv.id
                        inventory_map[new_inv.id] = new_inv
                        auto_created_inventory.append({
                            "id": new_inv.id, "name": new_inv.name, "action": "created",
                        })

            # ── Step E: Fetch ALL active non-expired batches ──────────────────
            all_batches = db.query(InventoryBatch).filter(
                InventoryBatch.inventory_item_id.in_(list(inventory_map.keys())),
                InventoryBatch.tenant_id == tenant_id,
                InventoryBatch.quantity_remaining > 0,
            ).all() if inventory_map else []

            batches_by_inv_id = defaultdict(list)
            for batch in all_batches:
                batches_by_inv_id[batch.inventory_item_id].append(batch)

            # ── Step F: Upsert using composite key (ingredient_id, is_semi_finished)
            # FIX: Because db.expire_all() was called after Step C's flush, these
            # queries now hit the DB fresh and will NOT see deleted rows.
            for idx, item in enumerate(payload.ingredients):
                is_semi  = bool(item.is_semi_finished)
                unit_str = str(item.unit) if item.unit else None

                existing_ingredient = db.query(SemiFinishedIngredient).filter(
                    SemiFinishedIngredient.semi_finished_id == semi_id,
                    SemiFinishedIngredient.ingredient_id    == item.ingredient_id,
                    SemiFinishedIngredient.tenant_id        == tenant_id,
                    SemiFinishedIngredient.is_semi_finished == is_semi,
                ).first()

                action = "UPDATE" if existing_ingredient else "INSERT"

                # ── Semi-finished product as ingredient ──────────────────────
                if is_semi:
                    semi_unit_cost = getattr(item, "_semi_unit_cost", Decimal("0"))
                    semi_name      = getattr(item, "_semi_name", item.ingredient_name or "")

                    print(f"  [Item {idx}] {action} semi-ingredient: name={semi_name!r}, "
                          f"qty={item.quantity_required}, unit={unit_str!r}, cost_per_unit={semi_unit_cost}")

                    if existing_ingredient:
                        existing_ingredient.quantity_required = item.quantity_required
                        existing_ingredient.unit              = unit_str
                        existing_ingredient.cost_per_unit     = semi_unit_cost
                        existing_ingredient.fixed_cost_amount = None
                        existing_ingredient.ingredient_name   = semi_name
                        existing_ingredient.is_semi_finished  = True
                    else:
                        db.add(SemiFinishedIngredient(
                            semi_finished_id  = semi_id,
                            tenant_id         = tenant_id,
                            ingredient_id     = item.ingredient_id,
                            ingredient_name   = semi_name,
                            quantity_required = item.quantity_required,
                            unit              = unit_str,
                            cost_per_unit     = semi_unit_cost,
                            fixed_cost_amount = None,
                            is_semi_finished  = True,
                        ))

                    print(f"  [Item {idx}]   line_cost = {item.quantity_required} × {semi_unit_cost} = "
                          f"{Decimal(str(item.quantity_required)) * semi_unit_cost}")
                    continue

                inv = inventory_map[item.ingredient_id]

                # ── Fixed cost item ──────────────────────────────────────────
                if inv.is_fixed_cost:
                    fixed_amt = Decimal(str(item.fixed_cost_amount or 0))

                    if existing_ingredient:
                        existing_ingredient.quantity_required = 1
                        existing_ingredient.unit              = unit_str
                        existing_ingredient.cost_per_unit     = Decimal("0")
                        existing_ingredient.fixed_cost_amount = fixed_amt
                        existing_ingredient.ingredient_name   = inv.name
                        existing_ingredient.is_semi_finished  = False
                    else:
                        db.add(SemiFinishedIngredient(
                            semi_finished_id  = semi_id,
                            tenant_id         = tenant_id,
                            ingredient_id     = item.ingredient_id,
                            ingredient_name   = inv.name,
                            quantity_required = 1,
                            unit              = unit_str,
                            cost_per_unit     = Decimal("0"),
                            fixed_cost_amount = fixed_amt,
                            is_semi_finished  = False,
                        ))
                    continue

                # ── Normal inventory ingredient ──────────────────────────────
                item_unit          = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit)
                fallback_cost      = Decimal(str(inv.unit_cost or 0))
                ingredient_batches = batches_by_inv_id.get(item.ingredient_id, [])

                print(f"  [Item {idx}] {action} normal ingredient: name={inv.name!r}, "
                      f"inv.unit={item_unit!r}, item.unit={unit_str!r}, "
                      f"fallback_cost={fallback_cost}, batch_count={len(ingredient_batches)}")

                cost_per_unit_converted, _ = calc_weighted_avg_cost(
                    ingredient_batches=ingredient_batches,
                    dish_unit=item.unit,
                    item_unit=item_unit,
                    fallback_cost=fallback_cost,
                )

                print(f"  [Item {idx}]   line_cost = {item.quantity_required} × {cost_per_unit_converted} = "
                      f"{Decimal(str(item.quantity_required)) * cost_per_unit_converted}")

                if existing_ingredient:
                    existing_ingredient.quantity_required = item.quantity_required
                    existing_ingredient.unit              = unit_str
                    existing_ingredient.cost_per_unit     = cost_per_unit_converted
                    existing_ingredient.fixed_cost_amount = None
                    existing_ingredient.ingredient_name   = inv.name
                    existing_ingredient.is_semi_finished  = False
                else:
                    db.add(SemiFinishedIngredient(
                        semi_finished_id  = semi_id,
                        tenant_id         = tenant_id,
                        ingredient_id     = item.ingredient_id,
                        ingredient_name   = inv.name,
                        quantity_required = item.quantity_required,
                        unit              = unit_str,
                        cost_per_unit     = cost_per_unit_converted,
                        fixed_cost_amount = None,
                        is_semi_finished  = False,
                    ))

            db.flush()

        # ── 5. Recalculate total cost from ALL remaining ingredients ──────────
        all_ingredients = db.query(SemiFinishedIngredient).filter(
            SemiFinishedIngredient.semi_finished_id == semi_id,
            SemiFinishedIngredient.tenant_id == tenant_id,
        ).all()

        total_cost = sum(
            Decimal(str(ing.fixed_cost_amount))
            if ing.fixed_cost_amount is not None
            else Decimal(str(ing.cost_per_unit)) * Decimal(str(ing.quantity_required))
            for ing in all_ingredients
        )

        for ing in all_ingredients:
            line = (
                float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None
                else float(ing.cost_per_unit) * float(ing.quantity_required)
            )
            print(f"  → {ing.ingredient_name!r}: qty={ing.quantity_required}, "
                  f"cpu={ing.cost_per_unit}, fixed={ing.fixed_cost_amount}, line={line:.4f}")

        # ── 6. Recalculate unit_cost based on yield_quantity ─────────────────
        yield_qty      = Decimal(str(semi.yield_quantity))
        semi.unit_cost = total_cost / yield_qty if yield_qty > 0 else Decimal("0")

        db.commit()
        db.refresh(semi)

        all_ingredients = db.query(SemiFinishedIngredient).filter(
            SemiFinishedIngredient.semi_finished_id == semi_id,
            SemiFinishedIngredient.tenant_id == tenant_id,
        ).all()

        for ing in all_ingredients:
            db.refresh(ing)

        return {
            "success":                True,
            "semi_finished_id":       semi.id,
            "name":                   semi.name,
            "yield_quantity":         float(semi.yield_quantity),
            "yield_unit":             semi.unit,
            "total_batch_cost":       float(total_cost),
            "unit_cost":              float(semi.unit_cost),
            "ingredient_count":       len(all_ingredients),
            "auto_created_inventory": auto_created_inventory if "auto_created_inventory" in locals() else [],
            "ingredients": [
                {
                    "id":                ing.id,
                    "ingredient_id":     ing.ingredient_id,
                    "ingredient_name":   ing.ingredient_name,
                    "is_semi_finished":  getattr(ing, "is_semi_finished", False),
                    "quantity_required": None if ing.fixed_cost_amount is not None else float(ing.quantity_required),
                    "unit":              ing.unit,
                    "cost_per_unit":     None if ing.fixed_cost_amount is not None else float(ing.cost_per_unit),
                    "fixed_cost_amount": float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None else None,
                    "line_cost":         float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None
                                         else float(Decimal(str(ing.cost_per_unit)) * Decimal(str(ing.quantity_required))),
                }
                for ing in all_ingredients
            ],
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"DB error updating semi-finished product: {db_error}")
        raise HTTPException(status_code=500, detail="Database error")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error updating semi-finished product: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
@router.delete("/semi-finished-ingredients/{semi_finished_id}", status_code=status.HTTP_200_OK)
def delete_semi_finished_product(
    semi_finished_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Soft-delete a semi-finished product (sets is_active = False).
    The product and its ingredients remain in the DB but are no longer visible or usable.
    """
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")
 
        tenant_id = current_user.tenant_id
 
        # 1. Fetch the product
        semi = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.id == semi_finished_id,
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).first()
 
        if not semi:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Semi-finished product with id {semi_finished_id} not found or already deleted.",
            )
 
        # 2. Soft delete
        semi.is_active = False
        db.commit()
 
        return {
            "success": True,
            "message": f"Semi-finished product '{semi.name}' (id: {semi_finished_id}) deleted successfully.",
            "semi_finished_id": semi_finished_id,
            "name": semi.name,
        }
 
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception(f"DB error deleting semi-finished product {semi_finished_id}: {e}")
        cause = getattr(e, "orig", None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DATABASE_ERROR",
                "message": "Database error while deleting.",
                "cause": str(cause) if cause else str(e),
            },
        )
 
    except HTTPException:
        raise
 
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error deleting semi-finished product {semi_finished_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": type(e).__name__,
                "message": "Unexpected server error.",
                "cause": str(e),
            },
        )
    
# # add both raw and semi-finished ingredients to dish all    
@router.delete("/dishes/{dish_id}")
def delete_dish(
    dish_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # ── 1. Fetch dish ────────────────────────────────────────────────────
        dish = db.query(Dish).filter(
            Dish.id == dish_id,
            Dish.tenant_id == tenant_id,
            Dish.is_active == True,
        ).first()
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")

        # ── 2. Soft delete dish only ─────────────────────────────────────────
        dish.is_active = False
        db.commit()

        return {
            "success": True,
            "message": f"Dish '{dish.name}' deleted successfully",
            "dish_id": dish_id,
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error deleting dish: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")         
    
@router.put("/update-dishes-with-ingredients/{dish_id}", status_code=status.HTTP_200_OK)
def update_dish(
    dish_id: int,
    payload: CreateDishWithIngredientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        if not payload.raw_ingredients and not payload.semi_finished_ingredients:
            raise HTTPException(
                status_code=400,
                detail="At least one raw or semi-finished ingredient is required",
            )

        # ── 1. Fetch existing dish ───────────────────────────────────────────
        dish = db.query(Dish).filter(
            Dish.id == dish_id,
            Dish.tenant_id == tenant_id,
            Dish.is_active == True,
        ).first()
        if not dish:
            raise HTTPException(status_code=404, detail="Dish not found")

        # ── 2. Validate dish type ────────────────────────────────────────────
        dish_type = db.query(DishType).filter(
            DishType.id == payload.type_id,
            DishType.tenant_id == tenant_id,
        ).first()
        if not dish_type:
            raise HTTPException(status_code=404, detail="Dish type not found")

        # ── 3. Validate raw ingredients ──────────────────────────────────────
        inventory_map     = {}
        batches_by_inv_id = {}

        if payload.raw_ingredients:
            from collections import defaultdict

            raw_ids = [item.ingredient_id for item in payload.raw_ingredients]
            inventory_items = db.query(Inventory).filter(
                Inventory.id.in_(raw_ids),
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).all()
            inventory_map = {inv.id: inv for inv in inventory_items}

            missing_raw = set(raw_ids) - set(inventory_map.keys())
            if missing_raw:
                raise HTTPException(
                    status_code=400,
                    detail=f"Inventory IDs not found: {sorted(missing_raw)}",
                )

            #  Fetch ALL batches — no expiry filter (expired batches still have valid cost)
            all_batches = db.query(InventoryBatch).filter(
                InventoryBatch.inventory_item_id.in_(raw_ids),
                InventoryBatch.tenant_id == tenant_id,
                InventoryBatch.quantity_remaining > 0,
            ).all()

            grouped_batches = defaultdict(list)
            for batch in all_batches:
                grouped_batches[batch.inventory_item_id].append(batch)
            batches_by_inv_id = dict(grouped_batches)

        # ── 4. Validate semi-finished ingredients ────────────────────────────
        semi_map = {}
        if payload.semi_finished_ingredients:
            semi_ids = [item.semi_finished_id for item in payload.semi_finished_ingredients]
            semi_items = db.query(SemiFinishedProduct).filter(
                SemiFinishedProduct.id.in_(semi_ids),
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            ).all()
            semi_map = {s.id: s for s in semi_items}

            missing_semi = set(semi_ids) - set(semi_map.keys())
            if missing_semi:
                raise HTTPException(
                    status_code=400,
                    detail=f"Semi-finished product IDs not found: {sorted(missing_semi)}",
                )

        # ── 5. Update dish fields ────────────────────────────────────────────
        dish.name          = payload.dish_name
        dish.type_id       = payload.type_id
        dish.selling_price = payload.selling_price

        # ── 6. Load existing ingredients into lookup map ─────────────────────
        existing_ingredients = db.query(DishIngredient).filter(
            DishIngredient.dish_id == dish_id,
            DishIngredient.tenant_id == tenant_id,
        ).all()

        existing_map = {}
        for ing in existing_ingredients:
            if ing.is_semi_finished:
                key = (None, ing.semi_finished_id)
            else:
                key = (ing.ingredient_id, None)
            existing_map[key] = ing

        # ── Unit sets for pcs vs packet detection ────────────────────────────
        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        # ── 7. Process raw ingredients (upsert) ──────────────────────────────
        total_dish_cost      = Decimal("0")
        zero_cost_items      = []
        upserted_ingredients = []

        for item in payload.raw_ingredients or []:
            inv = inventory_map[item.ingredient_id]

            #  Case 1 — Fixed cost item (Cylinder, Electricity, Charcoal etc.)
            if inv.is_fixed_cost:
                fixed_amt = Decimal(str(item.fixed_cost_amount or item.cost_per_unit or 0))
                is_zero   = fixed_amt == Decimal("0")

                if is_zero:
                    zero_cost_items.append(inv.name)

                line_cost        = fixed_amt  # ← direct ₹, no qty multiplication
                total_dish_cost += line_cost

                key = (item.ingredient_id, None)
                if key in existing_map:
                    ing                    = existing_map[key]
                    ing.quantity_required  = 1
                    ing.unit               = item.unit
                    ing.cost_per_unit      = Decimal("0")
                    ing.fixed_cost_amount  = fixed_amt
                    upserted_ingredients.append(ing)
                    del existing_map[key]
                else:
                    ing = DishIngredient(
                        dish_id           = dish.id,
                        ingredient_id     = item.ingredient_id,
                        semi_finished_id  = None,
                        ingredient_name   = inv.name,
                        quantity_required = 1,
                        unit              = item.unit,
                        cost_per_unit     = Decimal("0"),
                        fixed_cost_amount = fixed_amt,
                        is_semi_finished  = False,
                        tenant_id         = tenant_id,
                    )
                    db.add(ing)
                    upserted_ingredients.append(ing)
                continue  # ← skip Case 2 & 3 entirely

            #  Case 2 — Manual cost override (non-fixed, non-zero)
            elif item.cost_per_unit is not None and Decimal(str(item.cost_per_unit)) != Decimal("0"):
                item_unit_str        = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit or "")
                dish_unit_normalized = str(item.unit).lower().strip() if item.unit else ""
                item_unit_normalized = item_unit_str.lower().strip()

                if dish_unit_normalized in PIECE_UNITS and item_unit_normalized in PACKET_UNITS:
                    ingredient_batches = batches_by_inv_id.get(item.ingredient_id, [])
                    fallback_cost      = Decimal(str(inv.unit_cost or 0))

                    cost_per_unit_converted, is_zero = calc_weighted_avg_cost(
                        ingredient_batches=ingredient_batches,
                        dish_unit=item.unit,
                        item_unit=item_unit_str,
                        fallback_cost=fallback_cost,
                    )
                else:
                    cost_per_unit_converted = Decimal(str(item.cost_per_unit))
                    is_zero                 = cost_per_unit_converted == Decimal("0")

            #  Case 3 — Normal item — batch se calculate
            else:
                ingredient_batches = batches_by_inv_id.get(item.ingredient_id, [])
                fallback_cost      = Decimal(str(inv.unit_cost or 0))
                item_unit          = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit or "")

                cost_per_unit_converted, is_zero = calc_weighted_avg_cost(
                    ingredient_batches=ingredient_batches,
                    dish_unit=item.unit,
                    item_unit=item_unit,
                    fallback_cost=fallback_cost,
                )

            # Case 2 & 3 — qty based line cost
            line_cost        = cost_per_unit_converted * Decimal(str(item.quantity_required))
            total_dish_cost += line_cost

            if is_zero:
                zero_cost_items.append(inv.name)

            key = (item.ingredient_id, None)
            if key in existing_map:
                ing                   = existing_map[key]
                ing.quantity_required = item.quantity_required
                ing.unit              = item.unit
                ing.cost_per_unit     = cost_per_unit_converted
                ing.fixed_cost_amount = None  # ← not a fixed cost item
                upserted_ingredients.append(ing)
                del existing_map[key]
            else:
                ing = DishIngredient(
                    dish_id           = dish.id,
                    ingredient_id     = item.ingredient_id,
                    semi_finished_id  = None,
                    ingredient_name   = inv.name,
                    quantity_required = item.quantity_required,
                    unit              = item.unit,
                    cost_per_unit     = cost_per_unit_converted,
                    fixed_cost_amount = None,  # ← not a fixed cost item
                    is_semi_finished  = False,
                    tenant_id         = tenant_id,
                )
                db.add(ing)
                upserted_ingredients.append(ing)

        # ── 8. Process semi-finished ingredients (upsert) ────────────────────
        for item in payload.semi_finished_ingredients or []:
            sfp               = semi_map[item.semi_finished_id]
            cost_per_sfp_unit = Decimal(str(sfp.unit_cost or 0))
            sfp_unit          = sfp.unit.value if hasattr(sfp.unit, "value") else str(sfp.unit)

            try:
                ratio                   = convert_quantity_unit(Decimal("1"), item.unit, sfp_unit)
                cost_per_unit_converted = cost_per_sfp_unit * ratio
            except ValueError:
                cost_per_unit_converted = cost_per_sfp_unit

            line_cost        = cost_per_unit_converted * Decimal(str(item.quantity_required))
            total_dish_cost += line_cost

            if cost_per_sfp_unit == Decimal("0"):
                zero_cost_items.append(sfp.name)

            key = (None, item.semi_finished_id)
            if key in existing_map:
                ing                   = existing_map[key]
                ing.quantity_required = item.quantity_required
                ing.unit              = item.unit
                ing.cost_per_unit     = cost_per_unit_converted
                upserted_ingredients.append(ing)
                del existing_map[key]
            else:
                ing = DishIngredient(
                    dish_id=dish.id,
                    ingredient_id=None,
                    semi_finished_id=item.semi_finished_id,
                    ingredient_name=sfp.name,
                    quantity_required=item.quantity_required,
                    unit=item.unit,
                    cost_per_unit=cost_per_unit_converted,
                    is_semi_finished=True,
                    tenant_id=tenant_id,
                )
                db.add(ing)
                upserted_ingredients.append(ing)

        # ── 9. Delete ingredients not in payload ─────────────────────────────
        for ing in existing_map.values():
            db.delete(ing)

        # ── 10. Commit ───────────────────────────────────────────────────────
        db.commit()
        db.refresh(dish)

        # ── 11. Response ─────────────────────────────────────────────────────
        return {
            "success":         True,
            "dish_id":         dish.id,
            "dish_name":       dish.name,
            "type_id":         dish.type_id,
            "selling_price":   float(dish.selling_price),
            "total_dish_cost": float(total_dish_cost),
            "gross_profit":    float(dish.selling_price) - float(total_dish_cost),
            "updated_count":   len(upserted_ingredients),
            "warnings": (
                [f"No cost found for: {', '.join(zero_cost_items)} — cost defaulted to 0"]
                if zero_cost_items else []
            ),
            "ingredients": [
                {
                    "id":                 ing.id,
                    "dish_id":            ing.dish_id,
                    "ingredient_id":      ing.ingredient_id,
                    "semi_finished_id":   ing.semi_finished_id,
                    "ingredient_name":    ing.ingredient_name,
                    "is_semi_finished":   ing.is_semi_finished,
                    "quantity_required":  float(ing.quantity_required or 0),
                    "unit":               ing.unit,
                    "cost_per_unit":      float(ing.cost_per_unit or 0),
                    "fixed_cost_amount":  float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None else None,
                    "line_cost":          float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None
                                        else float(ing.cost_per_unit or 0) * float(ing.quantity_required or 0),
                }
                for ing in upserted_ingredients
            ],
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"Database error while updating dish: {db_error}")
        raise HTTPException(status_code=500, detail="Database error while updating dish")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while updating dish: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
REQUIRED_COLUMNS = {
    "dish_name",
    "dish_type_name",
    "quantity_required",
    "unit",
}
# At least one of these must be filled per row
INGREDIENT_COLUMNS = {
    "raw_ingredient_name",        # → resolves to Inventory
    "semi_finished_name",         # → resolves to SemiFinishedProduct
}

OPTIONAL_COLUMNS = {
    "selling_price",
    "standard_portion_size",
    "preparation_time_minutes",
    "fixed_cost_amount",
}
    
@router.post("/add-ingredients-to-dish", status_code=status.HTTP_201_CREATED)
def add_dish_to_ingredients(
    payload: CreateDishWithIngredientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id

        # ── 1. Ensure dish type exists — auto-create if missing ──────────────
        dish_type = db.query(DishType).filter(
            DishType.id == payload.type_id,
            DishType.tenant_id == tenant_id,
        ).first()

        if not dish_type and payload.type_id:
            dish_type = DishType(
                id=payload.type_id,
                name=payload.type_name or f"Type-{payload.type_id}",
                tenant_id=tenant_id,
                is_active=True,
            )
            db.add(dish_type)
            db.flush()

        # ── 2. Lookup raw ingredients ─────────────────────────────────────────
        inventory_map          = {}
        batches_by_ingredient  = {}
        auto_created_inventory = []

        if payload.raw_ingredients:
            from collections import defaultdict

            # only known IDs
            raw_ids = [
                item.ingredient_id
                for item in payload.raw_ingredients
                if item.ingredient_id is not None
            ]

            inventory_items = db.query(Inventory).filter(
                Inventory.id.in_(raw_ids),
                Inventory.tenant_id == tenant_id,
            ).all()
            inventory_map = {inv.id: inv for inv in inventory_items}

            for item in payload.raw_ingredients:
                # already resolved by ID
                if item.ingredient_id is not None and item.ingredient_id in inventory_map:
                    continue

                # name-only — check if already exists by name
                if item.ingredient_name:
                    name_lower = item.ingredient_name.strip().lower()
                    existing = db.query(Inventory).filter(
                        func.lower(Inventory.name) == name_lower,
                        Inventory.tenant_id == tenant_id,
                        Inventory.is_active == True,
                    ).first()

                    if existing:
                        item.ingredient_id = existing.id
                        inventory_map[existing.id] = existing
                    else:
                        new_inv = Inventory(
                            name=item.ingredient_name.strip(),
                            unit=item.unit,
                            unit_cost=0,
                            is_fixed_cost=False,
                            is_active=True,
                            tenant_id=tenant_id,
                        )
                        db.add(new_inv)
                        db.flush()
                        item.ingredient_id = new_inv.id
                        inventory_map[new_inv.id] = new_inv
                        auto_created_inventory.append(new_inv.name)

            # fetch all active batches using fully resolved IDs
            all_batches = db.query(InventoryBatch).filter(
                InventoryBatch.inventory_item_id.in_(list(inventory_map.keys())),
                InventoryBatch.tenant_id == tenant_id,
                InventoryBatch.quantity_remaining > 0,
            ).all()

            grouped = defaultdict(list)
            for batch in all_batches:
                grouped[batch.inventory_item_id].append(batch)
            batches_by_ingredient = dict(grouped)

        # ── 3. Lookup semi-finished ───────────────────────────────────────────
        semi_map          = {}
        auto_created_semi = []

        if payload.semi_finished_ingredients:
            semi_ids = [
                item.semi_finished_id
                for item in payload.semi_finished_ingredients
                if item.semi_finished_id is not None
            ]

            semi_items = db.query(SemiFinishedProduct).filter(
                SemiFinishedProduct.id.in_(semi_ids),
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            ).all()
            semi_map = {s.id: s for s in semi_items}

            for item in payload.semi_finished_ingredients:
                # already resolved by ID
                if item.semi_finished_id is not None and item.semi_finished_id in semi_map:
                    continue

                # name-only — check if already exists by name
                if item.semi_finished_name:
                    name_lower = item.semi_finished_name.strip().lower()
                    existing = db.query(SemiFinishedProduct).filter(
                        func.lower(SemiFinishedProduct.name) == name_lower,
                        SemiFinishedProduct.tenant_id == tenant_id,
                        SemiFinishedProduct.is_active == True,
                    ).first()

                    if existing:
                        item.semi_finished_id = existing.id
                        semi_map[existing.id] = existing
                    else:
                        new_sfp = SemiFinishedProduct(
                            name=item.semi_finished_name.strip(),
                            unit=item.unit,
                            unit_cost=0,
                            is_active=True,
                            tenant_id=tenant_id,
                        )
                        db.add(new_sfp)
                        db.flush()
                        item.semi_finished_id = new_sfp.id
                        semi_map[new_sfp.id] = new_sfp
                        auto_created_semi.append(new_sfp.name)

        # ── 4. Duplicate dish check ───────────────────────────────────────────
        existing_dish = db.query(Dish).filter(
            Dish.name == payload.dish_name,
            Dish.tenant_id == tenant_id,
            Dish.is_active == True,
        ).first()

        if existing_dish:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A dish named '{payload.dish_name}' already exists for this tenant.",
            )

        # ── 5. Create the dish ────────────────────────────────────────────────
        new_dish = Dish(
            name=payload.dish_name,
            type_id=dish_type.id if dish_type else payload.type_id,
            selling_price=payload.selling_price,
            is_active=True,
            tenant_id=tenant_id,
        )
        db.add(new_dish)
        db.flush()

        # ── 6. Process raw ingredients ────────────────────────────────────────
        new_ingredients = []
        total_dish_cost = Decimal("0")
        zero_cost_items = []

        for item in payload.raw_ingredients or []:
            inv = inventory_map.get(item.ingredient_id)

            if not inv:
                continue

            # Case 1 — Fixed cost item
            if inv.is_fixed_cost:
                fixed_amt = Decimal(str(item.fixed_cost_amount or item.cost_per_unit or 0))
                is_zero   = fixed_amt == Decimal("0")

                if is_zero:
                    zero_cost_items.append(inv.name)

                total_dish_cost += fixed_amt

                new_ingredients.append(
                    DishIngredient(
                        dish_id           = new_dish.id,
                        ingredient_id     = inv.id,
                        semi_finished_id  = None,
                        ingredient_name   = inv.name,
                        quantity_required = 1,
                        unit              = item.unit,
                        cost_per_unit     = Decimal("0"),
                        fixed_cost_amount = fixed_amt,
                        is_semi_finished  = False,
                        tenant_id         = tenant_id,
                    )
                )
                continue

            # Case 2 — Manual cost override
            elif item.cost_per_unit is not None and Decimal(str(item.cost_per_unit)) != Decimal("0"):
                item_unit_str        = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit or "")
                dish_unit_normalized = str(item.unit).lower().strip() if item.unit else ""
                item_unit_normalized = item_unit_str.lower().strip()

                PIECE_UNITS  = {"pcs", "piece", "pieces"}
                PACKET_UNITS = {"packet", "packets", "pkt"}

                if dish_unit_normalized in PIECE_UNITS and item_unit_normalized in PACKET_UNITS:
                    ingredient_batches           = batches_by_ingredient.get(item.ingredient_id, [])
                    fallback_cost                = Decimal(str(inv.unit_cost or 0))
                    cost_per_unit_converted, is_zero = calc_weighted_avg_cost(
                        ingredient_batches=ingredient_batches,
                        dish_unit=item.unit,
                        item_unit=item_unit_str,
                        fallback_cost=fallback_cost,
                    )
                else:
                    cost_per_unit_converted = Decimal(str(item.cost_per_unit))
                    is_zero                 = cost_per_unit_converted == Decimal("0")

            # Case 3 — Calculate from batch
            else:
                ingredient_batches           = batches_by_ingredient.get(item.ingredient_id, [])
                fallback_cost                = Decimal(str(inv.unit_cost or 0))
                item_unit                    = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit or "")
                cost_per_unit_converted, is_zero = calc_weighted_avg_cost(
                    ingredient_batches=ingredient_batches,
                    dish_unit=item.unit,
                    item_unit=item_unit,
                    fallback_cost=fallback_cost,
                )

            if is_zero:
                zero_cost_items.append(inv.name)

            line_cost        = cost_per_unit_converted * Decimal(str(item.quantity_required))
            total_dish_cost += line_cost

            new_ingredients.append(
                DishIngredient(
                    dish_id           = new_dish.id,
                    ingredient_id     = inv.id,
                    semi_finished_id  = None,
                    ingredient_name   = inv.name,
                    quantity_required = item.quantity_required,
                    unit              = item.unit,
                    cost_per_unit     = cost_per_unit_converted,
                    fixed_cost_amount = None,
                    is_semi_finished  = False,
                    tenant_id         = tenant_id,
                )
            )

        # ── 7. Process semi-finished ingredients ──────────────────────────────
        for item in payload.semi_finished_ingredients or []:
            sfp = semi_map.get(item.semi_finished_id)

            if not sfp:
                continue

            cost_per_sfp_unit = Decimal(str(sfp.unit_cost or 0))
            sfp_unit          = sfp.unit.value if hasattr(sfp.unit, "value") else str(sfp.unit)

            if cost_per_sfp_unit == Decimal("0"):
                zero_cost_items.append(sfp.name)

            try:
                units_per_sfp_unit      = convert_quantity_unit(Decimal("1"), sfp_unit, item.unit)
                cost_per_unit_converted = cost_per_sfp_unit / units_per_sfp_unit
            except (ValueError, ZeroDivisionError):
                cost_per_unit_converted = cost_per_sfp_unit

            line_cost        = cost_per_unit_converted * Decimal(str(item.quantity_required))
            total_dish_cost += line_cost

            new_ingredients.append(
                DishIngredient(
                    dish_id           = new_dish.id,
                    ingredient_id     = None,
                    semi_finished_id  = sfp.id,
                    ingredient_name   = sfp.name,
                    quantity_required = item.quantity_required,
                    unit              = item.unit,
                    cost_per_unit     = cost_per_unit_converted,
                    is_semi_finished  = True,
                    tenant_id         = tenant_id,
                )
            )

        # ── 8. Bulk insert & commit ───────────────────────────────────────────
        db.add_all(new_ingredients)
        db.commit()
        db.refresh(new_dish)

        # ── 9. Notes ──────────────────────────────────────────────────────────
        notes = []
        if zero_cost_items:
            notes.append(f"Zero cost defaulted for: {', '.join(zero_cost_items)}")
        if auto_created_inventory:
            notes.append(f"Auto-created inventory items: {', '.join(auto_created_inventory)}")
        if auto_created_semi:
            notes.append(f"Auto-created semi-finished products: {', '.join(auto_created_semi)}")

        # ── 10. Response ──────────────────────────────────────────────────────
        return {
            "success":         True,
            "dish_id":         new_dish.id,
            "dish_name":       new_dish.name,
            "type_id":         new_dish.type_id,
            "selling_price":   float(new_dish.selling_price),
            "total_dish_cost": float(total_dish_cost),
            "gross_profit":    float(new_dish.selling_price) - float(total_dish_cost),
            "added_count":     len(new_ingredients),
            "notes":           notes,
            "ingredients": [
                {
                    "id":                ing.id,
                    "dish_id":           ing.dish_id,
                    "ingredient_id":     ing.ingredient_id,
                    "semi_finished_id":  ing.semi_finished_id,
                    "ingredient_name":   ing.ingredient_name,
                    "is_semi_finished":  ing.is_semi_finished,
                    "quantity_required": float(ing.quantity_required or 0),
                    "unit":              ing.unit,
                    "cost_per_unit":     float(ing.cost_per_unit or 0),
                    "fixed_cost_amount": float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None else None,
                    "line_cost":         float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None
                                         else float(ing.cost_per_unit or 0) * float(ing.quantity_required or 0),
                }
                for ing in new_ingredients
            ],
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"Database error while creating dish: {db_error}")
        raise HTTPException(status_code=500, detail="Database error while creating dish")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while creating dish: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")
    
@router.post("/add-ingredients-to-dish-via-excel", status_code=status.HTTP_201_CREATED)
def create_dishes_from_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # ── 0. Auth ───────────────────────────────────────────────────────────
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")
        tenant_id = current_user.tenant_id

        # ── 1. File type check ────────────────────────────────────────────────
        if not file.filename.endswith((".xlsx", ".xls")):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only .xlsx or .xls files are allowed",
            )

        # ── 2. Parse Excel ────────────────────────────────────────────────────
        try:
            contents = file.file.read()
            df = pd.read_excel(BytesIO(contents))
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Failed to parse Excel file. Please check the file format",
            )

        # ── 3. Normalise column names ─────────────────────────────────────────
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

        # ── 4. Required columns must exist ────────────────────────────────────
        missing_cols = REQUIRED_COLUMNS - set(df.columns)
        if missing_cols:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns: {sorted(missing_cols)}",
            )

        present_ing_cols = INGREDIENT_COLUMNS & set(df.columns)
        if not present_ing_cols:
            raise HTTPException(
                status_code=400,
                detail="Excel must have at least one of: raw_ingredient_name, semi_finished_name",
            )

        # ── 5. Replace NaN → None ─────────────────────────────────────────────
        df = df.where(pd.notna(df), None)
        str_cols = ["dish_name", "dish_type_name", "raw_ingredient_name", "semi_finished_name", "unit"]
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()
                df[col] = df[col].replace("", None)

        # ── 6. Required fields must not be empty ──────────────────────────────
        for col in REQUIRED_COLUMNS:
            if df[col].isnull().any():
                raise HTTPException(
                    status_code=400,
                    detail=f"Column '{col}' has missing values. All rows must have this field",
                )

        # ── 7. Each row must have at least one ingredient name ────────────────
        def has_no_ingredient(row):
            raw  = row.get("raw_ingredient_name")
            semi = row.get("semi_finished_name")
            return (not raw or str(raw).strip() == "") and \
                   (not semi or str(semi).strip() == "")

        bad_rows = [i + 2 for i, row in df.iterrows() if has_no_ingredient(row)]
        if bad_rows:
            raise HTTPException(
                status_code=400,
                detail=f"Rows {bad_rows} have neither raw_ingredient_name nor semi_finished_name filled",
            )

        # ── 8. Normalize + validate unit values ───────────────────────────────
        def normalize_unit(raw):
            if not raw or str(raw).strip() == "" or str(raw).strip().lower() == "none":
                return None
            return UNIT_MAPPING.get(
                str(raw).strip().lower().replace(" ", ""),
                str(raw).strip()  # keep original if not in mapping (will fail validation below)
            )

        #  Normalize all units via UNIT_MAPPING before validation
        df["unit"] = df["unit"].apply(normalize_unit)

        valid_units = {u.value for u in UnitType}
        invalid_units = set(df["unit"].dropna().unique()) - valid_units
        if invalid_units:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid unit values: {sorted(invalid_units)}. Allowed: {sorted(valid_units)}",
            )

        # ── 9. Bulk resolve raw ingredient names → Inventory ─────────────────
        raw_names = []
        if "raw_ingredient_name" in df.columns:
            raw_names = (
                df["raw_ingredient_name"]
                .dropna()
                .str.strip()
                .str.lower()
                .unique()
                .tolist()
            )

        inventory_items = db.query(Inventory).filter(
            func.lower(Inventory.name).in_(raw_names),
            Inventory.tenant_id == tenant_id,
        ).all() if raw_names else []
        inventory_map = {inv.name.strip().lower(): inv for inv in inventory_items}

        auto_created_inventory = []
        for raw_name in raw_names:
            if raw_name not in inventory_map:
                matching_row = df[
                    df["raw_ingredient_name"].str.strip().str.lower() == raw_name
                ].iloc[0]
                #  unit already normalized via UNIT_MAPPING in step 8
                unit = str(matching_row["unit"]).strip()
                new_inv = Inventory(
                    name=raw_name,
                    unit=unit,
                    unit_cost=0,
                    is_active=True,
                    tenant_id=tenant_id,
                )
                db.add(new_inv)
                db.flush()
                inventory_map[raw_name] = new_inv
                auto_created_inventory.append(raw_name)

        # ── 10. Fetch ALL active batches per raw ingredient ───────────────────
        inv_ids = [inv.id for inv in inventory_map.values()]

        # ── 10. Fetch ALL active batches per raw ingredient ───────────────────
        all_batches = db.query(InventoryBatch).filter(
            InventoryBatch.inventory_item_id.in_(inv_ids),
            InventoryBatch.tenant_id == tenant_id,
            InventoryBatch.quantity_remaining > 0,
        ).all() if inv_ids else []

        from collections import defaultdict
        batches_by_inv_id: dict[int, list] = defaultdict(list)
        for b in all_batches:
            batches_by_inv_id[b.inventory_item_id].append(b)

        # ── 11. Bulk resolve semi-finished names → SemiFinishedProduct ────────
        semi_names = []
        if "semi_finished_name" in df.columns:
            semi_names = (
                df["semi_finished_name"]
                .dropna()
                .str.strip()
                .str.lower()
                .unique()
                .tolist()
            )

        semi_items = db.query(SemiFinishedProduct).filter(
            func.lower(SemiFinishedProduct.name).in_(semi_names),
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).all() if semi_names else []
        semi_map = {s.name.strip().lower(): s for s in semi_items}

        auto_created_semi = []
        for semi_name in semi_names:
            if semi_name not in semi_map:
                matching_row = df[
                    df["semi_finished_name"].str.strip().str.lower() == semi_name
                ].iloc[0]
                #  unit already normalized via UNIT_MAPPING in step 8
                unit = str(matching_row["unit"]).strip()
                new_sfp = SemiFinishedProduct(
                    name=semi_name,
                    unit=unit,
                    unit_cost=0,
                    is_active=True,
                    tenant_id=tenant_id,
                )
                db.add(new_sfp)
                db.flush()
                semi_map[semi_name] = new_sfp
                auto_created_semi.append(semi_name)

        # ── 12. Zero-cost warnings ────────────────────────────────────────────
        zero_cost_items = []
        for inv in inventory_map.values():
            batches = batches_by_inv_id.get(inv.id, [])
            has_cost = any(b.total_cost and b.total_cost > 0 for b in batches)
            if not has_cost and (not inv.unit_cost or inv.unit_cost == 0):
                zero_cost_items.append(inv.name)
        for sfp in semi_map.values():
            if not sfp.unit_cost or sfp.unit_cost == 0:
                zero_cost_items.append(sfp.name)

        # ── Helper: weighted avg cost per dish unit from all batches ──────────
        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        def calc_weighted_avg_cost(
            ingredient_batches: list,
            dish_unit: str,
            item_unit: str,
            fallback_cost: Decimal,
        ) -> tuple[Decimal, bool]:
            if not ingredient_batches:
                return fallback_cost, fallback_cost == Decimal("0")

            dish_unit_normalized = str(dish_unit).lower().strip() if dish_unit else ""
            item_unit_normalized = str(item_unit).lower().strip() if item_unit else ""

            #  pcs vs packet — derive cost from total_cost + pieces_per_packet
            if dish_unit_normalized in PIECE_UNITS and item_unit_normalized in PACKET_UNITS:
                total_pieces = Decimal("0")
                total_cost   = Decimal("0")

                for b in ingredient_batches:
                    b_qty_remaining   = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
                    b_qty_received    = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
                    b_total_cost      = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")
                    pieces_per_packet = Decimal(str(b.pieces))             if b.pieces             else Decimal("1")

                    if b_qty_received > Decimal("0"):
                        remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
                    else:
                        remaining_cost = Decimal("0")

                    total_pieces += b_qty_remaining * pieces_per_packet
                    total_cost   += remaining_cost

                if total_pieces > Decimal("0"):
                    cost_per_piece = total_cost / total_pieces
                    return cost_per_piece, cost_per_piece == Decimal("0")

            # ── Original logic untouched below ───────────────────────────────────────
            total_qty_in_item_unit = Decimal("0")
            total_cost             = Decimal("0")

            for b in ingredient_batches:
                b_unit          = b.unit.value if hasattr(b.unit, "value") else str(b.unit)
                b_qty_remaining = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
                b_qty_received  = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
                b_total_cost    = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")

                if b_qty_received > 0:
                    remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
                else:
                    remaining_cost = Decimal("0")

                try:
                    qty_in_item_unit = convert_quantity_unit(b_qty_remaining, b_unit, item_unit)
                except ValueError:
                    qty_in_item_unit = b_qty_remaining

                total_qty_in_item_unit += qty_in_item_unit
                total_cost             += remaining_cost

            if total_qty_in_item_unit == Decimal("0"):
                return fallback_cost, True

            avg_cost_per_item_unit = total_cost / total_qty_in_item_unit

            try:
                ratio              = convert_quantity_unit(Decimal("1"), dish_unit, item_unit)
                cost_per_dish_unit = avg_cost_per_item_unit * ratio
            except ValueError:
                cost_per_dish_unit = avg_cost_per_item_unit

            return cost_per_dish_unit, cost_per_dish_unit == Decimal("0")

        # ── 13. Group rows by dish_name ───────────────────────────────────────
        grouped: dict[str, dict] = {}
        for _, row in df.iterrows():
            dish_name = str(row["dish_name"]).strip()
            if dish_name not in grouped:
                grouped[dish_name] = {
                    "dish_name":                dish_name,
                    "type_name":                str(row["dish_type_name"]).strip(),
                    "selling_price":            safe_float(row.get("selling_price"), default=None),
                    "standard_portion_size":    row.get("standard_portion_size"),
                    "preparation_time_minutes": int(row["preparation_time_minutes"]) if row.get("preparation_time_minutes") else None,
                    "raw_ingredients":          [],
                    "semi_finished_ingredients": [],
                }

            #  unit already normalized in df["unit"] — no extra mapping needed
            qty      = float(row["quantity_required"])
            unit     = str(row["unit"]).strip()
            raw_name = str(row["raw_ingredient_name"]).strip().lower() if row.get("raw_ingredient_name") else None
            semi_name= str(row["semi_finished_name"]).strip().lower()  if row.get("semi_finished_name")  else None

            if raw_name:
                fixed_cost_amount = row.get("fixed_cost_amount")
                fixed_cost_amount = float(fixed_cost_amount) if fixed_cost_amount not in (None, "", "nan") else None

                grouped[dish_name]["raw_ingredients"].append({
                    "ingredient_name":   raw_name,
                    "quantity_required": qty,
                    "unit":              unit,
                    "fixed_cost_amount":  fixed_cost_amount,
                })
            if semi_name:
                grouped[dish_name]["semi_finished_ingredients"].append({
                    "ingredient_name":   semi_name,
                    "quantity_required": qty,
                    "unit":              unit,
                })

        # ── 14. At least one ingredient per dish ──────────────────────────────
        for dish_name, dish_data in grouped.items():
            if not dish_data["raw_ingredients"] and not dish_data["semi_finished_ingredients"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Dish '{dish_name}' must have at least one ingredient",
                )

        # ── 15. No duplicate ingredient names within same dish ────────────────
        for dish_name, dish_data in grouped.items():
            merged_raw = {}
            for item in dish_data["raw_ingredients"]:
                key = item["ingredient_name"].lower()
                if key in merged_raw:
                    merged_raw[key]["quantity_required"] += item["quantity_required"]
                else:
                    merged_raw[key] = dict(item)
            dish_data["raw_ingredients"] = list(merged_raw.values())

            # Merge semi-finished ingredients
            merged_semi = {}
            for item in dish_data["semi_finished_ingredients"]:
                key = item["ingredient_name"].lower()
                if key in merged_semi:
                    merged_semi[key]["quantity_required"] += item["quantity_required"]
                else:
                    merged_semi[key] = dict(item)
            dish_data["semi_finished_ingredients"] = list(merged_semi.values())

        # ── 16. Bulk resolve dish types ───────────────────────────────────────
        type_names_lower = {d["type_name"].lower() for d in grouped.values()}
        valid_types = db.query(DishType).filter(
            func.lower(DishType.name).in_(type_names_lower),
            DishType.tenant_id == tenant_id,
        ).all()
        type_name_map = {t.name.strip().lower(): t for t in valid_types}

        auto_created_types = []
        for type_name in type_names_lower:
            if type_name not in type_name_map:
                new_type = DishType(name=type_name, tenant_id=tenant_id)
                db.add(new_type)
                db.flush()
                type_name_map[type_name] = new_type
                auto_created_types.append(type_name)

        # ── 17. Create all dishes + ingredients ───────────────────────────────
        created_dishes        = []
        total_all_dishes_cost = Decimal("0")

        for dish_name, dish_data in grouped.items():
            dish_type = type_name_map[dish_data["type_name"].lower()]

            new_dish = Dish(
                name=dish_data["dish_name"],
                type_id=dish_type.id,
                selling_price=safe_float(dish_data["selling_price"]),
                standard_portion_size=dish_data["standard_portion_size"],
                preparation_time_minutes=dish_data["preparation_time_minutes"],
                is_active=True,
                tenant_id=tenant_id,
            )
            db.add(new_dish)
            db.flush()

            new_ingredients = []
            total_dish_cost = Decimal("0")

           # ── Raw ingredients ───────────────────────────────────────────────
            for item in dish_data["raw_ingredients"]:
                inv = inventory_map[item["ingredient_name"].lower()]

                #  Fixed cost item (Cylinder, Electricity, Charcoal)
                if inv.is_fixed_cost:
                    fixed_amt         = Decimal(str(item.get("fixed_cost_amount") or 0))
                    is_zero           = fixed_amt == Decimal("0")
                    total_dish_cost  += fixed_amt

                    if is_zero:
                        zero_cost_items.append(inv.name)

                    new_ingredients.append(DishIngredient(
                        dish_id           = new_dish.id,
                        ingredient_id     = inv.id,
                        semi_finished_id  = None,
                        ingredient_name   = item["ingredient_name"],
                        quantity_required = 1,
                        unit              = item["unit"],
                        cost_per_unit     = Decimal("0"),
                        fixed_cost_amount = fixed_amt,
                        is_semi_finished  = False,
                        tenant_id         = tenant_id,
                    ))
                    continue  # ← skip normal cost calculation

                #  Normal item — batch based calculation
                ingredient_batches = batches_by_inv_id.get(inv.id, [])
                fallback_cost      = Decimal(str(inv.unit_cost or 0))
                item_unit          = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit)

                cost_per_unit, is_zero = calc_weighted_avg_cost(
                    ingredient_batches=ingredient_batches,
                    dish_unit=item["unit"],
                    item_unit=item_unit,
                    fallback_cost=fallback_cost,
                )

                ingredient_qty        = Decimal(str(item["quantity_required"]))
                ingredient_total_cost = cost_per_unit * ingredient_qty
                total_dish_cost      += ingredient_total_cost

                if is_zero:
                    zero_cost_items.append(inv.name)

                new_ingredients.append(DishIngredient(
                    dish_id           = new_dish.id,
                    ingredient_id     = inv.id,
                    semi_finished_id  = None,
                    ingredient_name   = item["ingredient_name"],
                    quantity_required = item["quantity_required"],
                    unit              = item["unit"],
                    cost_per_unit     = cost_per_unit,
                    fixed_cost_amount = None,   # ← not a fixed cost item
                    is_semi_finished  = False,
                    tenant_id         = tenant_id,
                ))

            # ── Semi-finished ingredients ─────────────────────────────────────
            for item in dish_data["semi_finished_ingredients"]:
                sfp               = semi_map[item["ingredient_name"].lower()]
                cost_per_sfp_unit = Decimal(str(sfp.unit_cost or 0))
                sfp_unit          = sfp.unit.value if hasattr(sfp.unit, "value") else str(sfp.unit)

                try:
                    ratio         = convert_quantity_unit(Decimal("1"), item["unit"], sfp_unit)
                    cost_per_unit = cost_per_sfp_unit * ratio
                except ValueError:
                    cost_per_unit = cost_per_sfp_unit

                ingredient_qty        = Decimal(str(item["quantity_required"]))
                ingredient_total_cost = cost_per_unit * ingredient_qty
                total_dish_cost      += ingredient_total_cost

                new_ingredients.append(DishIngredient(
                    dish_id=new_dish.id,
                    ingredient_id=None,
                    semi_finished_id=sfp.id,
                    ingredient_name=item["ingredient_name"],
                    quantity_required=item["quantity_required"],
                    unit=item["unit"],
                    cost_per_unit=cost_per_unit,
                    is_semi_finished=True,
                    tenant_id=tenant_id,
                ))

            db.add_all(new_ingredients)
            db.flush()

            total_all_dishes_cost += total_dish_cost
            selling_price          = float(dish_data["selling_price"] or 0)

            created_dishes.append({
                "dish_id":         new_dish.id,
                "dish_name":       new_dish.name,
                "type_id":         dish_type.id,
                "selling_price":   selling_price,
                "total_dish_cost": float(total_dish_cost),
                "gross_profit":    selling_price - float(total_dish_cost),
                "added_count":     len(new_ingredients),
                "ingredients": [
                    {
                        "id":                    ing.id,
                        "dish_id":               ing.dish_id,
                        "ingredient_id":         ing.ingredient_id,
                        "semi_finished_id":      ing.semi_finished_id,
                        "ingredient_name":       ing.ingredient_name,
                        "is_semi_finished":      ing.is_semi_finished,
                        "quantity_required":     None if ing.fixed_cost_amount is not None else float(ing.quantity_required or 0),
                        "unit":                  ing.unit,
                        "cost_per_unit":         None if ing.fixed_cost_amount is not None else float(ing.cost_per_unit or 0),
                        "fixed_cost_amount":     float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None else None,
                        "ingredient_total_cost": float(ing.fixed_cost_amount) if ing.fixed_cost_amount is not None
                                                 else float(ing.cost_per_unit or 0) * float(ing.quantity_required or 0),
                    }
                    for ing in new_ingredients
                ],
            })

        db.commit()

        # ── 18. Build notes ───────────────────────────────────────────────────
        notes = []
        if zero_cost_items:
            notes.append(f"No cost found for: {', '.join(zero_cost_items)} — defaulted to 0")
        if auto_created_inventory:
            notes.append(f"Auto-created inventory items: {', '.join(auto_created_inventory)}")
        if auto_created_semi:
            notes.append(f"Auto-created semi-finished products: {', '.join(auto_created_semi)}")
        if auto_created_types:
            notes.append(f"Auto-created dish types: {', '.join(auto_created_types)}")

        return {
            "success":               True,
            "total_dishes_created":  len(created_dishes),
            "total_all_dishes_cost": float(total_all_dishes_cost),
            "notes":                 notes,
            "data":                  created_dishes,
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"Database error while uploading dishes from Excel: {db_error}")
        raise HTTPException(status_code=500, detail="Database error while creating dishes")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error while uploading dishes from Excel: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")

@router.put("/recalculate-semi-finished-cost/{semi_id}")
def recalculate_semi_finished_cost(
    semi_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  #  Add this
):
    try:
        if not current_user or not current_user.tenant_id:
            raise HTTPException(status_code=401, detail="Invalid user session")

        tenant_id = current_user.tenant_id  #  Now defined

        semi = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.id == semi_id,
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).first()

        if not semi:
            raise HTTPException(status_code=404, detail="Semi-finished product not found")

        ingredients = db.query(SemiFinishedIngredient).filter(
            SemiFinishedIngredient.semi_finished_id == semi_id,
            SemiFinishedIngredient.tenant_id == tenant_id,
        ).all()

        total_cost = Decimal("0")

        for ing in ingredients:
            #  Fixed cost item — use stored fixed amount directly
            if ing.fixed_cost_amount is not None:
                total_cost += Decimal(str(ing.fixed_cost_amount))
                continue

            inv = db.query(Inventory).filter(
                Inventory.id == ing.ingredient_id,
                Inventory.tenant_id == tenant_id,
            ).first()

            if not inv:
                continue

            item_unit_str = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit or "")

            batches = db.query(InventoryBatch).filter(
                InventoryBatch.inventory_item_id == ing.ingredient_id,
                InventoryBatch.tenant_id == tenant_id,
                InventoryBatch.quantity_remaining > 0,
            ).all()

            fallback_cost = Decimal(str(inv.unit_cost or 0))

            cost_per_unit, _ = calc_weighted_avg_cost(
                ingredient_batches=batches,
                dish_unit=ing.unit,
                item_unit=item_unit_str,
                fallback_cost=fallback_cost,
            )

            #  Update stored cost_per_unit on ingredient row
            ing.cost_per_unit = cost_per_unit
            total_cost += cost_per_unit * Decimal(str(ing.quantity_required))

        #  Recalculate and update unit_cost
        new_unit_cost = round(total_cost / Decimal(str(semi.yield_quantity)), 4) if semi.yield_quantity else Decimal("0")
        semi.unit_cost = new_unit_cost

        db.commit()

        return {
            "success": True,
            "semi_finished_id": semi_id,
            "name": semi.name,
            "old_unit_cost": float(semi.unit_cost),
            "new_unit_cost": float(new_unit_cost),
            "total_batch_cost": float(total_cost),
        }

    except SQLAlchemyError as db_error:
        db.rollback()
        logger.exception(f"DB error recalculating semi-finished cost: {db_error}")
        raise HTTPException(status_code=500, detail="Database error")

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error recalculating semi-finished cost: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error")

@router.post("/fix-semi-finished-costs")
def fix_semi_finished_costs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from collections import defaultdict

    tenant_id = current_user.tenant_id
    fixed_dishes = []
    errors = []

    # ── 1. Get all semi-finished dish ingredients for this tenant ─────────────
    semi_ingredients = db.query(DishIngredient).filter(
        DishIngredient.is_semi_finished == True,
        DishIngredient.tenant_id == tenant_id,
    ).all()

    if not semi_ingredients:
        return {"message": "No semi-finished ingredients found", "fixed": 0}

    # ── 2. Load all referenced SFPs ───────────────────────────────────────────
    sfp_ids  = list({ing.semi_finished_id for ing in semi_ingredients})
    sfp_map  = {
        s.id: s for s in db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.id.in_(sfp_ids),
            SemiFinishedProduct.tenant_id == tenant_id,
        ).all()
    }

    # ── 3. Fix each ingredient row ────────────────────────────────────────────
    dish_ids_to_recalc = set()

    for ing in semi_ingredients:
        sfp = sfp_map.get(ing.semi_finished_id)
        if not sfp:
            errors.append(f"SFP id={ing.semi_finished_id} not found, skipping")
            continue

        cost_per_sfp_unit = Decimal(str(sfp.unit_cost or 0))
        sfp_unit          = sfp.unit.value if hasattr(sfp.unit, "value") else str(sfp.unit)
        dish_unit         = ing.unit.value if hasattr(ing.unit, "value") else str(ing.unit or "")

        try:
            units_per_sfp_unit      = convert_quantity_unit(Decimal("1"), sfp_unit, dish_unit)
            correct_cost_per_unit   = cost_per_sfp_unit / units_per_sfp_unit
        except (ValueError, ZeroDivisionError) as e:
            errors.append(f"Unit convert failed for ing id={ing.id} ({sfp_unit}→{dish_unit}): {e}")
            correct_cost_per_unit = cost_per_sfp_unit  # fallback

        old_cost = ing.cost_per_unit
        ing.cost_per_unit = correct_cost_per_unit

        fixed_dishes.append({
            "dish_ingredient_id": ing.id,
            "dish_id":            ing.dish_id,
            "sfp_name":           sfp.name,
            "sfp_unit":           sfp_unit,
            "dish_unit":          dish_unit,
            "old_cost_per_unit":  float(old_cost or 0),
            "new_cost_per_unit":  float(correct_cost_per_unit),
            "quantity":           float(ing.quantity_required or 0),
        })

        dish_ids_to_recalc.add(ing.dish_id)

    # ── 4. Recalculate total_dish_cost for affected dishes ────────────────────
    # (only if your Dish model stores total_dish_cost as a column)
    # If it's computed at query time, skip this block.
    updated_dishes = []

    for dish_id in dish_ids_to_recalc:
        dish = db.query(Dish).filter(
            Dish.id == dish_id,
            Dish.tenant_id == tenant_id,
        ).first()

        if not dish:
            continue

        all_ings = db.query(DishIngredient).filter(
            DishIngredient.dish_id == dish_id
        ).all()

        new_total = Decimal("0")
        for i in all_ings:
            if i.fixed_cost_amount is not None:
                new_total += Decimal(str(i.fixed_cost_amount))
            else:
                new_total += Decimal(str(i.cost_per_unit or 0)) * Decimal(str(i.quantity_required or 0))

        # Uncomment if Dish has a stored total_dish_cost column:
        # dish.total_dish_cost = new_total

        updated_dishes.append({
            "dish_id":   dish_id,
            "new_total": float(new_total),
        })

    # ── 5. Commit ─────────────────────────────────────────────────────────────
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Commit failed: {str(e)}")

    return {
        "success":        True,
        "fixed_count":    len(fixed_dishes),
        "fixed_details":  fixed_dishes,
        "dish_recalc":    updated_dishes,
        "errors":         errors,
    }   

#--------------------------------combos api's--------------------------------    
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_combo(
    payload: ComboCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id

    try:
        combo = Combo(
            name=payload.name,
            type_id=payload.type_id,
            selling_price=payload.selling_price,
            tenant_id=tenant_id,
        )
        db.add(combo)
        db.flush()  # get combo.id

        # 2. Insert items
        for item_in in payload.items:
            snapshot = _resolve_item(
                db, tenant_id,
                item_in.dish_id,
                item_in.semi_finished_id,
                item_in.ingredient_id,
                user_unit=item_in.unit,
            )
            db.add(ComboItem(
                combo_id=combo.id,
                tenant_id=tenant_id,
                quantity=item_in.quantity,
                **snapshot,
            ))

        db.commit()
        db.refresh(combo)

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "committed":     True,
                "message":       "Combo created successfully.",
                "combo_id":      combo.id,
                "name":          combo.name,
                "selling_price": float(combo.selling_price) if combo.selling_price else None,
                "item_count":    len(payload.items),
            },
        )

    except HTTPException:
        db.rollback()
        raise

    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )
    
@router.get("/", status_code=status.HTTP_200_OK)
def list_combos(
    page:      int           = Query(1,    ge=1),
    page_size: int           = Query(20,   ge=1, le=100),
    search:    Optional[str] = Query(None, description="Search by combo name"),
    type_id:   Optional[int] = Query(None, description="Filter by category"),
    db:        Session       = Depends(get_db),
    current_user: User       = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id

    query = (
        db.query(Combo)
        .filter(Combo.tenant_id == tenant_id, Combo.is_active == True)
        .options(joinedload(Combo.combo_items))
    )

    if search:
        query = query.filter(Combo.name.ilike(f"%{search.strip()}%"))

    if type_id:
        query = query.filter(Combo.type_id == type_id)

    total_count = query.count()
    skip        = (page - 1) * page_size
    total_pages = (total_count + page_size - 1) // page_size

    combos = (
        query.order_by(Combo.created_at.desc())
        .offset(skip)
        .limit(page_size)
        .all()
    )

    # ── Unit sets (mirrors dish/semi-finished GET) ────────────────────────────
    PIECE_UNITS  = {"pcs", "piece", "pieces"}
    PACKET_UNITS = {"packet", "packets", "pkt"}

    # ── Step 1: Collect direct references from combo items ───────────────────
    combo_direct_ingredient_ids = set()
    combo_sfp_ids               = set()
    combo_dish_ids               = set()

    for combo in combos:
        for item in combo.combo_items:
            if item.fixed_cost_amount is not None:
                continue
            if item.dish_id is not None:
                combo_dish_ids.add(item.dish_id)
            elif item.semi_finished_id is not None:
                combo_sfp_ids.add(item.semi_finished_id)
            elif item.ingredient_id is not None:
                combo_direct_ingredient_ids.add(item.ingredient_id)

    raw_ingredient_ids_all = set(combo_direct_ingredient_ids)

    # ── Step 2: Fetch dishes referenced by combos, collect their dependencies ─
    dishes   = []
    dish_map = {}

    if combo_dish_ids:
        dishes = (
            db.query(Dish)
            .filter(Dish.id.in_(combo_dish_ids), Dish.tenant_id == tenant_id)
            .options(joinedload(Dish.dish_ingredient))
            .all()
        )
        dish_map = {d.id: d for d in dishes}

        for dish in dishes:
            for ing in dish.dish_ingredient:
                if ing.fixed_cost_amount is not None:
                    continue
                if ing.is_semi_finished and ing.semi_finished_id is not None:
                    combo_sfp_ids.add(ing.semi_finished_id)
                elif ing.ingredient_id is not None:
                    raw_ingredient_ids_all.add(ing.ingredient_id)

    # ── Step 3: Fetch SFPs referenced (direct + nested via dishes) ────────────
    sfp_rows_by_id = defaultdict(list)

    if combo_sfp_ids:
        sfp_ingredient_rows = (
            db.query(SemiFinishedIngredient)
            .filter(
                SemiFinishedIngredient.semi_finished_id.in_(combo_sfp_ids),
                SemiFinishedIngredient.tenant_id == tenant_id,
            )
            .all()
        )

        for row in sfp_ingredient_rows:
            sfp_rows_by_id[row.semi_finished_id].append(row)
            if (
                not row.is_semi_finished
                and row.fixed_cost_amount is None
                and row.ingredient_id is not None
            ):
                raw_ingredient_ids_all.add(row.ingredient_id)

    # ── Step 4: Build live weighted-avg cost map for ALL raw ingredients ─────
    inventory_batch_map   = {}  # ingredient_id -> {item_unit, avg_cost_per_item_unit}
    batches_by_ingredient = defaultdict(list)

    if raw_ingredient_ids_all:
        all_batches = (
            db.query(
                InventoryBatch.inventory_item_id,
                InventoryBatch.unit,
                InventoryBatch.quantity_received,
                InventoryBatch.quantity_remaining,
                InventoryBatch.total_cost,
                InventoryBatch.pieces,
            )
            .filter(
                InventoryBatch.inventory_item_id.in_(raw_ingredient_ids_all),
                InventoryBatch.tenant_id == tenant_id,
                InventoryBatch.quantity_remaining > 0,
                InventoryBatch.is_active == True,
            )
            .all()
        )

        for batch in all_batches:
            batches_by_ingredient[batch.inventory_item_id].append(batch)

        inventories = (
            db.query(Inventory)
            .filter(
                Inventory.id.in_(raw_ingredient_ids_all),
                Inventory.tenant_id == tenant_id,
            )
            .all()
        )

        inventory_unit_map = {
            inv.id: _normalize_unit(inv.unit)
            for inv in inventories
        }

        for ingredient_id, batches in batches_by_ingredient.items():
            item_unit = inventory_unit_map.get(ingredient_id, "gm")

            total_qty_in_item_unit = Decimal("0")
            total_cost             = Decimal("0")

            for batch in batches:
                batch_unit       = _normalize_unit(batch.unit)
                qty_remaining    = Decimal(str(batch.quantity_remaining)) if batch.quantity_remaining else Decimal("0")
                qty_received     = Decimal(str(batch.quantity_received))  if batch.quantity_received  else Decimal("0")
                batch_total_cost = Decimal(str(batch.total_cost))         if batch.total_cost         else Decimal("0")

                if qty_received > 0:
                    remaining_cost = (qty_remaining / qty_received) * batch_total_cost
                else:
                    remaining_cost = Decimal("0")

                try:
                    qty_in_item_unit = convert_quantity_unit(qty_remaining, batch_unit, item_unit)
                except ValueError:
                    qty_in_item_unit = qty_remaining

                total_qty_in_item_unit += qty_in_item_unit
                total_cost             += remaining_cost

            avg_cost_per_item_unit = (
                total_cost / total_qty_in_item_unit
                if total_qty_in_item_unit > 0
                else Decimal("0")
            )

            inventory_batch_map[ingredient_id] = {
                "item_unit":              item_unit,
                "avg_cost_per_item_unit": avg_cost_per_item_unit,
            }

    # ── Shared helper: live cost for a raw inventory ingredient ───────────────
    def calc_raw_ingredient_line(ingredient_id, unit_str, qty: Decimal, stored_cpu=None) -> tuple[Decimal, Decimal]:
        """Returns (cost_per_unit, line_cost) as Decimal."""
        ing_unit   = _normalize_unit(unit_str)
        batch_info = inventory_batch_map.get(ingredient_id)
        item_unit  = (batch_info["item_unit"] if batch_info else "").lower().strip()

        # pcs vs packet
        if ing_unit in PIECE_UNITS and item_unit in PACKET_UNITS:
            batches      = batches_by_ingredient.get(ingredient_id, [])
            total_pieces = Decimal("0")
            total_cost   = Decimal("0")

            for b in batches:
                b_qty_remaining   = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
                b_qty_received    = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
                b_total_cost      = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")
                pieces_per_packet = Decimal(str(b.pieces))             if b.pieces             else Decimal("1")

                if b_qty_received > Decimal("0"):
                    remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
                else:
                    remaining_cost = Decimal("0")

                total_pieces += b_qty_remaining * pieces_per_packet
                total_cost   += remaining_cost

            if total_pieces > Decimal("0"):
                cost_per_piece = total_cost / total_pieces
                return cost_per_piece, cost_per_piece * qty

        # Standard unit conversion
        if batch_info and batch_info["avg_cost_per_item_unit"] > Decimal("0"):
            avg_cost = batch_info["avg_cost_per_item_unit"]
            try:
                one_ing_unit_in_item_unit = convert_quantity_unit(Decimal("1"), ing_unit, item_unit)
                cpu = avg_cost * one_ing_unit_in_item_unit
                return cpu, cpu * qty
            except ValueError:
                pass

        # Fallback — stored cost
        cpu = Decimal(str(stored_cpu or 0))
        return cpu, cpu * qty

    # ── Step 5: Compute live unit_cost for each referenced SFP ─────────────────
    sfp_unit_cost_map = {}  # sfp_id -> Decimal unit_cost
    sfp_unit_map      = {}  # sfp_id -> normalized unit string

    if combo_sfp_ids:
        sfps = (
            db.query(SemiFinishedProduct)
            .filter(
                SemiFinishedProduct.id.in_(combo_sfp_ids),
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            )
            .all()
        )

        for sfp in sfps:
            rows = sfp_rows_by_id.get(sfp.id, [])
            production_cost = Decimal("0")

            for row in rows:
                if row.fixed_cost_amount is not None:
                    production_cost += Decimal(str(row.fixed_cost_amount))
                    continue

                qty = Decimal(str(row.quantity_required)) if row.quantity_required else Decimal("0")

                if row.is_semi_finished:
                    # Nested SFP within SFP — use stored cost_per_unit (not recursive)
                    cpu = Decimal(str(row.cost_per_unit or 0))
                    production_cost += qty * cpu
                elif row.ingredient_id is not None:
                    _, line_cost = calc_raw_ingredient_line(row.ingredient_id, row.unit, qty, row.cost_per_unit)
                    production_cost += line_cost
                else:
                    cpu = Decimal(str(row.cost_per_unit or 0))
                    production_cost += qty * cpu

            yield_qty = Decimal(str(safe_float(sfp.yield_quantity))) if sfp.yield_quantity else Decimal("0")
            sfp_unit_cost_map[sfp.id] = (
                production_cost / yield_qty if yield_qty > 0 else Decimal("0")
            )
            sfp_unit_map[sfp.id] = _normalize_unit(sfp.unit)

    # ── Step 6: Compute live total_dish_cost for each referenced dish ──────────
    dish_cost_map = {}  # dish_id -> Decimal total cost

    for dish in dishes:
        total_cost = Decimal("0")

        for ing in dish.dish_ingredient:
            if ing.fixed_cost_amount is not None:
                total_cost += Decimal(str(ing.fixed_cost_amount))
                continue

            qty       = Decimal(str(ing.quantity_required)) if ing.quantity_required else Decimal("0")
            dish_unit = _normalize_unit(ing.unit)

            if ing.is_semi_finished and ing.semi_finished_id is not None:
                live_cpu = sfp_unit_cost_map.get(ing.semi_finished_id, Decimal("0"))
                sfp_unit = sfp_unit_map.get(ing.semi_finished_id, "")

                if not sfp_unit or not dish_unit or sfp_unit == dish_unit:
                    cost_per_dish_unit = live_cpu
                else:
                    try:
                        sfp_units_per_dish_unit = convert_quantity_unit(Decimal("1"), dish_unit, sfp_unit)
                        cost_per_dish_unit = live_cpu * sfp_units_per_dish_unit
                    except (ValueError, ZeroDivisionError):
                        cost_per_dish_unit = live_cpu

                total_cost += cost_per_dish_unit * qty

            elif ing.ingredient_id is not None:
                _, line_cost = calc_raw_ingredient_line(ing.ingredient_id, ing.unit, qty, ing.cost_per_unit)
                total_cost += line_cost

            else:
                cpu = Decimal(str(ing.cost_per_unit or 0))
                total_cost += qty * cpu

        dish_cost_map[dish.id] = total_cost

    # ── Step 7: Per combo-item cost calculator ──────────────────────────────────
    def calc_combo_item_cost(item) -> tuple[Optional[float], float]:
        """Returns (cost_per_unit, line_cost)"""

        if item.fixed_cost_amount is not None:
            return None, float(item.fixed_cost_amount)

        qty       = Decimal(str(item.quantity)) if item.quantity is not None else Decimal("0")
        item_unit = _normalize_unit(item.unit)

        # ── Dish reference — live total_dish_cost as "per dish" cost ─────────
        if item.dish_id is not None:
            cpu = dish_cost_map.get(item.dish_id, Decimal(str(item.cost_per_unit or 0)))
            total = cpu * qty
            return safe_float(round(cpu, 6)), safe_float(round(total, 6))

        # ── Semi-finished reference — live unit_cost with unit conversion ─────
        if item.semi_finished_id is not None:
            live_cpu = sfp_unit_cost_map.get(item.semi_finished_id, Decimal("0"))
            sfp_unit = sfp_unit_map.get(item.semi_finished_id, "")

            if not sfp_unit or not item_unit or sfp_unit == item_unit:
                cpu = live_cpu
            else:
                try:
                    sfp_units_per_item_unit = convert_quantity_unit(Decimal("1"), item_unit, sfp_unit)
                    cpu = live_cpu * sfp_units_per_item_unit
                except (ValueError, ZeroDivisionError):
                    cpu = live_cpu

            total = cpu * qty
            return safe_float(round(cpu, 6)), safe_float(round(total, 6))

        # ── Raw inventory ingredient — live weighted avg + pcs/packet ─────────
        if item.ingredient_id is not None:
            cpu, total = calc_raw_ingredient_line(item.ingredient_id, item.unit, qty, item.cost_per_unit)
            return safe_float(round(cpu, 6)), safe_float(round(total, 6))

        # ── Fallback — stored cost ─────────────────────────────────────────────
        cpu = Decimal(str(item.cost_per_unit or 0))
        total = qty * cpu
        return safe_float(round(cpu, 6)), safe_float(round(total, 6))

    # ── Step 8: Build response ───────────────────────────────────────────────────
    result = []
    for combo in combos:
        item_results = []
        computed_price = Decimal("0")

        for item in combo.combo_items:
            cost_per_unit, line_cost = calc_combo_item_cost(item)
            computed_price += Decimal(str(line_cost))

            item_results.append({
                "id":                item.id,
                "item_name":         item.item_name,
                "item_type": (
                    "dish"          if item.dish_id          is not None else
                    "semi_finished" if item.semi_finished_id is not None else
                    "ingredient"
                ),
                "dish_id":           item.dish_id,
                "semi_finished_id":  item.semi_finished_id,
                "ingredient_id":     item.ingredient_id,
                "quantity":          safe_float(item.quantity),
                "unit":              item.unit,
                "cost_per_unit":     cost_per_unit,
                "fixed_cost_amount": float(item.fixed_cost_amount) if item.fixed_cost_amount is not None else None,
                "line_cost":         round(line_cost, 4),
            })

        result.append({
            "id":             combo.id,
            "name":           combo.name,
            "type_id":        combo.type_id,
            "type_name":      combo.type.name if combo.type else None,
            "selling_price":  float(combo.selling_price) if combo.selling_price else None,
            "computed_price": float(round(computed_price, 4)),
            "is_active":      combo.is_active,
            "item_count":     len(combo.combo_items),
            "items":          item_results,
        })

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "record": {
                "total_count":  total_count,
                "total_pages":  total_pages,
                "current_page": page,
                "page_size":    page_size,
                "has_next":     page < total_pages,
                "has_previous": page > 1,
            },
            "combos": result,
        },
    )

@router.delete("/{combo_id}", status_code=status.HTTP_200_OK)
def delete_combo(
    combo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id

    combo = db.query(Combo).filter(
        Combo.id == combo_id,
        Combo.tenant_id == tenant_id,
    ).first()

    if not combo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": "Combo not found."},
        )

    combo_name = combo.name
    db.delete(combo)  # cascade delete-orphan removes combo_items automatically
    db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "committed": True,
            "message":   f"Combo '{combo_name}' deleted successfully.",
            "combo_id":  combo_id,
        },
    )

@router.patch("/{combo_id}", status_code=status.HTTP_200_OK)
def update_combo(
    combo_id: int,
    payload:  ComboUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id

    combo = db.query(Combo).filter(
        Combo.id == combo_id,
        Combo.tenant_id == tenant_id,
    ).first()

    if not combo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "NOT_FOUND", "message": "Combo not found."},
        )

    if payload.name          is not None: combo.name          = payload.name
    if payload.type_id       is not None: combo.type_id       = payload.type_id
    if payload.is_active     is not None: combo.is_active     = payload.is_active
    if payload.selling_price is not None: combo.selling_price = payload.selling_price

    if payload.items is not None:

        if len(payload.items) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error_code": "EMPTY_ITEMS", "message": "Combo must have at least one item."},
            )

        combo.combo_items.clear()
        db.flush()

        for item_in in payload.items:
            snapshot = _resolve_item(
                db, tenant_id,
                item_in.dish_id,
                item_in.semi_finished_id,
                item_in.ingredient_id,
                user_unit=item_in.unit,
            )
            db.add(ComboItem(
                combo_id=combo.id,
                tenant_id=tenant_id,
                quantity=item_in.quantity,
                **snapshot,
            ))

    db.commit()
    db.refresh(combo)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "committed":      True,
            "message":        "Combo updated successfully.",
            "combo_id":       combo.id,
            "name":           combo.name,
            "type_id":        combo.type_id,
            "type_name":      combo.type.name if combo.type else None,
            "selling_price":  float(combo.selling_price) if combo.selling_price else None,
            "is_active":      combo.is_active,
            "item_count":     len(combo.combo_items),
            "items": [
                {
                    "id":               item.id,
                    "item_name":        item.item_name,
                    "item_type":        (
                        "dish"          if item.dish_id          is not None else
                        "semi_finished" if item.semi_finished_id is not None else
                        "ingredient"
                    ),
                    "dish_id":          item.dish_id,
                    "semi_finished_id": item.semi_finished_id,
                    "ingredient_id":    item.ingredient_id,
                    "quantity":         float(item.quantity),
                    "unit":             item.unit,
                    "cost_per_unit":    float(item.cost_per_unit),
                    "line_cost":        round(float(
                        item.fixed_cost_amount or (item.cost_per_unit * float(item.quantity))
                    ), 4),
                }
                for item in combo.combo_items
            ],
        },
    )
