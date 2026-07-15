"""
app/services/wastage_service.py
Wastage Management Service
"""
import calendar
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from typing import Optional, List, Tuple
from fastapi import HTTPException ,status
from sqlalchemy import case, func, and_, cast, Numeric, DateTime, or_
from sqlalchemy.orm import Session, joinedload

from app.api.v1.endpoints.dishes import _resolve_item
from app.models.wastage_model import Wastage, WastageType, WastageReason
from app.models.inventory import Inventory, InventoryBatch, InventoryTransaction, TransactionType
from app.models.dish import Combo, ComboItem, Dish, DishIngredient, DishPreparationBatchLog, SemiFinishedIngredient, SemiFinishedProduct
from app.models.users import User
from app.schemas.wastage import (
    GetWastageResponse, ItemTypeFilter, PeriodFilter, RecordInventoryWastage, RecordSemiFinishedWastage, RecordUnsoldDish,
    WastageOut, WastageRecord, WastageReport, WastageCategoryTotal, TopWastageItem, WastageBreakdownItem, WastageSummary
)
from app.utils.common_unit_converter import _normalize_unit, convert_quantity_unit
from app.utils.inventory_batch_helper import sync_inventory_totals
from app.utils.unit_converter import are_units_compatible, convert_to_base_unit, normalize_unit
from collections import defaultdict         
from collections import defaultdict as _defaultdict
from app.core.config import settings
import logging
from uuid import UUID
from decimal import Decimal, ROUND_HALF_UP



logger = logging.getLogger(__name__)
# Configurable threshold: perishable wastage alert if > 5% of total perishable inventory value
PERISHABLE_WASTAGE_ALERT_PCT = 5.0

PIECE_UNITS  = {"pcs", "piece", "pieces"}
PACKET_UNITS = {"packet", "packets", "pkt"}

def _wastage_ref(wastage_id: UUID) -> str:
    return f"wastage:{wastage_id}"

def _to_dt(d: Optional[date]) -> Optional[datetime]:
    """Convert date → datetime (midnight UTC) for transaction_date fields."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
class WastageService:

    @staticmethod
    def record_unsold_dish(
        db: Session,
        tenant_id: int,
        data: RecordUnsoldDish,
        user_id: int,
    ) -> dict:
        """
        Record unsold dish wastage and break down into constituent ingredient costs.
        Returns the parent wastage record plus breakdown items.
        """
        dish = db.query(Dish).filter(
            Dish.id == data.dish_id,
            Dish.tenant_id == tenant_id,
        ).first()
        if not dish:
            raise ValueError(f"Dish {data.dish_id} not found")

        # Get dish ingredients for cost breakdown
        ingredients = db.query(DishIngredient).filter(
            DishIngredient.dish_id == data.dish_id,
            DishIngredient.tenant_id == tenant_id,
        ).all()

        # Calculate per-dish cost from ingredients
        total_ingredient_cost_per_dish = sum(
            Decimal(str(ing.quantity_required)) * Decimal(str(ing.cost_per_unit or 0))
            for ing in ingredients
        )
        total_dish_cost = total_ingredient_cost_per_dish * data.quantity_unsold

        disposal_ts = data.disposal_timestamp or datetime.now(timezone.utc)

        # Parent wastage record (the dish-level entry)
        parent = Wastage(
            tenant_id=tenant_id,
            wastage_type=WastageType.DISH,
            dish_id=data.dish_id,
            quantity_wasted=float(data.quantity_unsold),
            unit="portion",
            unit_cost=float(total_ingredient_cost_per_dish),
            cost_value=float(total_dish_cost),
            wastage_reason=WastageReason.UNSOLD_DISH,
            wastage_date=disposal_ts,
            notes=data.notes,
            is_breakdown=False,
            recorded_by_user_id=user_id,
        )
        db.add(parent)
        db.flush()  # get parent.id before adding children

        # Ingredient breakdown rows
        breakdown_items = []
        for ing in ingredients:
            qty_wasted = Decimal(str(ing.quantity_required)) * data.quantity_unsold
            ing_unit_cost = Decimal(str(ing.cost_per_unit or 0))
            ing_cost_value = qty_wasted * ing_unit_cost

            child = Wastage(
                tenant_id=tenant_id,
                wastage_type=WastageType.INVENTORY,
                inventory_item_id=ing.ingredient_id if not ing.is_semi_finished else None,
                dish_id=data.dish_id,
                quantity_wasted=float(qty_wasted),
                unit=ing.unit,
                unit_cost=float(ing_unit_cost),
                cost_value=float(ing_cost_value),
                wastage_reason=WastageReason.UNSOLD_DISH,
                wastage_date=disposal_ts,
                notes=f"Breakdown of unsold dish: {dish.name}",
                is_breakdown=True,
                parent_wastage_id=parent.id,
                recorded_by_user_id=user_id,
            )
            db.add(child)
            breakdown_items.append({
                "ingredient_name": ing.ingredient_name,
                "quantity_wasted": float(qty_wasted),
                "unit": ing.unit,
                "unit_cost": float(ing_unit_cost),
                "cost_value": float(ing_cost_value),
            })

        db.commit()
        db.refresh(parent)

        return {
            "wastage_id": parent.id,
            "dish_name": dish.name,
            "quantity_unsold": float(data.quantity_unsold),
            "total_dish_cost": float(total_dish_cost),
            "disposal_timestamp": disposal_ts,
            "ingredient_breakdown": breakdown_items,
        }

    @staticmethod
    def record_bulk_unsold_dishes(
        db: Session,
        tenant_id: int,
        dishes: list,
        user_id: int,
    ) -> dict:
        results = []
        total_cost = Decimal(0)
        for dish_data in dishes:
            result = WastageService.record_unsold_dish(db, tenant_id, dish_data, user_id)
            results.append(result)
            total_cost += Decimal(str(result["total_dish_cost"]))

        return {
            "total_dishes": len(results),
            "total_wastage_cost": float(total_cost),
            "results": results,
        }

    @staticmethod
    def auto_mark_expired_batches(
        db: Session,
        tenant_id: int,
        user_id: int,
    ) -> dict:
        """
        Scan all active batches and auto-create wastage records for expired ones
        that haven't been marked yet. Called by a scheduled task.
        """
        today = date.today()

        # Find expired batches with remaining quantity, not yet wastaged
        expired_batches = db.query(InventoryBatch).filter(
            InventoryBatch.tenant_id == tenant_id,
            InventoryBatch.is_active == True,
            InventoryBatch.expiry_date < today,
            InventoryBatch.quantity_remaining > 0,
        ).all()

        created = []
        for batch in expired_batches:
            # Check if already has an expiry wastage record for this batch
            existing = db.query(Wastage).filter(
                Wastage.inventory_batch_id == batch.id,
                Wastage.wastage_reason == WastageReason.EXPIRY,
            ).first()
            if existing:
                continue

            item = db.query(Inventory).filter(Inventory.id == batch.inventory_item_id).first()
            if not item:
                continue

            unit_cost = Decimal(str(batch.unit_cost or item.unit_cost or 0))
            qty = Decimal(str(batch.quantity_remaining))

            wastage = Wastage(
                tenant_id=tenant_id,
                wastage_type=WastageType.INVENTORY,
                inventory_item_id=batch.inventory_item_id,
                inventory_batch_id=batch.id,
                quantity_wasted=float(qty),
                unit=item.unit,
                unit_cost=float(unit_cost),
                cost_value=float(qty * unit_cost),
                wastage_reason=WastageReason.EXPIRY,
                wastage_date=datetime.now(timezone.utc),
                notes=f"Auto-flagged: Batch {batch.batch_number} expired on {batch.expiry_date}",
                recorded_by_user_id=user_id,
            )
            db.add(wastage)

            # Zero out the batch
            batch.quantity_remaining = 0
            item.current_quantity = max(0, float(
                Decimal(str(item.current_quantity or 0)) - qty
            ))

            created.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "item_name": item.name,
                "quantity_wasted": float(qty),
            })

        db.commit()
        return {"auto_flagged_count": len(created), "records": created}

    @staticmethod
    def get_expiry_alerts(
        db: Session,
        tenant_id: int,
        threshold_days: int = 3,
    ) -> dict:
        """
        Return items with batches expiring within threshold_days.
        Used for 'Use First' recommendations.
        """
        from datetime import timedelta
        cutoff = date.today() + timedelta(days=threshold_days)

        batches = db.query(InventoryBatch).filter(
            InventoryBatch.tenant_id == tenant_id,
            InventoryBatch.is_active == True,
            InventoryBatch.expiry_date <= cutoff,
            InventoryBatch.expiry_date >= date.today(),
            InventoryBatch.quantity_remaining > 0,
        ).order_by(InventoryBatch.expiry_date.asc()).all()

        alerts = []
        for batch in batches:
            item = db.query(Inventory).filter(Inventory.id == batch.inventory_item_id).first()
            days_left = (batch.expiry_date - date.today()).days
            alerts.append({
                "batch_id": batch.id,
                "batch_number": batch.batch_number,
                "item_id": batch.inventory_item_id,
                "item_name": item.name if item else "Unknown",
                "expiry_date": batch.expiry_date,
                "days_until_expiry": days_left,
                "quantity_remaining": float(batch.quantity_remaining),
                "unit": batch.unit or (item.unit if item else None),
                "use_first": True,
                "urgency": "CRITICAL" if days_left == 0 else "HIGH" if days_left <= 1 else "MEDIUM",
            })

        return {
            "threshold_days": threshold_days,
            "total_alerts": len(alerts),
            "alerts": alerts,
        }

    @staticmethod
    def _aggregate_raw_ingredients(ingredients: list) -> list:
        """
        Merge rows that share the same ingredient_id (multi-batch duplicates),
        summing qty_deducted and ingredient_cost.
        Rows with qty_deducted == 0 AND ingredient_cost == 0 are dropped.
        Rows with ingredient_id == None are kept as-is (combo dish/sfp placeholders).
        """
        merged: dict = {}       # ingredient_id → merged row
        none_id_rows: list = [] # rows without ingredient_id (keep as-is)

        for row in ingredients:
            ing_id = row.get("ingredient_id")
            if ing_id is None:
                none_id_rows.append(row)
                continue

            if ing_id not in merged:
                merged[ing_id] = row.copy()
            else:
                merged[ing_id]["qty_deducted"]    = round(merged[ing_id]["qty_deducted"]    + row["qty_deducted"],    6)
                merged[ing_id]["ingredient_cost"] = round(merged[ing_id]["ingredient_cost"] + row["ingredient_cost"], 4)

        # Drop pure-zero rows (ghost batch entries)
        result = [
            r for r in merged.values()
            if not (r["qty_deducted"] == 0 and r["ingredient_cost"] == 0)
        ]
        return result + none_id_rows

    @staticmethod
    def get_wastage_records(
        db: Session,
        tenant_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        wastage_type: Optional[WastageType] = None,
        wastage_reason: Optional[WastageReason] = None,
        include_breakdown: bool = False,
        search: Optional[str] = None,
    ) -> List[dict]:
        """List wastage records with optional filters."""

        # ── Types that can carry a breakdown ─────────────────────────────────────
        BREAKDOWN_TYPES = (WastageType.DISH, WastageType.SEMI_FINISHED, WastageType.COMBO)

        query = db.query(Wastage).filter(
            Wastage.tenant_id == tenant_id,
            Wastage.is_breakdown == False,
        ).options(
            joinedload(Wastage.inventory_item),
            joinedload(Wastage.inventory_batch),
            joinedload(Wastage.semi_finished_product),
            joinedload(Wastage.semi_finished_batch),
            joinedload(Wastage.dish),
            joinedload(Wastage.combo),
            joinedload(Wastage.recorded_by),
        )

        if start_date:
            query = query.filter(func.date(Wastage.wastage_date) >= start_date)
        if end_date:
            query = query.filter(func.date(Wastage.wastage_date) <= end_date)
        if wastage_type:
            query = query.filter(Wastage.wastage_type == wastage_type)
        if wastage_reason:
            query = query.filter(Wastage.wastage_reason == wastage_reason)

        records = query.order_by(Wastage.wastage_date.desc()).all()

        # ── Fetch ALL breakdown children in ONE query ─────────────────────────────
        breakdown_parent_ids = [w.id for w in records if w.wastage_type in BREAKDOWN_TYPES]

        breakdown_map: dict = {}
        if breakdown_parent_ids:
            breakdown_records = (
                db.query(Wastage)
                .filter(
                    Wastage.tenant_id == tenant_id,
                    Wastage.is_breakdown == True,
                    Wastage.parent_wastage_id.in_(breakdown_parent_ids),
                )
                .options(
                    joinedload(Wastage.inventory_item),
                    joinedload(Wastage.semi_finished_product),
                    joinedload(Wastage.dish),
                )
                .all()
            )
            for br in breakdown_records:
                breakdown_map.setdefault(br.parent_wastage_id, []).append(br)

        # ── Summary accumulators ──────────────────────────────────────────────────
        result = []
        total_cost = 0.0
        dish_cost_map: dict[str, float] = {}
        combo_cost_map: dict[str, float] = {}
        inventory_cost_map: dict[str, float] = {}

        for w in records:
            item_name    = None
            dish_name    = None
            combo_name   = None
            batch_number = None

            if w.wastage_type == WastageType.INVENTORY:
                item_name    = w.inventory_item.name           if w.inventory_item  else None
                batch_number = w.inventory_batch.batch_number  if w.inventory_batch else None

            elif w.wastage_type == WastageType.SEMI_FINISHED:
                item_name    = w.semi_finished_product.name       if w.semi_finished_product else None
                batch_number = w.semi_finished_batch.batch_number if w.semi_finished_batch  else None

            elif w.wastage_type == WastageType.DISH:
                dish_name = w.dish.name if w.dish else None

            elif w.wastage_type == WastageType.COMBO:
                combo_name = w.combo.name if w.combo else None

            recorded_by = w.recorded_by.full_name if w.recorded_by else None
            record_cost = float(w.cost_value) if w.cost_value else 0.0
            total_cost += record_cost

            if dish_name:
                dish_cost_map[dish_name] = dish_cost_map.get(dish_name, 0.0) + record_cost
            if combo_name:
                combo_cost_map[combo_name] = combo_cost_map.get(combo_name, 0.0) + record_cost
            if item_name and w.wastage_type in (WastageType.INVENTORY, WastageType.SEMI_FINISHED):
                inventory_cost_map[item_name] = inventory_cost_map.get(item_name, 0.0) + record_cost

            # ── Per-type breakdown builder ────────────────────────────────────────
            breakdown = None
            children  = breakdown_map.get(w.id, [])

            # ── DISH breakdown ────────────────────────────────────────────────────
            if w.wastage_type == WastageType.DISH and children:
                raw_ingredients: list = []
                semi_finished_map: dict = {}

                for br in children:
                    br_cost = float(br.cost_value) if br.cost_value else 0.0

                    if br.semi_finished_product_id:
                        sfp_id = br.semi_finished_product_id
                        if sfp_id not in semi_finished_map:
                            semi_finished_map[sfp_id] = {
                                "semi_finished_id":   sfp_id,
                                "semi_finished_name": br.semi_finished_product.name if br.semi_finished_product else None,
                                "semi_finished_qty":  float(br.semi_finished_qty) if br.semi_finished_qty else None,
                                "semi_finished_unit": br.semi_finished_unit_used,
                                "source":             "semi_finished",
                                "sub_ingredients":    [],
                                "semi_finished_cost": 0.0,
                            }
                        ing_name = br.inventory_item.name if br.inventory_item else None
                        semi_finished_map[sfp_id]["sub_ingredients"].append({
                            "ingredient_id":   br.inventory_item_id,
                            "ingredient_name": ing_name,
                            "qty_deducted":    float(br.quantity_wasted),
                            "unit":            br.unit,
                            "ingredient_cost": round(br_cost, 2),
                        })
                        semi_finished_map[sfp_id]["semi_finished_cost"] += br_cost

                        if ing_name:
                            inventory_cost_map[ing_name] = inventory_cost_map.get(ing_name, 0.0) + br_cost

                    else:
                        ing_name = br.inventory_item.name if br.inventory_item else None
                        raw_ingredients.append({
                            "ingredient_id":   br.inventory_item_id,
                            "ingredient_name": ing_name,
                            "qty_deducted":    float(br.quantity_wasted),
                            "unit":            br.unit,
                            "ingredient_cost": round(br_cost, 2),
                            "source":          "raw",
                        })
                        if ing_name:
                            inventory_cost_map[ing_name] = inventory_cost_map.get(ing_name, 0.0) + br_cost

                # Aggregate sub_ingredients inside each semi-finished group
                for sfp in semi_finished_map.values():
                    sfp["sub_ingredients"] = WastageService._aggregate_raw_ingredients(sfp["sub_ingredients"])
                    sfp["semi_finished_cost"] = round(sfp["semi_finished_cost"], 2)

                breakdown = WastageService._aggregate_raw_ingredients(raw_ingredients) + list(semi_finished_map.values())

            # ── SEMI_FINISHED breakdown ───────────────────────────────────────────
            # Children whose semi_finished_product_id == parent's own id are direct
            # raw ingredients of the parent. Children with a DIFFERENT
            # semi_finished_product_id are truly nested semi-finished items.
            elif w.wastage_type == WastageType.SEMI_FINISHED and children:
                raw_ingredients: list = []
                semi_finished_map: dict = {}
                parent_sfp_id = w.semi_finished_product_id

                for br in children:
                    br_cost = float(br.cost_value) if br.cost_value else 0.0

                    # ── Truly nested semi-finished (different id from parent) ──────
                    if (
                        br.semi_finished_product_id
                        and br.semi_finished_product_id != parent_sfp_id
                    ):
                        sfp_id = br.semi_finished_product_id
                        if sfp_id not in semi_finished_map:
                            semi_finished_map[sfp_id] = {
                                "semi_finished_id":   sfp_id,
                                "semi_finished_name": br.semi_finished_product.name if br.semi_finished_product else None,
                                "semi_finished_qty":  float(br.semi_finished_qty) if br.semi_finished_qty else None,
                                "semi_finished_unit": br.semi_finished_unit_used,
                                "source":             "semi_finished",
                                "sub_ingredients":    [],
                                "semi_finished_cost": 0.0,
                            }
                        ing_name = br.inventory_item.name if br.inventory_item else None
                        semi_finished_map[sfp_id]["sub_ingredients"].append({
                            "ingredient_id":   br.inventory_item_id,
                            "ingredient_name": ing_name,
                            "qty_deducted":    float(br.quantity_wasted),
                            "unit":            br.unit,
                            "ingredient_cost": round(br_cost, 2),
                        })
                        semi_finished_map[sfp_id]["semi_finished_cost"] += br_cost

                        if ing_name:
                            inventory_cost_map[ing_name] = inventory_cost_map.get(ing_name, 0.0) + br_cost

                    # ── Direct raw ingredient of the parent semi-finished ──────────
                    else:
                        ing_name = br.inventory_item.name if br.inventory_item else None
                        raw_ingredients.append({
                            "ingredient_id":   br.inventory_item_id,
                            "ingredient_name": ing_name,
                            "qty_deducted":    float(br.quantity_wasted),
                            "unit":            br.unit,
                            "ingredient_cost": round(br_cost, 2),
                            "source":          "raw",
                        })
                        if ing_name:
                            inventory_cost_map[ing_name] = inventory_cost_map.get(ing_name, 0.0) + br_cost

                # Aggregate sub_ingredients inside each nested semi-finished group
                for sfp in semi_finished_map.values():
                    sfp["sub_ingredients"] = WastageService._aggregate_raw_ingredients(sfp["sub_ingredients"])
                    sfp["semi_finished_cost"] = round(sfp["semi_finished_cost"], 2)

                breakdown = WastageService._aggregate_raw_ingredients(raw_ingredients) + list(semi_finished_map.values())

            # ── COMBO breakdown ───────────────────────────────────────────────────
            elif w.wastage_type == WastageType.COMBO and children:
                raw_ingredients: list = []
                dish_map: dict        = {}
                sfp_map: dict         = {}

                for br in children:
                    br_cost = float(br.cost_value) if br.cost_value else 0.0

                    if br.dish_id:
                        d_id = br.dish_id
                        if d_id not in dish_map:
                            dish_map[d_id] = {
                                "dish_id":         d_id,
                                "dish_name":       br.dish.name if br.dish else None,
                                "source":          "dish",
                                "sub_ingredients": [],
                                "dish_cost":       0.0,
                            }
                        ing_name = br.inventory_item.name if br.inventory_item else None
                        dish_map[d_id]["sub_ingredients"].append({
                            "ingredient_id":   br.inventory_item_id,
                            "ingredient_name": ing_name,
                            "qty_deducted":    float(br.quantity_wasted),
                            "unit":            br.unit,
                            "ingredient_cost": round(br_cost, 2),
                        })
                        dish_map[d_id]["dish_cost"] += br_cost

                        if ing_name:
                            inventory_cost_map[ing_name] = inventory_cost_map.get(ing_name, 0.0) + br_cost

                    elif br.semi_finished_product_id:
                        sfp_id = br.semi_finished_product_id
                        if sfp_id not in sfp_map:
                            sfp_map[sfp_id] = {
                                "semi_finished_id":   sfp_id,
                                "semi_finished_name": br.semi_finished_product.name if br.semi_finished_product else None,
                                "semi_finished_qty":  float(br.semi_finished_qty) if br.semi_finished_qty else None,
                                "semi_finished_unit": br.semi_finished_unit_used,
                                "source":             "semi_finished",
                                "sub_ingredients":    [],
                                "semi_finished_cost": 0.0,
                            }
                        ing_name = br.inventory_item.name if br.inventory_item else None
                        sfp_map[sfp_id]["sub_ingredients"].append({
                            "ingredient_id":   br.inventory_item_id,
                            "ingredient_name": ing_name,
                            "qty_deducted":    float(br.quantity_wasted),
                            "unit":            br.unit,
                            "ingredient_cost": round(br_cost, 2),
                        })
                        sfp_map[sfp_id]["semi_finished_cost"] += br_cost

                        if ing_name:
                            inventory_cost_map[ing_name] = inventory_cost_map.get(ing_name, 0.0) + br_cost

                    else:
                        ing_name = br.inventory_item.name if br.inventory_item else None
                        raw_ingredients.append({
                            "ingredient_id":   br.inventory_item_id,
                            "ingredient_name": ing_name,
                            "qty_deducted":    float(br.quantity_wasted),
                            "unit":            br.unit,
                            "ingredient_cost": round(br_cost, 2),
                            "source":          "raw",
                        })
                        if ing_name:
                            inventory_cost_map[ing_name] = inventory_cost_map.get(ing_name, 0.0) + br_cost

                # Aggregate sub_ingredients inside each dish/sfp group
                for d in dish_map.values():
                    d["sub_ingredients"] = WastageService._aggregate_raw_ingredients(d["sub_ingredients"])
                    d["dish_cost"] = round(d["dish_cost"], 2)
                for sfp in sfp_map.values():
                    sfp["sub_ingredients"] = WastageService._aggregate_raw_ingredients(sfp["sub_ingredients"])
                    sfp["semi_finished_cost"] = round(sfp["semi_finished_cost"], 2)

                breakdown = list(dish_map.values()) + list(sfp_map.values()) + WastageService._aggregate_raw_ingredients(raw_ingredients)

            # ── Build record dict ─────────────────────────────────────────────────
            record_dict = {
                "id":                  str(w.id),
                "wastage_type":        w.wastage_type.value,
                "wastage_reason":      w.wastage_reason.value,
                "item_name":           item_name,
                "inventory_item_id":   w.inventory_item_id if w.inventory_item_id else None,
                "dish_name":           dish_name,
                "dish_id":             w.dish_id if w.dish_id else None,
                "combo_name":          combo_name,
                "combo_id":            w.combo_id if w.combo_id else None,
                "batch_number":        batch_number,
                "quantity_wasted":     float(w.quantity_wasted),
                "unit":                w.unit,
                "unit_cost":           w.unit_cost  if w.unit_cost  else None,
                "cost_value":          record_cost  if record_cost  else None,
                "wastage_date":        w.wastage_date,
                "notes":               w.notes,
                "photo_url":           f"{settings.BASE_URL}/api/v1/wastage/photo/{str(w.id)}" if w.photo_url else None,
                "is_breakdown":        w.is_breakdown,
                "recorded_by":         recorded_by,
                "breakdown":           breakdown,
            }
            result.append(record_dict)

        # ── Search ────────────────────────────────────────────────────────────────
        if search:
            s = search.lower()
            result = [
                r for r in result
                if (r["item_name"]  and s in r["item_name"].lower())
                or (r["dish_name"]  and s in r["dish_name"].lower())
                or (r["combo_name"] and s in r["combo_name"].lower())
            ]

        # ── Summary ───────────────────────────────────────────────────────────────
        most_wasted_dish       = max(dish_cost_map,      key=dish_cost_map.get)      if dish_cost_map      else None
        most_wasted_combo      = max(combo_cost_map,     key=combo_cost_map.get)     if combo_cost_map     else None
        most_wasted_inventory  = max(inventory_cost_map, key=inventory_cost_map.get) if inventory_cost_map else None
        least_wasted_inventory = min(inventory_cost_map, key=inventory_cost_map.get) if inventory_cost_map else None

        summary = {
            "total_wastage_cost":    round(total_cost, 2),
            "total_wastage_records": len(result),
            "most_wasted_dish": {
                "name":       most_wasted_dish,
                "total_cost": round(dish_cost_map[most_wasted_dish], 2),
            } if most_wasted_dish else None,
            "most_wasted_combo": {
                "name":       most_wasted_combo,
                "total_cost": round(combo_cost_map[most_wasted_combo], 2),
            } if most_wasted_combo else None,
            "most_wasted_inventory_item": {
                "name":       most_wasted_inventory,
                "total_cost": round(inventory_cost_map[most_wasted_inventory], 2),
            } if most_wasted_inventory else None,
            "least_wasted_inventory_item": {
                "name":       least_wasted_inventory,
                "total_cost": round(inventory_cost_map[least_wasted_inventory], 2),
            } if least_wasted_inventory else None,
        }

        return {"records": result, "summary": summary}
    
    @staticmethod
    def generate_report(
        db: Session,
        tenant_id: int,
        period: str,
        start_date: date,
        end_date: date,
        perishable_threshold_pct: float = PERISHABLE_WASTAGE_ALERT_PCT,
    ) -> dict:
        """
        Generate a wastage report for a given period.
        Breaks down by: reason, perishable vs non-perishable, top items.
        """
        # All top-level records in range
        base_q = db.query(Wastage).filter(
            Wastage.tenant_id == tenant_id,
            Wastage.is_breakdown == False,
            func.date(Wastage.wastage_date) >= start_date,
            func.date(Wastage.wastage_date) <= end_date,
        )

        records = base_q.all()

        total_cost = sum(float(r.cost_value or 0) for r in records)
        unsold_dish_cost = sum(
            float(r.cost_value or 0) for r in records
            if r.wastage_reason == WastageReason.UNSOLD_DISH
        )

        # Perishable vs non-perishable split
        # A record is perishable if it's INVENTORY type and the item has an expiry/shelf life
        perishable_cost = Decimal(0)
        non_perishable_cost = Decimal(0)
        for r in records:
            cost = Decimal(str(r.cost_value or 0))
            if r.wastage_type == WastageType.INVENTORY and r.inventory_item:
                if r.inventory_item.shelf_life_in_days or r.inventory_item.expiry_date:
                    perishable_cost += cost
                else:
                    non_perishable_cost += cost
            # Dish wastage counted separately
        
        # Total perishable inventory value (for threshold calculation)
        perishable_items = db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.is_active == True,
        ).all()
        total_perishable_inventory_value = sum(
            float((item.current_quantity or 0) * (item.unit_cost or item.price_per_unit or 0))
            for item in perishable_items
            if item.shelf_life_in_days or item.expiry_date
        )

        perishable_wastage_pct = (
            (float(perishable_cost) / total_perishable_inventory_value * 100)
            if total_perishable_inventory_value > 0 else 0.0
        )
        alert_exceeded = perishable_wastage_pct > perishable_threshold_pct

        # Breakdown by reason
        by_reason_map: dict = {}
        for r in records:
            key = r.wastage_reason.value
            if key not in by_reason_map:
                by_reason_map[key] = {"cost": Decimal(0), "qty": Decimal(0), "count": 0}
            by_reason_map[key]["cost"] += Decimal(str(r.cost_value or 0))
            by_reason_map[key]["qty"] += Decimal(str(r.quantity_wasted or 0))
            by_reason_map[key]["count"] += 1

        by_reason = []
        for reason, data in by_reason_map.items():
            by_reason.append({
                "reason": reason,
                "total_quantity": float(data["qty"]),
                "total_cost": float(data["cost"]),
                "record_count": data["count"],
                "percentage_of_total_cost": round(
                    float(data["cost"]) / total_cost * 100, 2
                ) if total_cost > 0 else 0.0,
            })
        by_reason.sort(key=lambda x: x["total_cost"], reverse=True)

        # Top wastage items
        item_map: dict = {}
        for r in records:
            name = None
            if r.inventory_item:
                name = r.inventory_item.name
            elif r.dish:
                name = r.dish.name
            if not name:
                continue
            wtype = r.wastage_type.value
            key = (name, wtype)
            if key not in item_map:
                item_map[key] = {"qty": Decimal(0), "cost": Decimal(0), "unit": r.unit, "count": 0}
            item_map[key]["qty"] += Decimal(str(r.quantity_wasted or 0))
            item_map[key]["cost"] += Decimal(str(r.cost_value or 0))
            item_map[key]["count"] += 1

        top_items = sorted(
            [
                {
                    "item_name": k[0],
                    "wastage_type": k[1],
                    "total_quantity": float(v["qty"]),
                    "unit": v["unit"],
                    "total_cost": float(v["cost"]),
                    "occurrences": v["count"],
                }
                for k, v in item_map.items()
            ],
            key=lambda x: x["total_cost"],
            reverse=True,
        )[:10]

        return {
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "tenant_id": tenant_id,
            "total_wastage_cost": round(total_cost, 2),
            "total_perishable_wastage_cost": round(float(perishable_cost), 2),
            "total_non_perishable_wastage_cost": round(float(non_perishable_cost), 2),
            "total_unsold_dish_cost": round(unsold_dish_cost, 2),
            "perishable_wastage_pct_of_inventory": round(perishable_wastage_pct, 2),
            "alert_perishable_threshold_exceeded": alert_exceeded,
            "perishable_threshold_pct": perishable_threshold_pct,
            "by_reason": by_reason,
            "top_wastage_items": top_items,
        }
    
    @staticmethod
    def record_inventory_wastage(
        db: Session,
        tenant_id: int,
        data: RecordInventoryWastage,
        user_id: int,
    ) -> Wastage:

        item = db.query(Inventory).filter(
            Inventory.id        == data.inventory_item_id,
            Inventory.tenant_id == tenant_id,
            Inventory.is_active == True,
        ).first()

        # ── Resolve effective wastage date early ──────────────────────────
        effective_wastage_date = data.wastage_date or datetime.now(timezone.utc)

        # ── Derive calendar date safely regardless of date vs datetime ────
        wastage_calendar_date = (
            effective_wastage_date.date()
            if isinstance(effective_wastage_date, datetime)
            else effective_wastage_date
        )

        # ── End of wastage day — include batches added anytime on that day ─
        wastage_end_of_day = datetime(
            wastage_calendar_date.year,
            wastage_calendar_date.month,
            wastage_calendar_date.day,
            23, 59, 59,
            tzinfo=timezone.utc,
        )

        # ── Get batches FIFO/FEFO — strict date filter, no fallback ──────
        batches_query = []
        if item:
            batches_query = (
                db.query(InventoryBatch)
                .filter(
                    InventoryBatch.tenant_id         == tenant_id,
                    InventoryBatch.inventory_item_id == data.inventory_item_id,
                    InventoryBatch.is_active         == True,
                    InventoryBatch.quantity_remaining > 0,
                    InventoryBatch.date_added         <= wastage_end_of_day,
                    or_(
                        InventoryBatch.expiry_date == None,
                        InventoryBatch.expiry_date >= wastage_calendar_date,
                    ),
                )
                .order_by(
                    InventoryBatch.expiry_date.asc().nullslast(),
                    InventoryBatch.date_added.asc(),
                )
                .all()
            )

            if data.inventory_batch_id:
                batches_query = [b for b in batches_query if b.id == data.inventory_batch_id]

        # ── Resolve reference unit ────────────────────────────────────────
        reference_unit = normalize_unit(
            batches_query[0].unit if batches_query and batches_query[0].unit
            else (item.unit if item else data.unit)
        )

        is_fixed_cost = bool(item and item.is_fixed_cost)

        # ── Calculate qty_in_reference_unit ──────────────────────────────
        if is_fixed_cost:
            batch_unit_cost = (
                Decimal(str(batches_query[0].unit_cost or 0))
                if batches_query else Decimal("0")
            )
            qty_in_reference_unit = (
                Decimal(str(data.quantity_wasted)) / batch_unit_cost
                if batch_unit_cost > 0 else Decimal("0")
            )
        else:
            wastage_unit = normalize_unit(data.unit)
            PIECE_UNITS  = {"pcs", "piece", "pieces"}
            PACKET_UNITS = {"packet", "packets", "pkt"}

            if wastage_unit in PIECE_UNITS and reference_unit in PACKET_UNITS:
                pieces_per_packet = (
                    Decimal(str(batches_query[0].pieces))
                    if batches_query and batches_query[0].pieces else Decimal("1")
                )
                qty_in_reference_unit = Decimal(str(data.quantity_wasted)) / pieces_per_packet
            else:
                try:
                    if wastage_unit != reference_unit and are_units_compatible(wastage_unit, reference_unit):
                        qty_in_reference_unit = Decimal(str(
                            convert_to_base_unit(float(data.quantity_wasted), wastage_unit, reference_unit)
                        ))
                    else:
                        qty_in_reference_unit = Decimal(str(data.quantity_wasted))
                except Exception:
                    qty_in_reference_unit = Decimal(str(data.quantity_wasted))

        # ── Determine unit_cost for wastage record ────────────────────────
        unit_cost = Decimal(0)
        if batches_query and batches_query[0].unit_cost:
            unit_cost = Decimal(str(batches_query[0].unit_cost))
        elif item:
            unit_cost = Decimal(str(item.unit_cost or item.price_per_unit or 0))

        # ── Initialise warning ────────────────────────────────────────────
        deduction_warning = None

        # ── No batches at all — set warning, skip deduction ──────────────
        if not batches_query:
            deduction_warning = (
                f"No stock available for "
                f"'{item.name if item else data.inventory_item_id}' "
                f"on or before {wastage_calendar_date} — skipped deduction."
            )

        # ── Pre-check available stock for non-fixed-cost (informational) ─
        elif not is_fixed_cost:
            total_available_in_reference_unit = Decimal(0)
            for b in batches_query:
                batch_unit = normalize_unit(
                    b.unit if b.unit else (item.unit if item else data.unit)
                )
                b_qty = Decimal(str(b.quantity_remaining))
                try:
                    if batch_unit != reference_unit and are_units_compatible(batch_unit, reference_unit):
                        b_qty = Decimal(str(
                            convert_to_base_unit(float(b_qty), batch_unit, reference_unit)
                        ))
                except Exception:
                    pass
                total_available_in_reference_unit += b_qty

            # Just note it — FIFO loop will still run and deduct what's available
            if qty_in_reference_unit > total_available_in_reference_unit:
                try:
                    input_unit = normalize_unit(data.unit)
                    available_in_input_unit = (
                        convert_to_base_unit(
                            float(total_available_in_reference_unit),
                            reference_unit,
                            input_unit,
                        )
                        if reference_unit != input_unit
                        else float(total_available_in_reference_unit)
                    )
                except Exception:
                    available_in_input_unit = float(total_available_in_reference_unit)

                deduction_warning = (
                    f"Insufficient stock for "
                    f"'{item.name if item else data.inventory_item_id}'. "
                    f"Requested: {float(data.quantity_wasted)} {data.unit}, "
                    f"Available: {round(available_in_input_unit, 4)} {data.unit} — "
                    f"partially deducted."
                )

        recorded_at = _to_dt(data.wastage_date) or datetime.now(timezone.utc)

        # ── Create wastage record FIRST to get its ID ────────────────────
        wastage_record = Wastage(
            tenant_id           = tenant_id,
            wastage_type        = WastageType.INVENTORY,
            inventory_item_id   = data.inventory_item_id,
            inventory_batch_id  = data.inventory_batch_id,
            quantity_wasted     = float(data.quantity_wasted),
            unit                = data.unit,
            unit_cost           = float(unit_cost),
            cost_value          = 0,
            wastage_reason      = data.wastage_reason,
            wastage_date        = effective_wastage_date,
            notes               = data.notes,
            photo_url           = data.photo_url,
            recorded_by_user_id = user_id,
        )
        db.add(wastage_record)
        db.flush()

        # ── Deduct FIFO/FEFO — runs whenever batches exist ───────────────
        qty_remaining = qty_in_reference_unit
        total_cost    = Decimal(0)

        if batches_query:
            for batch in batches_query:
                if qty_remaining <= 0:
                    break

                batch_unit      = normalize_unit(batch.unit if batch.unit else (item.unit if item else data.unit))
                batch_qty       = Decimal(str(batch.quantity_remaining))
                batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)

                try:
                    qty_needed_in_batch_unit = qty_remaining
                    if batch_unit != reference_unit:
                        qty_needed_in_batch_unit = Decimal(str(convert_to_base_unit(
                            float(qty_remaining), reference_unit, batch_unit
                        )))
                except Exception:
                    qty_needed_in_batch_unit = qty_remaining

                qty_from_batch           = min(batch_qty, qty_needed_in_batch_unit)
                batch.quantity_remaining = float(max(Decimal(0), batch_qty - qty_from_batch))

                if is_fixed_cost:
                    batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
                    batch_total_cost   = Decimal(str(batch.total_cost))        if batch.total_cost        else Decimal("0")
                    cost = (
                        (qty_from_batch / batch_qty_received) * batch_total_cost
                        if batch_qty_received > 0 else Decimal("0")
                    )
                else:
                    cost = qty_from_batch * batch_unit_cost

                total_cost += cost

                if Decimal(str(batch.quantity_remaining)) <= 0:
                    batch.is_active = False

                db.add(batch)
                db.add(InventoryTransaction(
                    tenant_id         = tenant_id,
                    inventory_item_id = data.inventory_item_id,
                    batch_id          = batch.id,
                    transaction_type  = TransactionType.WASTAGE,
                    quantity          = float(qty_from_batch),
                    unit              = batch_unit,
                    unit_cost         = float(batch_unit_cost),
                    total_value       = float(cost),
                    transaction_date  = effective_wastage_date,
                    reference_id      = _wastage_ref(wastage_record.id),
                ))

                try:
                    qty_deducted_in_reference_unit = qty_from_batch
                    if batch_unit != reference_unit:
                        qty_deducted_in_reference_unit = Decimal(str(convert_to_base_unit(
                            float(qty_from_batch), batch_unit, reference_unit
                        )))
                except Exception:
                    qty_deducted_in_reference_unit = qty_from_batch

                qty_remaining -= qty_deducted_in_reference_unit

            # ── Partial shortfall warning (overrides pre-check warning) ──
            if qty_remaining > Decimal("0.0000001"):
                try:
                    shortfall_in_input_unit = (
                        convert_to_base_unit(
                            float(qty_remaining),
                            reference_unit,
                            normalize_unit(data.unit),
                        )
                        if reference_unit != normalize_unit(data.unit)
                        else float(qty_remaining)
                    )
                except Exception:
                    shortfall_in_input_unit = float(qty_remaining)
                deduction_warning = (
                    f"Insufficient stock for "
                    f"'{item.name if item else data.inventory_item_id}' — "
                    f"partially deducted. Shortfall: {round(shortfall_in_input_unit, 4)} {data.unit}."
                )

        # ── Update cost on wastage record after loop ──────────────────────
        if is_fixed_cost:
            total_cost = Decimal(str(data.quantity_wasted))

        wastage_record.cost_value = float(total_cost)
        db.add(wastage_record)

        if item:
            sync_inventory_totals(data.inventory_item_id, db)

        db.commit()
        db.refresh(wastage_record)

        # ── Attach warning as transient attr for combo caller ────────────
        wastage_record._deduction_warning = deduction_warning

        return wastage_record

    @staticmethod
    def record_dish_wastage(
        db: Session,
        tenant_id: int,
        dish_id: int,
        quantity_wasted: int,
        wastage_reason: str,
        user_id: int,
        notes: Optional[str] = None,
        wastage_date: Optional[datetime] = None,
        photo_url: Optional[str] = None,
    ) -> dict:
 
        # ── 1. Fetch dish ────────────────────────────────────────────────────────
        dish = db.query(Dish).filter(
            Dish.id        == dish_id,
            Dish.tenant_id == tenant_id,
            Dish.is_active == True,
        ).first()
 
        dish_name = dish.name if dish else f"Dish#{dish_id}"
 
        try:
            reason_enum = WastageReason(wastage_reason) if wastage_reason else list(WastageReason)[0]
        except ValueError:
            reason_enum = list(WastageReason)[0]
 
        quantity_wasted     = quantity_wasted or 1
        quantity_wasted_dec = Decimal(str(quantity_wasted))
 
        recorded_at = datetime.now(timezone.utc)
 
        if wastage_date is not None:
            if isinstance(wastage_date, datetime):
                wastage_date_val = (
                    wastage_date if wastage_date.tzinfo
                    else wastage_date.replace(tzinfo=timezone.utc)
                )
            elif isinstance(wastage_date, date):
                wastage_date_val = datetime(
                    wastage_date.year, wastage_date.month, wastage_date.day,
                    0, 0, 0,
                    tzinfo=timezone.utc,
                )
            else:
                wastage_date_val = recorded_at
        else:
            wastage_date_val = recorded_at
 
        wastage_calendar_date = wastage_date_val.date()
 
        wastage_end_of_day = datetime(
            wastage_calendar_date.year,
            wastage_calendar_date.month,
            wastage_calendar_date.day,
            23, 59, 59,
            tzinfo=timezone.utc,
        )
 
        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}
 
        def _safe_unit(u) -> str:
            if u is None:
                return ""
            if hasattr(u, "value"):
                return normalize_unit(u.value)
            return normalize_unit(str(u))
 
        # ── Batch fetcher: FEFO, excludes expired, falls back gracefully ─────────
        # FIX 3: expire_on_commit=False is not enough — we must expire individual
        # objects after reversal so re-queries hit DB, not SQLAlchemy identity map.
        # Callers of this function in edit_wastage must call db.expire_all() after
        # flush before re-querying batches. Here we always query fresh.
        def _get_batches_for_ingredient(ingredient_id: int) -> list:
            return (
                db.query(InventoryBatch)
                .filter(
                    InventoryBatch.tenant_id         == tenant_id,
                    InventoryBatch.inventory_item_id == ingredient_id,
                    InventoryBatch.is_active         == True,
                    InventoryBatch.quantity_remaining > 0,
                    or_(
                        InventoryBatch.expiry_date == None,
                        InventoryBatch.expiry_date >= wastage_calendar_date,
                    ),
                )
                .order_by(
                    InventoryBatch.expiry_date.asc().nullslast(),
                    InventoryBatch.date_added.asc(),
                )
                .all()
            )
 
        # ── 2. Fetch dish ingredients ────────────────────────────────────────────
        dish_ingredients_all = []
        if dish:
            dish_ingredients_all = (
                db.query(DishIngredient)
                .filter(
                    DishIngredient.dish_id   == dish_id,
                    DishIngredient.tenant_id == tenant_id,
                )
                .all()
            )
 
        raw_ingredients  = [di for di in dish_ingredients_all if di.semi_finished_id is None]
        semi_ingredients = [di for di in dish_ingredients_all if di.semi_finished_id is not None]
 
        def resolve_semi_finished_to_raw(
            semi_id: int,
            qty_sfp_needed: Decimal,
            top_semi_id: int,
            top_semi_name: str,
            top_semi_qty: float,
            top_semi_unit: str,
            visited: set = None,
        ) -> list:
            if visited is None:
                visited = set()
            if semi_id in visited:
                return []
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
                if getattr(sub, "is_semi_finished", False):
                    nested_semi_id = sub.ingredient_id
                    if not nested_semi_id:
                        continue
                    nested_qty = Decimal(str(sub.quantity_required)) * scale_factor
                    nested_semi = db.query(SemiFinishedProduct).filter(
                        SemiFinishedProduct.id        == nested_semi_id,
                        SemiFinishedProduct.tenant_id == tenant_id,
                        SemiFinishedProduct.is_active == True,
                    ).first()
                    if nested_semi:
                        sub_unit    = normalize_unit(sub.unit)
                        nested_unit = normalize_unit(nested_semi.unit)
                        try:
                            if sub_unit != nested_unit:
                                nested_qty = Decimal(str(
                                    convert_to_base_unit(float(nested_qty), sub_unit, nested_unit)
                                ))
                        except Exception:
                            pass
                    result.extend(resolve_semi_finished_to_raw(
                        semi_id        = nested_semi_id,
                        qty_sfp_needed = nested_qty,
                        top_semi_id    = top_semi_id,
                        top_semi_name  = top_semi_name,
                        top_semi_qty   = top_semi_qty,
                        top_semi_unit  = top_semi_unit,
                        visited        = visited,
                    ))
                elif sub.ingredient_id:
                    result.append({
                        "ingredient_id":      sub.ingredient_id,
                        "ingredient_name":    sub.ingredient_name,
                        "qty_needed":         Decimal(str(sub.quantity_required)) * scale_factor,
                        "unit":               sub.unit,
                        "fixed_cost_amount":  sub.fixed_cost_amount,
                        "source":             "semi_finished",
                        "semi_finished_id":   top_semi_id,
                        "semi_finished_name": top_semi_name,
                        "semi_finished_qty":  top_semi_qty,
                        "semi_finished_unit": top_semi_unit,
                    })
            return result
 
        # ── 3. Build flat ingredients list ───────────────────────────────────────
        ingredients_to_deduct = []
 
        for di in raw_ingredients:
            if not di.ingredient_id:
                continue
            ingredients_to_deduct.append({
                "ingredient_id":      di.ingredient_id,
                "ingredient_name":    di.ingredient_name,
                "qty_needed":         Decimal(str(di.quantity_required)) * quantity_wasted_dec,
                "unit":               di.unit,
                # FIX 1/2: treat cost_per_unit == 0 with no physical stock unit
                # (e.g. Electricity in rupee) as fixed_cost so it never hits FIFO.
                # A raw ingredient is fixed-cost if:
                #   a) fixed_cost_amount is explicitly set, OR
                #   b) its unit is a currency unit (not weight/volume/pcs/packet)
                "fixed_cost_amount":  di.fixed_cost_amount,
                "source":             "raw",
                "semi_finished_id":   None,
                "semi_finished_name": None,
                "semi_finished_qty":  None,
                "semi_finished_unit": None,
            })
 
        for di in semi_ingredients:
            dish_sfp_unit  = normalize_unit(di.unit)
            qty_sfp_needed = Decimal(str(di.quantity_required)) * quantity_wasted_dec
 
            top_semi = db.query(SemiFinishedProduct).filter(
                SemiFinishedProduct.id        == di.semi_finished_id,
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            ).first()
            if not top_semi:
                continue
 
            semi_yield_unit = normalize_unit(top_semi.unit)
            try:
                if dish_sfp_unit != semi_yield_unit:
                    qty_sfp_needed = Decimal(str(
                        convert_to_base_unit(float(qty_sfp_needed), dish_sfp_unit, semi_yield_unit)
                    ))
            except Exception:
                pass
 
            ingredients_to_deduct.extend(
                resolve_semi_finished_to_raw(
                    semi_id        = di.semi_finished_id,
                    qty_sfp_needed = qty_sfp_needed,
                    top_semi_id    = top_semi.id,
                    top_semi_name  = top_semi.name,
                    top_semi_qty   = float(qty_sfp_needed),
                    top_semi_unit  = semi_yield_unit,
                )
            )
 
        # ── Helper: detect currency/non-physical units ───────────────────────────
        # FIX 1/2: ingredients measured in currency (rupee, dollar, etc.) have no
        # physical stock to deduct — treat them as fixed-cost always.
        CURRENCY_UNITS = {"rupee", "rupees", "rs", "inr", "dollar", "dollars", "usd", "eur", "euro"}
 
        def _is_currency_unit(unit_str: str) -> bool:
            return normalize_unit(unit_str).lower() in CURRENCY_UNITS
 
        # ── Aggregate total demand per ingredient_id (for validation) ────────────
        aggregated_demand: dict = defaultdict(lambda: {
            "total_qty_needed":  Decimal(0),
            "unit":              None,
            "ingredient_name":   None,
            "fixed_cost_amount": None,
        })
        for ing in ingredients_to_deduct:
            key = ing["ingredient_id"]
            aggregated_demand[key]["total_qty_needed"] += ing["qty_needed"]
            aggregated_demand[key]["unit"]              = ing["unit"]
            aggregated_demand[key]["ingredient_name"]   = ing["ingredient_name"]
            if ing.get("fixed_cost_amount") is not None:
                aggregated_demand[key]["fixed_cost_amount"] = ing["fixed_cost_amount"]
 
        # ── Collapse by (ingredient_id, semi_finished_id) ────────────────────────
        collapsed_deduct: dict = {}
        for ing in ingredients_to_deduct:
            key = (ing["ingredient_id"], ing["semi_finished_id"])
            if key not in collapsed_deduct:
                collapsed_deduct[key] = {
                    "ingredient_id":      ing["ingredient_id"],
                    "ingredient_name":    ing["ingredient_name"],
                    "qty_needed":         Decimal(0),
                    "unit":               ing["unit"],
                    "fixed_cost_amount":  ing.get("fixed_cost_amount"),
                    "source":             ing["source"],
                    "semi_finished_id":   ing["semi_finished_id"],
                    "semi_finished_name": ing["semi_finished_name"],
                    "semi_finished_qty":  ing.get("semi_finished_qty"),
                    "semi_finished_unit": ing.get("semi_finished_unit"),
                }
            collapsed_deduct[key]["qty_needed"] += ing["qty_needed"]
 
        ingredients_to_deduct = list(collapsed_deduct.values())
 
        # ── PRE-VALIDATE stock ───────────────────────────────────────────────────
        validation_errors      = []
        expired_stock_warnings = []
 
        for ingredient_id, agg in aggregated_demand.items():
            # FIX 1/2: skip validation for fixed-cost AND currency-unit ingredients
            # — they have no physical batch stock to validate against.
            if agg["fixed_cost_amount"] is not None:
                continue
            if agg["unit"] and _is_currency_unit(agg["unit"]):
                continue
 
            inventory = db.query(Inventory).filter(
                Inventory.id        == ingredient_id,
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).first()
 
            if inventory:
                expired_batches = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == ingredient_id,
                        InventoryBatch.quantity_remaining > 0,
                        InventoryBatch.expiry_date        != None,
                        InventoryBatch.expiry_date         < wastage_calendar_date,
                    )
                    .all()
                )
                if expired_batches:
                    expired_qty = sum(float(b.quantity_remaining) for b in expired_batches)
                    expired_stock_warnings.append(
                        f"'{agg['ingredient_name']}' has {len(expired_batches)} expired batch(es) "
                        f"with {round(expired_qty, 4)} {agg['unit']} remaining that were skipped. "
                        f"Please write them off separately."
                    )
 
            batches = _get_batches_for_ingredient(ingredient_id) if inventory else []
 
            if not batches:
                expired_stock_warnings.append(
                    f"No valid (non-expired) stock available for '{agg['ingredient_name']}' "
                    f"on or before {wastage_calendar_date}. "
                    f"Stock may have been added after the wastage date or all batches are expired."
                )
                continue
 
            ref_unit   = _safe_unit(batches[0].unit) if batches[0].unit else normalize_unit(agg["unit"])
            ing_unit   = normalize_unit(agg["unit"])
            qty_needed = agg["total_qty_needed"]
 
            # ── pcs → packet: compare in pcs ─────────────────────────────────────
            if ing_unit in PIECE_UNITS and ref_unit in PACKET_UNITS:
                total_available_pcs = Decimal(0)
                for b in batches:
                    pieces_per_packet    = Decimal(str(b.pieces)) if b.pieces else Decimal("1")
                    total_available_pcs += Decimal(str(b.quantity_remaining)) * pieces_per_packet
                if qty_needed > total_available_pcs:
                    expired_stock_warnings.append(
                        f"Insufficient stock for '{agg['ingredient_name']}'. "
                        f"Requested: {round(float(agg['total_qty_needed']), 4)} {agg['unit']}, "
                        f"Available: {round(float(total_available_pcs), 4)} {agg['unit']}."
                    )
                continue  # skip generic block
 
            # ── Generic unit conversion ───────────────────────────────────────────
            try:
                if ing_unit != ref_unit and are_units_compatible(ing_unit, ref_unit):
                    qty_needed = Decimal(str(
                        convert_to_base_unit(float(qty_needed), ing_unit, ref_unit)
                    ))
            except Exception:
                pass
 
            total_available = Decimal(0)
            for b in batches:
                b_unit = _safe_unit(b.unit) if b.unit else normalize_unit(agg["unit"])
                b_qty  = Decimal(str(b.quantity_remaining))
                try:
                    if b_unit != ref_unit and are_units_compatible(b_unit, ref_unit):
                        b_qty = Decimal(str(convert_to_base_unit(float(b_qty), b_unit, ref_unit)))
                except Exception:
                    pass
                total_available += b_qty
 
            if qty_needed > total_available:
                try:
                    available_in_ing_unit = (
                        convert_to_base_unit(float(total_available), ref_unit, ing_unit)
                        if ref_unit != ing_unit else float(total_available)
                    )
                except Exception:
                    available_in_ing_unit = float(total_available)
                expired_stock_warnings.append(
                    f"Insufficient stock for '{agg['ingredient_name']}'. "
                    f"Requested: {round(float(agg['total_qty_needed']), 4)} {agg['unit']}, "
                    f"Available: {round(available_in_ing_unit, 4)} {agg['unit']}."
                )
 
        # if expired_stock_warnings:
        #     raise HTTPException(
        #         status_code=status.HTTP_400_BAD_REQUEST,
        #         detail={"errors": expired_stock_warnings},
        #     )
 
        # ── 4. Create wastage record (cost filled in after FIFO) ─────────────────
        wastage_record = Wastage(
            tenant_id           = tenant_id,
            wastage_type        = WastageType.DISH,
            dish_id             = dish_id,
            quantity_wasted     = float(quantity_wasted),
            unit                = "plate",
            unit_cost           = 0,
            cost_value          = 0,
            wastage_reason      = reason_enum,
            wastage_date        = wastage_date_val,
            notes               = notes,
            photo_url           = photo_url,
            recorded_by_user_id = user_id,
        )
        db.add(wastage_record)
        db.flush()
 
        # ── 5. FIFO Deduction ────────────────────────────────────────────────────
        breakdown_data = []
        deduction_warnings  = []

        for ing in ingredients_to_deduct:
            dish_ing_unit     = normalize_unit(ing["unit"])
            fixed_cost_amount = ing.get("fixed_cost_amount")
 
            # FIX 1/2: currency-unit ingredients (e.g. Electricity in rupee) are
            # pure cost entries — no batch stock exists for them. Record cost only.
            if _is_currency_unit(dish_ing_unit) and fixed_cost_amount is None:
                ingredient_cost = ing["qty_needed"]  # qty IS the cost in rupees
                breakdown_data.append({
                    "ingredient_id":      ing["ingredient_id"],
                    "ingredient_name":    ing["ingredient_name"],
                    "qty_deducted":       ing["qty_needed"],
                    "unit":               dish_ing_unit,
                    "ingredient_cost":    ingredient_cost,
                    "source":             ing["source"],
                    "semi_finished_id":   ing["semi_finished_id"],
                    "semi_finished_name": ing["semi_finished_name"],
                    "semi_finished_qty":  ing.get("semi_finished_qty"),
                    "semi_finished_unit": ing.get("semi_finished_unit"),
                })
                continue
 
            inventory = db.query(Inventory).filter(
                Inventory.id        == ing["ingredient_id"],
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).first()
 
            batches = _get_batches_for_ingredient(ing["ingredient_id"]) if inventory else []
 
            if not batches:
                deduction_warnings.append(
                    f"No stock available for '{ing['ingredient_name']}' — skipped deduction."
                )
                breakdown_data.append({
                    "ingredient_id":      ing["ingredient_id"],
                    "ingredient_name":    ing["ingredient_name"],
                    "qty_deducted":       Decimal(0),
                    "unit":               dish_ing_unit,
                    "ingredient_cost":    Decimal(0),
                    "source":             ing["source"],
                    "semi_finished_id":   ing["semi_finished_id"],
                    "semi_finished_name": ing["semi_finished_name"],
                    "semi_finished_qty":  ing.get("semi_finished_qty"),
                    "semi_finished_unit": ing.get("semi_finished_unit"),
                })
                continue
 
            reference_unit = _safe_unit(batches[0].unit) if batches[0].unit else dish_ing_unit
 
            # ── Fixed-cost ingredient ─────────────────────────────────────────────
            if fixed_cost_amount is not None:
                batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
                qty_recipe      = Decimal(str(ing["qty_needed"]))
                qty_to_deduct   = (
                    (Decimal(str(fixed_cost_amount)) / batch_unit_cost) * qty_recipe
                    if batch_unit_cost > 0 else Decimal("0")
                )
                qty_remaining   = qty_to_deduct
                ingredient_cost = Decimal("0")
 
                for batch in batches:
                    if qty_remaining <= Decimal("0.0000001"):
                        break
                    batch_qty          = Decimal(str(batch.quantity_remaining))
                    batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
                    batch_total_cost   = Decimal(str(batch.total_cost))        if batch.total_cost        else Decimal("0")
                    qty_from_batch     = min(batch_qty, qty_remaining)
                    cost = (
                        (qty_from_batch / batch_qty_received) * batch_total_cost
                        if batch_qty_received > 0 else Decimal("0")
                    )
                    batch.quantity_remaining = float(batch_qty - qty_from_batch)
                    ingredient_cost         += cost
                    if Decimal(str(batch.quantity_remaining)) <= 0:
                        batch.is_active = False
                    db.add(batch)
                    db.add(InventoryTransaction(
                        tenant_id         = tenant_id,
                        inventory_item_id = ing["ingredient_id"],
                        batch_id          = batch.id,
                        transaction_type  = TransactionType.WASTAGE,
                        quantity          = float(qty_from_batch),
                        unit              = _safe_unit(batch.unit),
                        unit_cost         = float(fixed_cost_amount),
                        total_value       = float(cost),
                        transaction_date  = wastage_date_val,
                        reference_id      = _wastage_ref(wastage_record.id),
                    ))
                    qty_remaining -= qty_from_batch
 
                db.flush()
                if inventory:
                    sync_inventory_totals(ing["ingredient_id"], db)
 
                actual_cost = Decimal(str(fixed_cost_amount)) * quantity_wasted_dec
                breakdown_data.append({
                    "ingredient_id":      ing["ingredient_id"],
                    "ingredient_name":    ing["ingredient_name"],
                    "qty_deducted":       qty_to_deduct,
                    "unit":               reference_unit,
                    "ingredient_cost":    actual_cost,
                    "source":             ing["source"],
                    "semi_finished_id":   ing["semi_finished_id"],
                    "semi_finished_name": ing["semi_finished_name"],
                    "semi_finished_qty":  ing.get("semi_finished_qty"),
                    "semi_finished_unit": ing.get("semi_finished_unit"),
                })
                continue
 
            # ── pcs → packet FIFO ─────────────────────────────────────────────────
            if dish_ing_unit in PIECE_UNITS and reference_unit in PACKET_UNITS:
                # FIX 1/2: qty_remaining_pcs must be tracked correctly across batches.
                # Previous code could let pcs_from_batch exceed actual pcs in batch
                # when b_pieces * batch_qty_pkts < qty_remaining_pcs for last batch.
                qty_remaining_pcs = ing["qty_needed"]   # in pcs
                ingredient_cost   = Decimal(0)
 
                for batch in batches:
                    if qty_remaining_pcs <= Decimal("0.0000001"):
                        deduction_warnings.append(
                        f"Insufficient stock for '{ing['ingredient_name']}' — "
                        f"partially deducted. Shortfall: {round(float(qty_remaining_pcs), 4)} {dish_ing_unit}."
                        )

                        break
                    b_pieces        = Decimal(str(batch.pieces)) if batch.pieces else Decimal("1")
                    batch_unit      = _safe_unit(batch.unit) if batch.unit else reference_unit
                    batch_qty_pkts  = Decimal(str(batch.quantity_remaining))
                    # FIX 1/2: cap pcs available from this batch correctly
                    batch_qty_pcs   = batch_qty_pkts * b_pieces
                    batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)
                    cost_per_pcs    = batch_unit_cost / b_pieces if b_pieces > 0 else Decimal(0)
 
                    # take only what this batch actually has in pcs
                    pcs_from_batch  = min(batch_qty_pcs, qty_remaining_pcs)
                    pkts_from_batch = pcs_from_batch / b_pieces
 
                    batch.quantity_remaining = float(max(Decimal(0), batch_qty_pkts - pkts_from_batch))
                    cost             = pcs_from_batch * cost_per_pcs
                    ingredient_cost += cost
 
                    if Decimal(str(batch.quantity_remaining)) <= 0:
                        batch.is_active = False
 
                    db.add(batch)
                    db.add(InventoryTransaction(
                        tenant_id         = tenant_id,
                        inventory_item_id = ing["ingredient_id"],
                        batch_id          = batch.id,
                        transaction_type  = TransactionType.WASTAGE,
                        quantity          = float(pkts_from_batch),
                        unit              = batch_unit,
                        unit_cost         = float(batch_unit_cost),
                        total_value       = float(cost),
                        transaction_date  = wastage_date_val,
                        reference_id      = _wastage_ref(wastage_record.id),
                    ))
                    qty_remaining_pcs -= pcs_from_batch
 
                db.flush()
                if inventory:
                    sync_inventory_totals(ing["ingredient_id"], db)
 
                breakdown_data.append({
                    "ingredient_id":      ing["ingredient_id"],
                    "ingredient_name":    ing["ingredient_name"],
                    "qty_deducted":       ing["qty_needed"],   # display in pcs
                    "unit":               dish_ing_unit,
                    "ingredient_cost":    ingredient_cost,
                    "source":             ing["source"],
                    "semi_finished_id":   ing["semi_finished_id"],
                    "semi_finished_name": ing["semi_finished_name"],
                    "semi_finished_qty":  ing.get("semi_finished_qty"),
                    "semi_finished_unit": ing.get("semi_finished_unit"),
                })
                continue
 
            # ── Generic FIFO ──────────────────────────────────────────────────────
            qty_needed_ref = ing["qty_needed"]
            try:
                if dish_ing_unit != reference_unit and are_units_compatible(dish_ing_unit, reference_unit):
                    qty_needed_ref = Decimal(str(
                        convert_to_base_unit(float(qty_needed_ref), dish_ing_unit, reference_unit)
                    ))
            except Exception:
                pass
 
            qty_remaining       = qty_needed_ref
            ingredient_cost     = Decimal(0)
            qty_from_batch      = Decimal(0)      # safe default if loop never runs
            qty_deducted_in_ref = Decimal(0)
 
            for batch in batches:
                if qty_remaining <= Decimal("0.0000001"):
                    deduction_warnings.append(
                    f"Insufficient stock for '{ing['ingredient_name']}' — "
                    f"partially deducted. Shortfall: {round(float(qty_remaining), 4)} {reference_unit}."
                )
                    break
 
                batch_unit      = _safe_unit(batch.unit) if batch.unit else (
                    _safe_unit(inventory.unit) if inventory else dish_ing_unit
                )
                batch_qty       = Decimal(str(batch.quantity_remaining))
                batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)
 
                try:
                    qty_needed_in_batch_unit = qty_remaining
                    if batch_unit != reference_unit and are_units_compatible(reference_unit, batch_unit):
                        qty_needed_in_batch_unit = Decimal(str(
                            convert_to_base_unit(float(qty_remaining), reference_unit, batch_unit)
                        ))
                except Exception:
                    qty_needed_in_batch_unit = qty_remaining
 
                qty_from_batch           = min(batch_qty, qty_needed_in_batch_unit)
                batch.quantity_remaining = float(max(Decimal(0), batch_qty - qty_from_batch))
                cost                     = qty_from_batch * batch_unit_cost
                ingredient_cost         += cost  # accumulate actual FIFO cost
 
                if Decimal(str(batch.quantity_remaining)) <= 0:
                    batch.is_active = False
 
                db.add(batch)
                db.add(InventoryTransaction(
                    tenant_id         = tenant_id,
                    inventory_item_id = ing["ingredient_id"],
                    batch_id          = batch.id,
                    transaction_type  = TransactionType.WASTAGE,
                    quantity          = float(qty_from_batch),
                    unit              = batch_unit,
                    unit_cost         = float(batch_unit_cost),
                    total_value       = float(cost),
                    transaction_date  = wastage_date_val,
                    reference_id      = _wastage_ref(wastage_record.id),
                ))
 
                try:
                    qty_deducted_in_ref = qty_from_batch
                    if batch_unit != reference_unit and are_units_compatible(batch_unit, reference_unit):
                        qty_deducted_in_ref = Decimal(str(
                            convert_to_base_unit(float(qty_from_batch), batch_unit, reference_unit)
                        ))
                except Exception:
                    qty_deducted_in_ref = qty_from_batch
 
                qty_remaining -= qty_deducted_in_ref
 
            db.flush()
            if inventory:
                sync_inventory_totals(ing["ingredient_id"], db)
 
            breakdown_data.append({
                "ingredient_id":      ing["ingredient_id"],
                "ingredient_name":    ing["ingredient_name"],
                "qty_deducted":       qty_needed_ref,
                "unit":               reference_unit,
                "ingredient_cost":    ingredient_cost,
                "source":             ing["source"],
                "semi_finished_id":   ing["semi_finished_id"],
                "semi_finished_name": ing["semi_finished_name"],
                "semi_finished_qty":  ing.get("semi_finished_qty"),
                "semi_finished_unit": ing.get("semi_finished_unit"),
            })
 
        # ── 6. Compute total from actual FIFO costs (no rescaling) ───────────────
        total_dish_cost = sum(
            bd["ingredient_cost"] if isinstance(bd["ingredient_cost"], Decimal)
            else Decimal(str(bd["ingredient_cost"]))
            for bd in breakdown_data
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
 
        wastage_record.cost_value = float(total_dish_cost)
        wastage_record.unit_cost  = float(
            (total_dish_cost / quantity_wasted_dec).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )
        ) if quantity_wasted_dec > 0 else 0
        db.add(wastage_record)
        db.flush()
 
        # ── 7. Create breakdown children ─────────────────────────────────────────
        for bd in breakdown_data:
            qty_dec  = bd["qty_deducted"]    if isinstance(bd["qty_deducted"],    Decimal) else Decimal(str(bd["qty_deducted"]))
            cost_dec = bd["ingredient_cost"] if isinstance(bd["ingredient_cost"], Decimal) else Decimal(str(bd["ingredient_cost"]))
            db.add(Wastage(
                tenant_id                = tenant_id,
                wastage_type             = WastageType.INVENTORY,
                inventory_item_id        = bd["ingredient_id"],
                quantity_wasted          = float(qty_dec),
                unit                     = bd["unit"],
                unit_cost                = float(cost_dec / qty_dec) if qty_dec > 0 else 0,
                cost_value               = float(cost_dec),
                wastage_reason           = reason_enum,
                wastage_date             = wastage_date_val,
                recorded_by_user_id      = user_id,
                is_breakdown             = True,
                parent_wastage_id        = wastage_record.id,
                semi_finished_product_id = bd["semi_finished_id"],
                semi_finished_qty        = bd.get("semi_finished_qty"),
                semi_finished_unit_used  = bd.get("semi_finished_unit"),
            ))
 
        db.commit()
        db.refresh(wastage_record)
 
        # ── 8. Build grouped breakdown for API response ──────────────────────────
        raw_breakdown      = []
        semi_breakdown_map = {}
 
        for bd in breakdown_data:
            if bd["source"] == "raw":
                raw_breakdown.append({
                    "ingredient_id":   bd["ingredient_id"],
                    "ingredient_name": bd["ingredient_name"],
                    "qty_deducted":    float(bd["qty_deducted"]),
                    "unit":            bd["unit"],
                    "ingredient_cost": float(bd["ingredient_cost"]),
                    "source":          "raw",
                })
            else:
                sfp_id = bd["semi_finished_id"]
                if sfp_id not in semi_breakdown_map:
                    semi_breakdown_map[sfp_id] = {
                        "semi_finished_id":   sfp_id,
                        "semi_finished_name": bd["semi_finished_name"],
                        "semi_finished_qty":  bd.get("semi_finished_qty"),
                        "semi_finished_unit": bd.get("semi_finished_unit"),
                        "source":             "semi_finished",
                        "sub_ingredients":    [],
                        "semi_finished_cost": 0.0,
                    }
                semi_breakdown_map[sfp_id]["sub_ingredients"].append({
                    "ingredient_id":   bd["ingredient_id"],
                    "ingredient_name": bd["ingredient_name"],
                    "qty_deducted":    float(bd["qty_deducted"]),
                    "unit":            bd["unit"],
                    "ingredient_cost": float(bd["ingredient_cost"]),
                })
                semi_breakdown_map[sfp_id]["semi_finished_cost"] += float(bd["ingredient_cost"])
 
        return {
            "wastage_id":      str(wastage_record.id),
            "dish_name":       dish_name,
            "quantity_wasted": quantity_wasted,
            "total_cost":      float(total_dish_cost),
            "wastage_reason":  reason_enum.value,
            "wastage_date":    wastage_record.wastage_date,
            "photo_url":       wastage_record.photo_url,
            "breakdown":       raw_breakdown + list(semi_breakdown_map.values()),
            "warnings":        expired_stock_warnings  + deduction_warnings,
        }
    
    @staticmethod
    def record_semi_finished_wastage(
        db: Session,
        tenant_id: int,
        semi_finished_id: int,
        quantity_wasted: float,
        wastage_unit: str,
        wastage_reason: str,
        user_id: int,
        notes: Optional[str] = None,
        wastage_date: Optional[datetime] = None,
        photo_url: Optional[str] = None,
    ) -> dict:

        sfp = db.query(SemiFinishedProduct).filter(
            SemiFinishedProduct.id        == semi_finished_id,
            SemiFinishedProduct.tenant_id == tenant_id,
            SemiFinishedProduct.is_active == True,
        ).first()

        sfp_name = sfp.name if sfp else f"SFP#{semi_finished_id}"

        try:
            reason_enum = WastageReason(wastage_reason) if wastage_reason else list(WastageReason)[0]
        except ValueError:
            reason_enum = list(WastageReason)[0]

        quantity_wasted_dec = Decimal(str(quantity_wasted or 1))

        # ── Resolve wastage date ──────────────────────────────────────────────────
        if wastage_date is not None:
            if isinstance(wastage_date, datetime):
                wastage_date_val = wastage_date if wastage_date.tzinfo else wastage_date.replace(tzinfo=timezone.utc)
            elif isinstance(wastage_date, date):
                wastage_date_val = datetime(wastage_date.year, wastage_date.month, wastage_date.day, tzinfo=timezone.utc)
            else:
                wastage_date_val = datetime.now(timezone.utc)
        else:
            wastage_date_val = datetime.now(timezone.utc)

        wastage_calendar_date = wastage_date_val.date()

        def _safe_unit(u) -> str:
            if u is None:
                return ""
            return normalize_unit(u.value if hasattr(u, "value") else str(u))

        def _get_batches(ingredient_id: int) -> list:
            return (
                db.query(InventoryBatch)
                .filter(
                    InventoryBatch.tenant_id         == tenant_id,
                    InventoryBatch.inventory_item_id == ingredient_id,
                    InventoryBatch.is_active         == True,
                    InventoryBatch.quantity_remaining > 0,
                    func.date(InventoryBatch.date_added) <= wastage_calendar_date,
                    or_(
                        InventoryBatch.expiry_date == None,
                        InventoryBatch.expiry_date >= wastage_calendar_date,
                    ),
                )
                .order_by(InventoryBatch.created_at.desc())
                .all()
            )

        # ── Resolve SFP → flat raw ingredients (fully recursive) ─────────────────
        def resolve_sfp_to_raw(
            semi_id: int,
            qty_needed: Decimal,
            qty_unit: str,
            visited: set = None,
        ) -> list:
            if visited is None:
                visited = set()
            if semi_id in visited:
                return []
            visited = visited | {semi_id}

            semi = db.query(SemiFinishedProduct).filter(
                SemiFinishedProduct.id        == semi_id,
                SemiFinishedProduct.tenant_id == tenant_id,
                SemiFinishedProduct.is_active == True,
            ).first()
            if not semi:
                return []

            sfp_unit_norm = normalize_unit(semi.unit)
            qty_unit_norm = normalize_unit(qty_unit)

            qty_needed_converted = qty_needed
            try:
                if qty_unit_norm != sfp_unit_norm and are_units_compatible(qty_unit_norm, sfp_unit_norm):
                    qty_needed_converted = Decimal(str(
                        convert_to_base_unit(float(qty_needed), qty_unit_norm, sfp_unit_norm)
                    ))
            except Exception:
                pass

            scale = (
                qty_needed_converted / Decimal(str(semi.yield_quantity))
                if semi.yield_quantity else Decimal("1")
            )

            sub_ingredients = db.query(SemiFinishedIngredient).filter(
                SemiFinishedIngredient.semi_finished_id == semi_id,
                SemiFinishedIngredient.tenant_id        == tenant_id,
            ).all()

            result = []
            for sub in sub_ingredients:
                if getattr(sub, "is_semi_finished", False) and sub.ingredient_id:
                    nested_qty = Decimal(str(sub.quantity_required)) * scale
                    nested_sfp = db.query(SemiFinishedProduct).filter(
                        SemiFinishedProduct.id        == sub.ingredient_id,
                        SemiFinishedProduct.tenant_id == tenant_id,
                        SemiFinishedProduct.is_active == True,
                    ).first()

                    sub_unit    = normalize_unit(sub.unit)
                    nested_unit = normalize_unit(nested_sfp.unit) if nested_sfp else sub_unit

                    if nested_sfp:
                        try:
                            if sub_unit != nested_unit and are_units_compatible(sub_unit, nested_unit):
                                nested_qty = Decimal(str(
                                    convert_to_base_unit(float(nested_qty), sub_unit, nested_unit)
                                ))
                        except Exception:
                            pass

                    result.extend(resolve_sfp_to_raw(
                        semi_id    = sub.ingredient_id,
                        qty_needed = nested_qty,
                        qty_unit   = nested_unit,
                        visited    = visited,
                    ))

                elif sub.ingredient_id:
                    result.append({
                        "ingredient_id":     sub.ingredient_id,
                        "ingredient_name":   sub.ingredient_name,
                        "qty_needed":        Decimal(str(sub.quantity_required)) * scale,
                        "unit":              sub.unit,
                        "fixed_cost_amount": sub.fixed_cost_amount,
                    })

            return result

        # ── Normalise units ───────────────────────────────────────────────────────
        sfp_unit          = normalize_unit(sfp.unit if sfp else "")
        wastage_unit_norm = normalize_unit(wastage_unit) if wastage_unit else sfp_unit

        # ── Convert wasted qty into the SFP's base unit ───────────────────────────
        qty_in_sfp_unit = quantity_wasted_dec
        try:
            if wastage_unit_norm != sfp_unit and are_units_compatible(wastage_unit_norm, sfp_unit):
                qty_in_sfp_unit = Decimal(str(
                    convert_to_base_unit(float(quantity_wasted_dec), wastage_unit_norm, sfp_unit)
                ))
        except Exception:
            pass

        ingredients_flat = resolve_sfp_to_raw(semi_finished_id, qty_in_sfp_unit, sfp_unit)

        # ── Aggregate for validation ──────────────────────────────────────────────
        PIECE_UNITS  = {"pcs", "piece", "pieces"}
        PACKET_UNITS = {"packet", "packets", "pkt"}

        aggregated: dict = defaultdict(lambda: {
            "total_qty_needed":  Decimal(0),
            "unit":              None,
            "ingredient_name":   None,
            "fixed_cost_amount": None,
        })
        for ing in ingredients_flat:
            k = ing["ingredient_id"]
            aggregated[k]["total_qty_needed"] += ing["qty_needed"]
            aggregated[k]["unit"]              = ing["unit"]
            aggregated[k]["ingredient_name"]   = ing["ingredient_name"]
            if ing.get("fixed_cost_amount") is not None:
                aggregated[k]["fixed_cost_amount"] = ing["fixed_cost_amount"]

        # ── Compute SFP cost ──────────────────────────────────────────────────────
        sfp_unit_cost  = Decimal(str(sfp.unit_cost or 0)) if sfp else Decimal("0")
        total_sfp_cost = (sfp_unit_cost * qty_in_sfp_unit).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        total_fixed_cost = Decimal("0")

        # ── Create parent wastage record ──────────────────────────────────────────
        wastage_record = Wastage(
            tenant_id                = tenant_id,
            wastage_type             = WastageType.SEMI_FINISHED,
            semi_finished_product_id = semi_finished_id,
            quantity_wasted          = float(quantity_wasted_dec),
            unit                     = wastage_unit_norm,
            unit_cost                = float(sfp_unit_cost),
            cost_value               = 0,
            wastage_reason           = reason_enum,
            wastage_date             = wastage_date_val,
            notes                    = notes,
            photo_url                = photo_url,
            recorded_by_user_id      = user_id,
        )
        db.add(wastage_record)
        db.flush()

        # ── FIFO deduction ────────────────────────────────────────────────────────
        breakdown_data = []
        deduction_warnings = []

        for ing in ingredients_flat:
            inventory = db.query(Inventory).filter(
                Inventory.id        == ing["ingredient_id"],
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).first()
            batches = _get_batches(ing["ingredient_id"]) if inventory else []

            if not batches:
                deduction_warnings.append(
                f"No stock available for '{ing['ingredient_name']}' — skipped deduction."
            )
                breakdown_data.append({
                    "ingredient_id":   ing["ingredient_id"],
                    "ingredient_name": ing["ingredient_name"],
                    "qty_deducted":    Decimal(0),
                    "unit":            normalize_unit(ing["unit"]),
                    "ingredient_cost": Decimal(0),
                })
                continue

            reference_unit    = _safe_unit(batches[0].unit)
            fixed_cost_amount = ing.get("fixed_cost_amount")

            # ── Fixed-cost ingredient — same logic as record_dish_wastage ─────────
            if fixed_cost_amount is not None:
                batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
                qty_recipe      = Decimal(str(ing["qty_needed"]))

                # qty_to_deduct: how many batch units to physically pull
                # mirrors dish wastage: (fixed_cost_amount / batch_unit_cost) * qty_recipe
                qty_to_deduct = (
                    (Decimal(str(fixed_cost_amount)) / batch_unit_cost) * qty_recipe
                    if batch_unit_cost > 0 else Decimal("0")
                )
                qty_remaining   = qty_to_deduct
                ingredient_cost = Decimal("0")

                for batch in batches:
                    if qty_remaining <= Decimal("0.0000001"):
                        deduction_warnings.append(
                        f"Insufficient stock for '{ing['ingredient_name']}' — "
                        f"partially deducted. Shortfall: {round(float(qty_remaining), 4)} {reference_unit}."
                        )  
                        break

                    batch_unit         = _safe_unit(batch.unit)
                    batch_qty          = Decimal(str(batch.quantity_remaining))
                    batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
                    batch_total_cost   = Decimal(str(batch.total_cost))        if batch.total_cost        else Decimal("0")

                    qty_from_batch = min(batch_qty, qty_remaining)
                    cost = (
                        (qty_from_batch / batch_qty_received) * batch_total_cost
                        if batch_qty_received > 0 else Decimal("0")
                    )

                    batch.quantity_remaining = float(max(Decimal(0), batch_qty - qty_from_batch))
                    ingredient_cost         += cost

                    if Decimal(str(batch.quantity_remaining)) <= 0:
                        batch.is_active = False

                    db.add(batch)
                    db.add(InventoryTransaction(
                        tenant_id         = tenant_id,
                        inventory_item_id = ing["ingredient_id"],
                        batch_id          = batch.id,
                        transaction_type  = TransactionType.WASTAGE,
                        quantity          = float(qty_from_batch),
                        unit              = batch_unit,
                        unit_cost         = float(batch_unit_cost),
                        total_value       = float(cost),
                        transaction_date  = wastage_date_val,
                        reference_id      = _wastage_ref(wastage_record.id),
                    ))
                    qty_remaining -= qty_from_batch

                db.flush()
                if inventory:
                    sync_inventory_totals(ing["ingredient_id"], db)

                # actual_cost: fixed charge × scaled qty (already scaled by resolve_sfp_to_raw)
                actual_cost      = Decimal(str(fixed_cost_amount)) * qty_recipe
                total_fixed_cost += actual_cost

                breakdown_data.append({
                    "ingredient_id":   ing["ingredient_id"],
                    "ingredient_name": ing["ingredient_name"],
                    "qty_deducted":    qty_to_deduct,
                    "unit":            reference_unit,
                    "ingredient_cost": actual_cost,
                })
                continue

            # ── pcs → packet FIFO path ────────────────────────────────────────────
            dish_ing_unit = normalize_unit(ing["unit"])
            qty_needed    = ing["qty_needed"]

            if dish_ing_unit in PIECE_UNITS and reference_unit in PACKET_UNITS:
                qty_remaining_pcs = qty_needed
                ingredient_cost   = Decimal(0)

                for batch in batches:
                    if qty_remaining_pcs <= Decimal("0.0000001"):
                        deduction_warnings.append(
                        f"Insufficient stock for '{ing['ingredient_name']}' — "
                        f"partially deducted. Shortfall: {round(float(qty_remaining_pcs), 4)} {dish_ing_unit}."
                        )
                        break

                    b_pieces        = Decimal(str(batch.pieces)) if batch.pieces else Decimal("1")
                    batch_unit      = _safe_unit(batch.unit)
                    batch_qty_pkts  = Decimal(str(batch.quantity_remaining))
                    batch_qty_pcs   = batch_qty_pkts * b_pieces
                    batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)
                    cost_per_pcs    = batch_unit_cost / b_pieces if b_pieces else Decimal(0)

                    pcs_from_batch  = min(batch_qty_pcs, qty_remaining_pcs)
                    pkts_from_batch = pcs_from_batch / b_pieces

                    batch.quantity_remaining = float(max(Decimal(0), batch_qty_pkts - pkts_from_batch))
                    cost             = pcs_from_batch * cost_per_pcs
                    ingredient_cost += cost

                    if Decimal(str(batch.quantity_remaining)) <= 0:
                        batch.is_active = False

                    db.add(batch)
                    db.add(InventoryTransaction(
                        tenant_id         = tenant_id,
                        inventory_item_id = ing["ingredient_id"],
                        batch_id          = batch.id,
                        transaction_type  = TransactionType.WASTAGE,
                        quantity          = float(pkts_from_batch),
                        unit              = batch_unit,
                        unit_cost         = float(batch_unit_cost),
                        total_value       = float(cost),
                        transaction_date  = wastage_date_val,
                        reference_id      = _wastage_ref(wastage_record.id),
                    ))
                    qty_remaining_pcs -= pcs_from_batch

                db.flush()
                if inventory:
                    sync_inventory_totals(ing["ingredient_id"], db)

                breakdown_data.append({
                    "ingredient_id":   ing["ingredient_id"],
                    "ingredient_name": ing["ingredient_name"],
                    "qty_deducted":    qty_needed,
                    "unit":            dish_ing_unit,
                    "ingredient_cost": ingredient_cost,
                })
                continue

            # ── Generic FIFO path ─────────────────────────────────────────────────
            try:
                if dish_ing_unit != reference_unit and are_units_compatible(dish_ing_unit, reference_unit):
                    qty_needed = Decimal(str(
                        convert_to_base_unit(float(qty_needed), dish_ing_unit, reference_unit)
                    ))
            except Exception:
                pass

            qty_remaining   = qty_needed
            ingredient_cost = Decimal(0)

            for batch in batches:
                if qty_remaining <= Decimal("0.0000001"):
                    break

                batch_unit      = _safe_unit(batch.unit)
                batch_qty       = Decimal(str(batch.quantity_remaining))
                batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)

                try:
                    qty_in_batch_unit = qty_remaining
                    if batch_unit != reference_unit and are_units_compatible(reference_unit, batch_unit):
                        qty_in_batch_unit = Decimal(str(
                            convert_to_base_unit(float(qty_remaining), reference_unit, batch_unit)
                        ))
                except Exception:
                    qty_in_batch_unit = qty_remaining

                qty_from_batch           = min(batch_qty, qty_in_batch_unit)
                batch.quantity_remaining = float(max(Decimal(0), batch_qty - qty_from_batch))
                cost                     = qty_from_batch * batch_unit_cost
                ingredient_cost         += cost

                if Decimal(str(batch.quantity_remaining)) <= 0:
                    batch.is_active = False

                db.add(batch)
                db.add(InventoryTransaction(
                    tenant_id         = tenant_id,
                    inventory_item_id = ing["ingredient_id"],
                    batch_id          = batch.id,
                    transaction_type  = TransactionType.WASTAGE,
                    quantity          = float(qty_from_batch),
                    unit              = batch_unit,
                    unit_cost         = float(batch_unit_cost),
                    total_value       = float(cost),
                    transaction_date  = wastage_date_val,
                    reference_id      = _wastage_ref(wastage_record.id),
                ))

                try:
                    qty_deducted_ref = qty_from_batch
                    if batch_unit != reference_unit and are_units_compatible(batch_unit, reference_unit):
                        qty_deducted_ref = Decimal(str(
                            convert_to_base_unit(float(qty_from_batch), batch_unit, reference_unit)
                        ))
                except Exception:
                    qty_deducted_ref = qty_from_batch

                qty_remaining -= qty_deducted_ref

            db.flush()
            if inventory:
                sync_inventory_totals(ing["ingredient_id"], db)

            breakdown_data.append({
                "ingredient_id":   ing["ingredient_id"],
                "ingredient_name": ing["ingredient_name"],
                "qty_deducted":    qty_needed,
                "unit":            reference_unit,
                "ingredient_cost": ingredient_cost,
            })

        # ── Fold fixed costs into total and update wastage record ─────────────────
        total_sfp_cost = (total_sfp_cost + total_fixed_cost).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

        wastage_record.cost_value = float(total_sfp_cost)
        db.add(wastage_record)
        db.flush()

        # ── Breakdown children ────────────────────────────────────────────────────
        for bd in breakdown_data:
            qty_dec  = bd["qty_deducted"]    if isinstance(bd["qty_deducted"],    Decimal) else Decimal(str(bd["qty_deducted"]))
            cost_dec = bd["ingredient_cost"] if isinstance(bd["ingredient_cost"], Decimal) else Decimal(str(bd["ingredient_cost"]))
            db.add(Wastage(
                tenant_id                = tenant_id,
                wastage_type             = WastageType.INVENTORY,
                inventory_item_id        = bd["ingredient_id"],
                quantity_wasted          = float(qty_dec),
                unit                     = bd["unit"],
                unit_cost                = float(cost_dec / qty_dec) if qty_dec > 0 else 0,
                cost_value               = float(cost_dec),
                wastage_reason           = reason_enum,
                wastage_date             = wastage_date_val,
                recorded_by_user_id      = user_id,
                is_breakdown             = True,
                parent_wastage_id        = wastage_record.id,
                semi_finished_product_id = semi_finished_id,
            ))

        db.commit()
        db.refresh(wastage_record)

        return {
            "wastage_id":      str(wastage_record.id),
            "sfp_name":        sfp_name,
            "quantity_wasted": float(quantity_wasted_dec),
            "unit":            wastage_unit_norm,
            "total_cost":      float(total_sfp_cost),
            "wastage_reason":  reason_enum.value,
            "wastage_date":    wastage_record.wastage_date,
            "photo_url":       wastage_record.photo_url,
            "warnings":        deduction_warnings,
            "breakdown": [
                {
                    "ingredient_id":   bd["ingredient_id"],
                    "ingredient_name": bd["ingredient_name"],
                    "qty_deducted":    float(bd["qty_deducted"]),
                    "unit":            bd["unit"],
                    "ingredient_cost": float(bd["ingredient_cost"]),
                }
                for bd in breakdown_data
            ],
        }

    
    @staticmethod
    def record_combo_wastage(
        db: Session,
        tenant_id: int,
        combo_id: int,
        quantity_wasted: int,
        wastage_reason: str,
        user_id: int,
        notes: Optional[str] = None,
        wastage_date: Optional[datetime] = None,
        photo_url: Optional[str] = None,
    ) -> dict:

        combo = db.query(Combo).filter(
            Combo.id        == combo_id,
            Combo.tenant_id == tenant_id,
        ).first()

        combo_name = combo.name if combo else f"Combo#{combo_id}"

        try:
            reason_enum = WastageReason(wastage_reason) if wastage_reason else list(WastageReason)[0]
        except ValueError:
            reason_enum = list(WastageReason)[0]

        quantity_wasted_dec = Decimal(str(quantity_wasted or 1))

        # ── Resolve wastage date ──────────────────────────────────────────────────
        if wastage_date is not None:
            if isinstance(wastage_date, datetime):
                wastage_date_val = wastage_date if wastage_date.tzinfo else wastage_date.replace(tzinfo=timezone.utc)
            elif isinstance(wastage_date, date):
                wastage_date_val = datetime(wastage_date.year, wastage_date.month, wastage_date.day, tzinfo=timezone.utc)
            else:
                wastage_date_val = datetime.now(timezone.utc)
        else:
            wastage_date_val = datetime.now(timezone.utc)

        # ── Fetch combo items ─────────────────────────────────────────────────────
        combo_items = db.query(ComboItem).filter(
            ComboItem.combo_id  == combo_id,
            ComboItem.tenant_id == tenant_id,
        ).all() if combo else []

        if not combo_items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Combo {combo_id} has no items or does not exist.",
            )

        # ── Compute cost snapshot BEFORE any deduction ────────────────────────────
        combo_unit_cost = Decimal("0")
        item_cost_map   = {}

        for ci in combo_items:
            try:
                snapshot = _resolve_item(
                    db, tenant_id,
                    ci.dish_id,
                    ci.semi_finished_id,
                    ci.ingredient_id,
                    user_unit=ci.unit or "",
                )
                line_cost = Decimal(str(snapshot["cost_per_unit"])) * Decimal(str(ci.quantity or 1))
            except Exception:
                line_cost = Decimal(str(ci.cost_per_unit or 0)) * Decimal(str(ci.quantity or 1))

            item_cost_map[ci.id] = line_cost
            combo_unit_cost     += line_cost

        total_combo_cost = (combo_unit_cost * quantity_wasted_dec).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

        # ── Create parent wastage record ──────────────────────────────────────────
        wastage_record = Wastage(
            tenant_id           = tenant_id,
            wastage_type        = WastageType.COMBO,
            combo_id            = combo_id,
            quantity_wasted     = float(quantity_wasted_dec),
            unit                = "combo",
            unit_cost           = float(combo_unit_cost),
            cost_value          = 0,
            wastage_reason      = reason_enum,
            wastage_date        = wastage_date_val,
            notes               = notes,
            photo_url           = photo_url,
            recorded_by_user_id = user_id,
        )
        db.add(wastage_record)
        db.flush()

        # ── Deduct each combo item by delegating to existing service methods ──────
        breakdown        = []
        combo_warnings   = []

        for ci in combo_items:
            qty_for_item = Decimal(str(ci.quantity or 1)) * quantity_wasted_dec

            # ── Dish item ─────────────────────────────────────────────────────────
            if ci.dish_id:
                try:
                    result = WastageService.record_dish_wastage(
                        db              = db,
                        tenant_id       = tenant_id,
                        dish_id         = ci.dish_id,
                        quantity_wasted = int(qty_for_item),
                        wastage_reason  = wastage_reason,
                        user_id         = user_id,
                        wastage_date    = wastage_date_val,
                    )
                    child = db.query(Wastage).filter(Wastage.id == result["wastage_id"]).first()
                    if child:
                        child.parent_wastage_id = wastage_record.id
                        child.is_breakdown      = True
                        db.add(child)

                    if result.get("warnings"):
                        combo_warnings.extend(result["warnings"])

                    breakdown.append({
                        "type":    "dish",
                        "id":      ci.dish_id,
                        "name":    result.get("dish_name"),
                        "qty":     float(qty_for_item),
                        "cost":    result.get("total_cost", 0),
                        "warnings": result.get("warnings", []),
                    })
                except HTTPException as e:
                    raise HTTPException(
                        status_code=e.status_code,
                        detail=f"Combo item (dish_id={ci.dish_id}): {e.detail}",
                    )

            # ── Semi-finished item ────────────────────────────────────────────────
            elif ci.semi_finished_id:
                _sfp = db.query(SemiFinishedProduct).filter(
                    SemiFinishedProduct.id        == ci.semi_finished_id,
                    SemiFinishedProduct.tenant_id == tenant_id,
                    SemiFinishedProduct.is_active == True,
                ).first()
                _sfp_unit = (
                    (_sfp.unit.value if hasattr(_sfp.unit, "value") else str(_sfp.unit))
                    if _sfp and _sfp.unit else "gm"
                )
                wastage_unit = ci.unit if ci.unit else _sfp_unit

                try:
                    result = WastageService.record_semi_finished_wastage(
                        db               = db,
                        tenant_id        = tenant_id,
                        semi_finished_id = ci.semi_finished_id,
                        quantity_wasted  = float(qty_for_item),
                        wastage_unit     = wastage_unit,
                        wastage_reason   = wastage_reason,
                        user_id          = user_id,
                        wastage_date     = wastage_date_val,
                    )
                    child = db.query(Wastage).filter(Wastage.id == result["wastage_id"]).first()
                    if child:
                        child.parent_wastage_id = wastage_record.id
                        child.is_breakdown      = True
                        db.add(child)

                    if result.get("warnings"):
                        combo_warnings.extend(result["warnings"])

                    breakdown.append({
                        "type":     "semi_finished",
                        "id":       ci.semi_finished_id,
                        "name":     result.get("sfp_name"),
                        "qty":      float(qty_for_item),
                        "cost":     result.get("total_cost", 0),
                        "warnings": result.get("warnings", []),
                    })
                except HTTPException as e:
                    raise HTTPException(
                        status_code=e.status_code,
                        detail=f"Combo item (semi_finished_id={ci.semi_finished_id}): {e.detail}",
                    )

            # ── Raw inventory item ────────────────────────────────────────────────
            elif ci.ingredient_id:
                if not ci.unit:
                    _inv_item = db.query(Inventory).filter(
                        Inventory.id        == ci.ingredient_id,
                        Inventory.tenant_id == tenant_id,
                    ).first()
                    _inv_unit = (
                        (_inv_item.unit.value if hasattr(_inv_item.unit, "value") else str(_inv_item.unit))
                        if _inv_item and _inv_item.unit else "gm"
                    )
                else:
                    _inv_unit = ci.unit

                _wastage_date_for_schema = (
                    wastage_date_val.date()
                    if isinstance(wastage_date_val, datetime)
                    else wastage_date_val
                )

                data = RecordInventoryWastage(
                    inventory_item_id  = ci.ingredient_id,
                    inventory_batch_id = None,
                    quantity_wasted    = qty_for_item,
                    unit               = _inv_unit,
                    wastage_reason     = reason_enum,
                    wastage_date       = _wastage_date_for_schema,
                )
                try:
                    record = WastageService.record_inventory_wastage(
                        db        = db,
                        tenant_id = tenant_id,
                        data      = data,
                        user_id   = user_id,
                    )
                    record.parent_wastage_id = wastage_record.id
                    record.is_breakdown      = True
                    db.add(record)

                    _warn = getattr(record, "_deduction_warning", None)
                    if _warn:
                        combo_warnings.append(_warn)

                    breakdown.append({
                        "type":    "inventory",
                        "id":      ci.ingredient_id,
                        "name":    ci.item_name,
                        "qty":     float(qty_for_item),
                        "cost":    float(record.cost_value or 0),
                        "warning": _warn,
                    })
                except HTTPException as e:
                    raise HTTPException(
                        status_code=e.status_code,
                        detail=f"Combo item (ingredient_id={ci.ingredient_id}): {e.detail}",
                    )

        # ── Finalise parent record ────────────────────────────────────────────────
        wastage_record.cost_value = float(total_combo_cost)
        db.add(wastage_record)
        db.commit()

        return {
            "wastage_id":      str(wastage_record.id),
            "combo_name":      combo_name,
            "quantity_wasted": int(quantity_wasted_dec),
            "total_cost":      float(total_combo_cost),
            "wastage_reason":  reason_enum.value,
            "wastage_date":    wastage_date_val,
            "photo_url":       photo_url,
            "breakdown":       breakdown,
            "warnings":        combo_warnings,
        }
    
    @staticmethod
    def edit_wastage(
        db: Session,
        tenant_id: int,
        wastage_id: UUID,
        user_id: int,
        wastage_reason: Optional[str] = None,
        notes: Optional[str] = None,
        wastage_date: Optional[date] = None,
        photo_url: Optional[str] = None,
        quantity_wasted: Optional[float] = None,
        unit: Optional[str] = None,
        inventory_item_id: Optional[int] = None,
        inventory_batch_id: Optional[int] = None,
        dish_id: Optional[int] = None,
        semi_finished_product_id: Optional[int] = None,
        combo_id: Optional[int] = None,
    ) -> dict:

        # ── 1. Fetch parent wastage record ──────────────────────────────────────
        wastage = (
            db.query(Wastage)
            .filter(
                Wastage.id == wastage_id,
                Wastage.tenant_id == tenant_id,
                Wastage.is_breakdown == False,
            )
            .first()
        )

        if not wastage:
            raise ValueError(f"Wastage record {wastage_id} not found")

        wastage_type = wastage.wastage_type
        logger.info("[EDIT WASTAGE] START wastage_id=%s type=%s", wastage_id, wastage_type)

        # ── 2. Determine what changed ────────────────────────────────────────────
        new_qty      = quantity_wasted if quantity_wasted is not None else float(wastage.quantity_wasted)
        new_unit     = unit or wastage.unit
        new_item_id  = inventory_item_id        if inventory_item_id        is not None else wastage.inventory_item_id
        new_batch_id = inventory_batch_id       if inventory_batch_id       is not None else wastage.inventory_batch_id
        new_dish_id  = dish_id                  if dish_id                  is not None else wastage.dish_id
        new_sfp_id   = semi_finished_product_id if semi_finished_product_id is not None else wastage.semi_finished_product_id
        new_combo_id = combo_id                 if combo_id                 is not None else wastage.combo_id

        qty_explicitly_sent = quantity_wasted          is not None
        item_changed        = inventory_item_id        is not None and inventory_item_id        != wastage.inventory_item_id
        batch_changed       = inventory_batch_id       is not None and inventory_batch_id       != wastage.inventory_batch_id
        dish_changed        = dish_id                  is not None and dish_id                  != wastage.dish_id
        sfp_changed         = semi_finished_product_id is not None and semi_finished_product_id != wastage.semi_finished_product_id
        combo_changed       = combo_id                 is not None and combo_id                 != wastage.combo_id
        needs_rededuct      = qty_explicitly_sent or item_changed or batch_changed or dish_changed or sfp_changed or combo_changed

        logger.info(
            "[EDIT WASTAGE] qty_explicitly_sent=%s item_changed=%s batch_changed=%s "
            "dish_changed=%s sfp_changed=%s combo_changed=%s needs_rededuct=%s",
            qty_explicitly_sent, item_changed, batch_changed,
            dish_changed, sfp_changed, combo_changed, needs_rededuct,
        )

        # ── 3. Patch simple fields ───────────────────────────────────────────────
        if wastage_reason is not None:
            try:
                wastage.wastage_reason = WastageReason(wastage_reason)
            except ValueError:
                raise ValueError(
                    f"Invalid wastage_reason. Allowed: {[r.value for r in WastageReason]}"
                )

        if notes is not None:
            wastage.notes = notes

        if wastage_date is not None:
            wastage.wastage_date = datetime(
                wastage_date.year, wastage_date.month, wastage_date.day,
                0, 0, 0, tzinfo=timezone.utc,
            )

        if photo_url:
            wastage.photo_url = photo_url

        # ── 4. Simple patch only ─────────────────────────────────────────────────
        if not needs_rededuct:
            logger.info("[EDIT WASTAGE] No re-deduction needed – patching simple fields only")
            db.add(wastage)
            db.commit()
            db.refresh(wastage)
            return WastageService._format_wastage_response(wastage)

        # ── 5. FIFO REVERSAL ─────────────────────────────────────────────────────
        ref_id = _wastage_ref(wastage_id)
        logger.info("[EDIT WASTAGE] Reversing transactions with reference_id='%s'", ref_id)

        txns_to_reverse = (
            db.query(InventoryTransaction)
            .filter(
                InventoryTransaction.tenant_id        == tenant_id,
                InventoryTransaction.transaction_type == TransactionType.WASTAGE,
                InventoryTransaction.reference_id     == ref_id,
            )
            .all()
        )

        logger.info("[EDIT WASTAGE] txns_to_reverse count=%d", len(txns_to_reverse))

        reversed_item_ids = {txn.inventory_item_id for txn in txns_to_reverse if txn.inventory_item_id}

        for txn in txns_to_reverse:
            logger.info(
                "[EDIT WASTAGE] Reversing txn id=%s batch_id=%s qty=%s unit=%s",
                txn.id, txn.batch_id, txn.quantity, txn.unit,
            )
            batch = (
                db.query(InventoryBatch)
                .filter(
                    InventoryBatch.id        == txn.batch_id,
                    InventoryBatch.tenant_id == tenant_id,
                )
                .first()
            )
            if batch:
                old_qty = batch.quantity_remaining
                batch.quantity_remaining = float(
                    Decimal(str(batch.quantity_remaining)) + Decimal(str(txn.quantity))
                )
                if batch.quantity_remaining > 0:
                    batch.is_active = True
                db.add(batch)
                logger.info(
                    "[EDIT WASTAGE] Reversed batch id=%s qty_remaining: %s → %s",
                    batch.id, old_qty, batch.quantity_remaining,
                )
            else:
                logger.warning(
                    "[EDIT WASTAGE] Batch NOT FOUND for txn id=%s batch_id=%s",
                    txn.id, txn.batch_id,
                )
            db.delete(txn)

        # ── For COMBO: also reverse transactions tied to child wastage records ──
        if wastage_type == WastageType.COMBO:
            child_wastages = db.query(Wastage).filter(
                Wastage.parent_wastage_id == wastage_id,
                Wastage.tenant_id         == tenant_id,
            ).all()

            child_wastage_ids = [str(w.id) for w in child_wastages]

            for child_id in child_wastage_ids:
                child_ref_id = _wastage_ref(child_id)
                child_txns = (
                    db.query(InventoryTransaction)
                    .filter(
                        InventoryTransaction.tenant_id        == tenant_id,
                        InventoryTransaction.transaction_type == TransactionType.WASTAGE,
                        InventoryTransaction.reference_id     == child_ref_id,
                    )
                    .all()
                )
                logger.info(
                    "[EDIT WASTAGE] COMBO child ref=%s txns_to_reverse=%d",
                    child_ref_id, len(child_txns),
                )
                for txn in child_txns:
                    batch = (
                        db.query(InventoryBatch)
                        .filter(
                            InventoryBatch.id        == txn.batch_id,
                            InventoryBatch.tenant_id == tenant_id,
                        )
                        .first()
                    )
                    if batch:
                        old_qty = batch.quantity_remaining
                        batch.quantity_remaining = float(
                            Decimal(str(batch.quantity_remaining)) + Decimal(str(txn.quantity))
                        )
                        if batch.quantity_remaining > 0:
                            batch.is_active = True
                        db.add(batch)
                        reversed_item_ids.add(txn.inventory_item_id)
                        logger.info(
                            "[EDIT WASTAGE] COMBO child reversed batch id=%s qty: %s → %s",
                            batch.id, old_qty, batch.quantity_remaining,
                        )
                    db.delete(txn)

                # Delete grandchildren (breakdown rows of each child dish/sfp wastage)
                db.query(Wastage).filter(
                    Wastage.parent_wastage_id == child_id,
                    Wastage.tenant_id         == tenant_id,
                ).delete(synchronize_session=False)

            # Delete child wastage records (dish/sfp level rows under this combo wastage)
            db.query(Wastage).filter(
                Wastage.parent_wastage_id == wastage_id,
                Wastage.tenant_id         == tenant_id,
            ).delete(synchronize_session=False)

        else:
            # For INVENTORY / DISH / SEMI_FINISHED: delete direct breakdown children
            db.query(Wastage).filter(
                Wastage.parent_wastage_id == wastage_id,
                Wastage.tenant_id         == tenant_id,
            ).delete(synchronize_session=False)

        db.flush()

        for item_id in reversed_item_ids:
            sync_inventory_totals(item_id, db)

        db.flush()
        db.refresh(wastage)
        logger.info("[EDIT WASTAGE] Reversal flushed (will commit together with re-deduction)")
        # Re-fetch wastage after commit
        wastage = (
            db.query(Wastage)
            .filter(Wastage.id == wastage_id, Wastage.tenant_id == tenant_id)
            .first()
        )

        # ── Build wastage_date_val ───────────────────────────────────────────────
        if wastage_date is not None:
            wastage_date_val = datetime(
                wastage_date.year, wastage_date.month, wastage_date.day,
                0, 0, 0, tzinfo=timezone.utc,
            )
        elif wastage.wastage_date is not None:
            if isinstance(wastage.wastage_date, datetime):
                wastage_date_val = (
                    wastage.wastage_date if wastage.wastage_date.tzinfo
                    else wastage.wastage_date.replace(tzinfo=timezone.utc)
                )
            else:
                wastage_date_val = datetime(
                    wastage.wastage_date.year, wastage.wastage_date.month, wastage.wastage_date.day,
                    0, 0, 0, tzinfo=timezone.utc,
                )
        else:
            wastage_date_val = datetime.now(timezone.utc)

        wastage_calendar_date = wastage_date_val.date()
        recorded_at           = wastage_date_val

        # ════════════════════════════════════════════════════════════════════════
        # 6a. INVENTORY RE-DEDUCTION
        # ════════════════════════════════════════════════════════════════════════
        if wastage_type == WastageType.INVENTORY:
            if not new_item_id:
                raise ValueError("inventory_item_id is required for inventory wastage")
            if not new_unit:
                raise ValueError("unit is required for inventory wastage")

            item = (
                db.query(Inventory)
                .filter(
                    Inventory.id        == new_item_id,
                    Inventory.tenant_id == tenant_id,
                    Inventory.is_active == True,
                )
                .first()
            )

            batches_query = []
            if item:
                batches_query = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == new_item_id,
                        InventoryBatch.is_active         == True,
                        InventoryBatch.quantity_remaining > 0,
                        func.date(InventoryBatch.date_added) <= wastage_calendar_date,
                    )
                    .order_by(InventoryBatch.expiry_date.asc().nullslast(), InventoryBatch.date_added.asc())
                    .all()
                )
                if not batches_query:
                    batches_query = (
                        db.query(InventoryBatch)
                        .filter(
                            InventoryBatch.tenant_id         == tenant_id,
                            InventoryBatch.inventory_item_id == new_item_id,
                            InventoryBatch.quantity_remaining > 0,
                            func.date(InventoryBatch.date_added) <= wastage_calendar_date,
                        )
                        .order_by(InventoryBatch.expiry_date.asc().nullslast(), InventoryBatch.date_added.asc())
                        .all()
                    )
                if not batches_query:
                    batches_query = (
                        db.query(InventoryBatch)
                        .filter(
                            InventoryBatch.tenant_id         == tenant_id,
                            InventoryBatch.inventory_item_id == new_item_id,
                            InventoryBatch.quantity_remaining > 0,
                        )
                        .order_by(InventoryBatch.expiry_date.asc().nullslast(), InventoryBatch.date_added.asc())
                        .all()
                    )
                if new_batch_id:
                    batches_query = [b for b in batches_query if b.id == new_batch_id]

            reference_unit = normalize_unit(
                batches_query[0].unit if batches_query and batches_query[0].unit
                else (item.unit if item else new_unit)
            )

            is_fixed_cost = bool(item and item.is_fixed_cost)

            if is_fixed_cost:
                batch_unit_cost = Decimal(str(batches_query[0].unit_cost or 0)) if batches_query else Decimal("0")
                qty_in_reference_unit = (
                    Decimal(str(new_qty)) / batch_unit_cost if batch_unit_cost > 0 else Decimal("0")
                )
            else:
                wastage_unit = normalize_unit(new_unit)
                PIECE_UNITS  = {"pcs", "piece", "pieces"}
                PACKET_UNITS = {"packet", "packets", "pkt"}
                if wastage_unit in PIECE_UNITS and reference_unit in PACKET_UNITS:
                    pieces_per_packet = (
                        Decimal(str(batches_query[0].pieces))
                        if batches_query and batches_query[0].pieces else Decimal("1")
                    )
                    qty_in_reference_unit = Decimal(str(new_qty)) / pieces_per_packet
                else:
                    try:
                        if wastage_unit != reference_unit and are_units_compatible(wastage_unit, reference_unit):
                            qty_in_reference_unit = Decimal(str(
                                convert_to_base_unit(float(new_qty), wastage_unit, reference_unit)
                            ))
                        else:
                            qty_in_reference_unit = Decimal(str(new_qty))
                    except Exception:
                        qty_in_reference_unit = Decimal(str(new_qty))

            if not is_fixed_cost:
                if not batches_query:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"No stock available for '{item.name if item else new_item_id}'.",
                    )
                total_available = Decimal(0)
                for b in batches_query:
                    b_unit = normalize_unit(b.unit if b.unit else (item.unit if item else new_unit))
                    b_qty  = Decimal(str(b.quantity_remaining))
                    try:
                        if b_unit != reference_unit and are_units_compatible(b_unit, reference_unit):
                            b_qty = Decimal(str(convert_to_base_unit(float(b_qty), b_unit, reference_unit)))
                    except Exception:
                        pass
                    total_available += b_qty

                if qty_in_reference_unit > total_available:
                    try:
                        input_unit = normalize_unit(new_unit)
                        available_in_input_unit = (
                            convert_to_base_unit(float(total_available), reference_unit, input_unit)
                            if reference_unit != input_unit else float(total_available)
                        )
                    except Exception:
                        available_in_input_unit = float(total_available)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Insufficient stock for '{item.name if item else new_item_id}'. "
                            f"Requested: {float(new_qty)} {new_unit}, "
                            f"Available: {round(available_in_input_unit, 4)} {new_unit}."
                        ),
                    )

            qty_remaining = qty_in_reference_unit
            total_cost    = Decimal(0)

            for batch in batches_query:
                if qty_remaining <= 0:
                    break

                batch_unit      = normalize_unit(batch.unit if batch.unit else (item.unit if item else new_unit))
                batch_qty       = Decimal(str(batch.quantity_remaining))
                batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)

                try:
                    qty_needed_in_batch_unit = (
                        Decimal(str(convert_to_base_unit(float(qty_remaining), reference_unit, batch_unit)))
                        if batch_unit != reference_unit else qty_remaining
                    )
                except Exception:
                    qty_needed_in_batch_unit = qty_remaining

                qty_from_batch           = min(batch_qty, qty_needed_in_batch_unit)
                batch.quantity_remaining = float(max(Decimal(0), batch_qty - qty_from_batch))

                if is_fixed_cost:
                    batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
                    batch_total_cost   = Decimal(str(batch.total_cost))        if batch.total_cost        else Decimal("0")
                    cost = (qty_from_batch / batch_qty_received) * batch_total_cost if batch_qty_received > 0 else Decimal("0")
                else:
                    cost = qty_from_batch * batch_unit_cost

                total_cost += cost

                if Decimal(str(batch.quantity_remaining)) <= 0:
                    batch.is_active = False

                db.add(batch)
                db.add(InventoryTransaction(
                    tenant_id         = tenant_id,
                    inventory_item_id = new_item_id,
                    batch_id          = batch.id,
                    transaction_type  = TransactionType.WASTAGE,
                    quantity          = float(qty_from_batch),
                    unit              = batch_unit,
                    unit_cost         = float(batch_unit_cost),
                    total_value       = float(cost),
                    transaction_date  = recorded_at,
                    reference_id      = ref_id,
                ))

                try:
                    qty_deducted_in_ref = (
                        Decimal(str(convert_to_base_unit(float(qty_from_batch), batch_unit, reference_unit)))
                        if batch_unit != reference_unit else qty_from_batch
                    )
                except Exception:
                    qty_deducted_in_ref = qty_from_batch

                qty_remaining -= qty_deducted_in_ref
                logger.info(
                    "[EDIT WASTAGE] batch id=%s deducted=%s(%s) qty_remaining_ref=%s",
                    batch.id, qty_from_batch, batch_unit, qty_remaining,
                )

            db.flush()

            unit_cost = Decimal(0)
            if batches_query and batches_query[0].unit_cost:
                unit_cost = Decimal(str(batches_query[0].unit_cost))
            elif item:
                unit_cost = Decimal(str(item.unit_cost or item.price_per_unit or 0))

            if is_fixed_cost:
                total_cost = Decimal(str(new_qty))

            if item:
                sync_inventory_totals(new_item_id, db)

            _COST_DP   = Decimal("0.01")
            total_cost = total_cost.quantize(_COST_DP)

            wastage.inventory_item_id  = new_item_id
            wastage.inventory_batch_id = new_batch_id
            wastage.quantity_wasted    = float(new_qty)
            wastage.unit               = new_unit
            wastage.unit_cost          = float(unit_cost.quantize(_COST_DP))
            wastage.cost_value         = float(total_cost)
            if wastage_date is not None:
                wastage.wastage_date = wastage_date_val

            db.add(wastage)
            db.commit()
            db.refresh(wastage)
            return WastageService._format_wastage_response(wastage)

        # ════════════════════════════════════════════════════════════════════════
        # 6b. DISH RE-DEDUCTION
        # ════════════════════════════════════════════════════════════════════════
        elif wastage_type == WastageType.DISH:
            if not new_dish_id:
                raise ValueError("dish_id is required for dish wastage")

            dish = (
                db.query(Dish)
                .filter(Dish.id == new_dish_id, Dish.tenant_id == tenant_id, Dish.is_active == True)
                .first()
            )
            dish_name           = dish.name if dish else f"Dish#{new_dish_id}"
            quantity_wasted_int = int(new_qty)

            logger.info(
                "[EDIT WASTAGE] Dish re-deduction: dish_id=%s dish_name=%s qty=%s",
                new_dish_id, dish_name, quantity_wasted_int,
            )

            dish_ingredients_all = []
            if dish:
                dish_ingredients_all = (
                    db.query(DishIngredient)
                    .filter(DishIngredient.dish_id == new_dish_id, DishIngredient.tenant_id == tenant_id)
                    .all()
                )

            raw_ingredients  = [di for di in dish_ingredients_all if di.semi_finished_id is None]
            semi_ingredients = [di for di in dish_ingredients_all if di.semi_finished_id is not None]

            ingredients_to_deduct = []

            for di in raw_ingredients:
                if not di.ingredient_id:
                    continue
                ingredients_to_deduct.append({
                    "ingredient_id":        di.ingredient_id,
                    "ingredient_name":      di.ingredient_name,
                    "qty_needed":           Decimal(str(di.quantity_required)) * quantity_wasted_int,
                    "unit":                 di.unit,
                    "fixed_cost_amount":    di.fixed_cost_amount,
                    "recipe_cost_per_unit": Decimal(str(di.cost_per_unit)) if di.cost_per_unit else None,
                    "source":               "raw",
                    "semi_finished_id":     None,
                    "semi_finished_name":   None,
                    "semi_finished_qty":    None,
                    "semi_finished_unit":   None,
                })

            if semi_ingredients:
                semi_finished_ids = list({di.semi_finished_id for di in semi_ingredients})
                semi_product_map = {
                    s.id: s
                    for s in db.query(SemiFinishedProduct).filter(
                        SemiFinishedProduct.id.in_(semi_finished_ids),
                        SemiFinishedProduct.tenant_id == tenant_id,
                        SemiFinishedProduct.is_active == True,
                    ).all()
                }
                sub_ing_map: dict = defaultdict(list)
                for sub in db.query(SemiFinishedIngredient).filter(
                    SemiFinishedIngredient.semi_finished_id.in_(semi_finished_ids),
                    SemiFinishedIngredient.tenant_id == tenant_id,
                ).all():
                    sub_ing_map[sub.semi_finished_id].append(sub)

                for di in semi_ingredients:
                    semi = semi_product_map.get(di.semi_finished_id)
                    if not semi:
                        continue
                    dish_sfp_unit   = normalize_unit(di.unit)
                    semi_yield_unit = normalize_unit(semi.unit)
                    qty_sfp_needed  = Decimal(str(di.quantity_required)) * quantity_wasted_int
                    try:
                        if dish_sfp_unit != semi_yield_unit:
                            qty_sfp_needed = Decimal(str(
                                convert_to_base_unit(float(qty_sfp_needed), dish_sfp_unit, semi_yield_unit)
                            ))
                    except Exception:
                        pass
                    scale_factor = (
                        qty_sfp_needed / Decimal(str(semi.yield_quantity))
                        if semi.yield_quantity else Decimal(1)
                    )
                    for sub_ing in sub_ing_map.get(semi.id, []):
                        if not sub_ing.ingredient_id:
                            continue
                        ingredients_to_deduct.append({
                            "ingredient_id":        sub_ing.ingredient_id,
                            "ingredient_name":      sub_ing.ingredient_name,
                            "qty_needed":           Decimal(str(sub_ing.quantity_required)) * scale_factor,
                            "unit":                 sub_ing.unit,
                            "fixed_cost_amount":    sub_ing.fixed_cost_amount,
                            "recipe_cost_per_unit": Decimal(str(sub_ing.cost_per_unit)) if getattr(sub_ing, "cost_per_unit", None) else None,
                            "source":               "semi_finished",
                            "semi_finished_id":     semi.id,
                            "semi_finished_name":   semi.name,
                            "semi_finished_qty":    float(qty_sfp_needed),
                            "semi_finished_unit":   semi_yield_unit,
                        })

            logger.info("[EDIT WASTAGE] ingredients_to_deduct count=%d", len(ingredients_to_deduct))

            def _get_batches_for_ingredient(ingredient_id: int) -> list:
                result = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == ingredient_id,
                        InventoryBatch.is_active         == True,
                        InventoryBatch.quantity_remaining > 0,
                        func.date(InventoryBatch.date_added) <= wastage_calendar_date,
                    )
                    .order_by(InventoryBatch.expiry_date.asc().nullslast(), InventoryBatch.date_added.asc())
                    .all()
                )
                if result:
                    return result
                result = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == ingredient_id,
                        InventoryBatch.quantity_remaining > 0,
                        func.date(InventoryBatch.date_added) <= wastage_calendar_date,
                    )
                    .order_by(InventoryBatch.expiry_date.asc().nullslast(), InventoryBatch.date_added.asc())
                    .all()
                )
                if result:
                    return result
                return (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == ingredient_id,
                        InventoryBatch.quantity_remaining > 0,
                    )
                    .order_by(InventoryBatch.expiry_date.asc().nullslast(), InventoryBatch.date_added.asc())
                    .all()
                )

            def _safe_convert(qty: Decimal, from_unit: str, to_unit: str) -> Decimal:
                if from_unit == to_unit:
                    return qty
                try:
                    if are_units_compatible(from_unit, to_unit):
                        return Decimal(str(convert_to_base_unit(float(qty), from_unit, to_unit)))
                except Exception:
                    pass
                return qty

            # ── Validate all ingredients BEFORE any deduction ────────────────────
            validation_errors = []
            for ing in ingredients_to_deduct:
                if ing.get("fixed_cost_amount") is not None:
                    continue
                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.id        == ing["ingredient_id"],
                        Inventory.tenant_id == tenant_id,
                        Inventory.is_active == True,
                    )
                    .first()
                )
                batches = _get_batches_for_ingredient(ing["ingredient_id"]) if inventory else []
                if not batches:
                    validation_errors.append(f"No stock available for '{ing['ingredient_name']}'.")
                    continue

                PIECE_UNITS  = {"pcs", "piece", "pieces"}
                PACKET_UNITS = {"packet", "packets", "pkt"}

                ref_unit   = normalize_unit(batches[0].unit if batches[0].unit else ing["unit"])
                ing_unit   = normalize_unit(ing["unit"])
                qty_needed = _safe_convert(ing["qty_needed"], ing_unit, ref_unit)

                if ing_unit in PIECE_UNITS and ref_unit in PACKET_UNITS:
                    total_avail_pcs = Decimal(0)
                    for b in batches:
                        b_pieces = Decimal(str(b.pieces)) if b.pieces else Decimal("1")
                        total_avail_pcs += Decimal(str(b.quantity_remaining)) * b_pieces

                    if qty_needed > total_avail_pcs:
                    # available_in_ing_unit = _safe_convert(total_available, ref_unit, ing_unit)
                        validation_errors.append(
                            f"Insufficient stock for '{ing['ingredient_name']}'. "
                            f"Requested: {float(ing['qty_needed'])} {ing['unit']}, "
                            f"Available: {round(float(total_avail_pcs), 4)} {ing['unit']}."
                        )
                    continue       

            if validation_errors:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"errors": validation_errors},
                )

            _COST_DP        = Decimal("0.01")
            total_dish_cost = Decimal(0)
            breakdown_data  = []
            reason_enum     = wastage.wastage_reason

            for ing in ingredients_to_deduct:
                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.id        == ing["ingredient_id"],
                        Inventory.tenant_id == tenant_id,
                        Inventory.is_active == True,
                    )
                    .first()
                )
                batches = _get_batches_for_ingredient(ing["ingredient_id"]) if inventory else []

                logger.info(
                    "[EDIT WASTAGE] Deducting ingredient id=%s name=%s qty_needed=%s unit=%s batches=%d",
                    ing["ingredient_id"], ing["ingredient_name"], ing["qty_needed"], ing["unit"], len(batches),
                )

                if not batches:
                    breakdown_data.append({
                        "ingredient_id":      ing["ingredient_id"],
                        "ingredient_name":    ing["ingredient_name"],
                        "qty_deducted":       ing["qty_needed"],
                        "unit":               normalize_unit(ing["unit"]),
                        "ingredient_cost":    Decimal(0),
                        "source":             ing["source"],
                        "semi_finished_id":   ing["semi_finished_id"],
                        "semi_finished_name": ing["semi_finished_name"],
                        "semi_finished_qty":  ing.get("semi_finished_qty"),
                        "semi_finished_unit": ing.get("semi_finished_unit"),
                    })
                    continue

                reference_unit    = normalize_unit(batches[0].unit if batches[0].unit else ing["unit"])
                fixed_cost_amount = ing.get("fixed_cost_amount")

                if fixed_cost_amount is not None:
                    batch_unit_cost = Decimal(str(batches[0].unit_cost or 0))
                    qty_recipe      = Decimal(str(ing["qty_needed"]))
                    qty_to_deduct   = (
                        (Decimal(str(fixed_cost_amount)) / batch_unit_cost) * qty_recipe
                        if batch_unit_cost > 0 else Decimal("0")
                    )
                    qty_remaining   = qty_to_deduct
                    ingredient_cost = Decimal("0")

                    for batch in batches:
                        if qty_remaining <= 0:
                            break
                        batch_qty          = Decimal(str(batch.quantity_remaining))
                        batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
                        batch_total_cost   = Decimal(str(batch.total_cost))        if batch.total_cost        else Decimal("0")
                        qty_from_batch     = min(batch_qty, qty_remaining)
                        cost = (
                            (qty_from_batch / batch_qty_received) * batch_total_cost
                            if batch_qty_received > 0 else Decimal("0")
                        )
                        batch.quantity_remaining = float(batch_qty - qty_from_batch)
                        ingredient_cost += cost
                        if Decimal(str(batch.quantity_remaining)) <= 0:
                            batch.is_active = False
                        db.add(batch)
                        db.add(InventoryTransaction(
                            tenant_id         = tenant_id,
                            inventory_item_id = ing["ingredient_id"],
                            batch_id          = batch.id,
                            transaction_type  = TransactionType.WASTAGE,
                            quantity          = float(qty_from_batch),
                            unit              = normalize_unit(batch.unit),
                            unit_cost         = float(batch_unit_cost),
                            total_value       = float(cost),
                            transaction_date  = recorded_at,
                            reference_id      = ref_id,
                        ))
                        qty_remaining -= qty_from_batch

                    db.flush()
                    if inventory:
                        sync_inventory_totals(ing["ingredient_id"], db)

                    actual_cost = Decimal(str(fixed_cost_amount)) * quantity_wasted_int
                    total_dish_cost += actual_cost
                    breakdown_data.append({
                        "ingredient_id":      ing["ingredient_id"],
                        "ingredient_name":    ing["ingredient_name"],
                        "qty_deducted":       qty_to_deduct,
                        "unit":               reference_unit,
                        "ingredient_cost":    actual_cost,
                        "source":             ing["source"],
                        "semi_finished_id":   ing["semi_finished_id"],
                        "semi_finished_name": ing["semi_finished_name"],
                        "semi_finished_qty":  ing.get("semi_finished_qty"),
                        "semi_finished_unit": ing.get("semi_finished_unit"),
                    })
                    continue

                dish_ing_unit        = normalize_unit(ing["unit"])
                qty_needed_original  = ing["qty_needed"]
                recipe_cost_per_unit = ing.get("recipe_cost_per_unit")

                PIECE_UNITS  = {"pcs", "piece", "pieces"}
                PACKET_UNITS = {"packet", "packets", "pkt"}

                qty_needed_ref       = _safe_convert(qty_needed_original, dish_ing_unit, reference_unit)
                qty_remaining        = qty_needed_ref
                ingredient_cost = Decimal(0)   # initialize here too
                batch_qty = Decimal(0)
                qty_from_batch     = Decimal(0)
                qty_deducted_in_ref = Decimal(0)
                batch_unit         = reference_unit
                batch_unit_cost    = Decimal(0)

                # logger.info(
                #     "[EDIT WASTAGE] ingredient id=%s name=%s dish_unit=%s reference_unit=%s "
                #     "qty_needed_original=%s qty_needed_ref=%s",
                #     ing["ingredient_id"], ing["ingredient_name"],
                #     dish_ing_unit, reference_unit, qty_needed_original, qty_needed_ref,
                # )

                if dish_ing_unit in PIECE_UNITS and reference_unit in PACKET_UNITS:
                    qty_remaining_pcs = qty_needed_original   # still in pcs
                    ingredient_cost   = Decimal(0)

                    for batch in batches:
                        if qty_remaining_pcs <= Decimal("0.0000001"):
                            break
                        b_pieces        = Decimal(str(batch.pieces)) if batch.pieces else Decimal("1")
                        batch_unit      = normalize_unit(batch.unit if batch.unit else ing["unit"])
                        batch_qty_pkts  = Decimal(str(batch.quantity_remaining))
                        batch_qty_pcs   = batch_qty_pkts * b_pieces
                        batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)
                        cost_per_pcs    = batch_unit_cost / b_pieces if b_pieces else Decimal(0)

                        pcs_from_batch  = min(batch_qty_pcs, qty_remaining_pcs)
                        pkts_from_batch = pcs_from_batch / b_pieces

                        batch.quantity_remaining = float(max(Decimal(0), batch_qty_pkts - pkts_from_batch))
                        cost             = pcs_from_batch * cost_per_pcs
                        ingredient_cost += cost

                        if Decimal(str(batch.quantity_remaining)) <= 0:
                            batch.is_active = False

                        db.add(batch)
                        db.add(InventoryTransaction(
                            tenant_id         = tenant_id,
                            inventory_item_id = ing["ingredient_id"],
                            batch_id          = batch.id,
                            transaction_type  = TransactionType.WASTAGE,
                            quantity          = float(pkts_from_batch),
                            unit              = batch_unit,
                            unit_cost         = float(batch_unit_cost),
                            total_value       = float(cost),
                            transaction_date  = recorded_at,
                            reference_id      = ref_id,
                        ))
                        qty_remaining_pcs -= pcs_from_batch

                        logger.info(
                            "[EDIT WASTAGE] batch id=%s batch_unit=%s batch_qty_before=%s "
                            "qty_from_batch=%s new_remaining=%s qty_remaining_ref=%s",
                            batch.id, batch_unit, batch_qty, qty_from_batch,
                            batch.quantity_remaining, qty_remaining,
                        )

                db.flush()
                if inventory:
                    sync_inventory_totals(ing["ingredient_id"], db)

                if recipe_cost_per_unit is not None and recipe_cost_per_unit > 0:
                    ingredient_cost = recipe_cost_per_unit * qty_needed_original
                else:
                    first_batch_unit_cost = (
                        Decimal(str(batches[0].unit_cost)) if batches and batches[0].unit_cost else Decimal(0)
                    )
                    first_batch_unit = normalize_unit(batches[0].unit if batches[0].unit else ing["unit"])
                    qty_for_cost     = _safe_convert(qty_needed_original, dish_ing_unit, first_batch_unit)
                    ingredient_cost  = first_batch_unit_cost * qty_for_cost
                    logger.warning(
                        "[EDIT WASTAGE] recipe_cost_per_unit missing for ingredient id=%s name=%s. "
                        "Fallback cost: %s * %s = %s",
                        ing["ingredient_id"], ing["ingredient_name"],
                        first_batch_unit_cost, qty_for_cost, ingredient_cost,
                    )

                total_dish_cost += ingredient_cost
                breakdown_data.append({
                    "ingredient_id":      ing["ingredient_id"],
                    "ingredient_name":    ing["ingredient_name"],
                    "qty_deducted":       qty_needed_original,
                    "unit":               dish_ing_unit,
                    "ingredient_cost":    ingredient_cost,
                    "source":             ing["source"],
                    "semi_finished_id":   ing["semi_finished_id"],
                    "semi_finished_name": ing["semi_finished_name"],
                    "semi_finished_qty":  ing.get("semi_finished_qty"),
                    "semi_finished_unit": ing.get("semi_finished_unit"),
                })

            total_dish_cost_rounded = total_dish_cost.quantize(_COST_DP)

            wastage.dish_id         = new_dish_id
            wastage.quantity_wasted = float(quantity_wasted_int)
            wastage.unit_cost       = float(
                (total_dish_cost_rounded / quantity_wasted_int).quantize(_COST_DP)
            ) if quantity_wasted_int else 0
            wastage.cost_value = float(total_dish_cost_rounded)
            if wastage_date is not None:
                wastage.wastage_date = wastage_date_val

            db.add(wastage)
            db.flush()

            for bd in breakdown_data:
                qty_dec      = bd["qty_deducted"]    if isinstance(bd["qty_deducted"],    Decimal) else Decimal(str(bd["qty_deducted"]))
                cost_dec     = bd["ingredient_cost"] if isinstance(bd["ingredient_cost"], Decimal) else Decimal(str(bd["ingredient_cost"]))
                cost_rounded = cost_dec.quantize(_COST_DP)
                db.add(Wastage(
                    tenant_id                = tenant_id,
                    wastage_type             = WastageType.INVENTORY,
                    inventory_item_id        = bd["ingredient_id"],
                    quantity_wasted          = float(qty_dec),
                    unit                     = bd["unit"],
                    unit_cost                = float((cost_rounded / qty_dec).quantize(_COST_DP)) if qty_dec > 0 else 0,
                    cost_value               = float(cost_rounded),
                    wastage_reason           = reason_enum,
                    wastage_date             = wastage_date_val,
                    recorded_by_user_id      = user_id,
                    is_breakdown             = True,
                    parent_wastage_id        = wastage.id,
                    semi_finished_product_id = bd.get("semi_finished_id"),
                    semi_finished_qty        = bd.get("semi_finished_qty"),
                    semi_finished_unit_used  = bd.get("semi_finished_unit"),
                ))

            db.commit()
            db.refresh(wastage)
            logger.info(
                "[EDIT WASTAGE] Dish DONE wastage_id=%s total_dish_cost=%s",
                wastage_id, total_dish_cost_rounded,
            )
            return {
                "wastage_id":      str(wastage.id),
                "dish_name":       dish_name,
                "quantity_wasted": quantity_wasted_int,
                "total_cost":      float(total_dish_cost_rounded),
                "wastage_reason":  reason_enum.value,
                "wastage_date":    wastage.wastage_date,
                "photo_url":       wastage.photo_url,
            }

        # ════════════════════════════════════════════════════════════════════════
        # 6c. SEMI_FINISHED RE-DEDUCTION
        # ════════════════════════════════════════════════════════════════════════
        elif wastage_type == WastageType.SEMI_FINISHED:
            if not new_sfp_id:
                raise ValueError("semi_finished_product_id is required for semi-finished wastage")

            sfp = (
                db.query(SemiFinishedProduct)
                .filter(
                    SemiFinishedProduct.id        == new_sfp_id,
                    SemiFinishedProduct.tenant_id == tenant_id,
                    SemiFinishedProduct.is_active == True,
                )
                .first()
            )
            sfp_name = sfp.name if sfp else f"SFP#{new_sfp_id}"

            sfp_unit          = normalize_unit(sfp.unit if sfp else "")
            wastage_unit_norm = normalize_unit(new_unit) if new_unit else sfp_unit

            qty_in_sfp_unit = Decimal(str(new_qty))
            try:
                if wastage_unit_norm != sfp_unit and are_units_compatible(wastage_unit_norm, sfp_unit):
                    qty_in_sfp_unit = Decimal(str(
                        convert_to_base_unit(float(new_qty), wastage_unit_norm, sfp_unit)
                    ))
            except Exception:
                pass

            # ── Resolve SFP → flat raw ingredients (fully recursive) ─────────────
            def _resolve_sfp_to_raw(
                semi_id: int,
                qty_needed: Decimal,
                qty_unit: str,
                visited: set = None,
            ) -> list:
                if visited is None:
                    visited = set()
                if semi_id in visited:
                    return []
                visited = visited | {semi_id}

                semi = db.query(SemiFinishedProduct).filter(
                    SemiFinishedProduct.id        == semi_id,
                    SemiFinishedProduct.tenant_id == tenant_id,
                    SemiFinishedProduct.is_active == True,
                ).first()
                if not semi:
                    return []

                sfp_unit_norm_inner = normalize_unit(semi.unit)
                qty_unit_norm       = normalize_unit(qty_unit)
                qty_needed_converted = qty_needed
                try:
                    if qty_unit_norm != sfp_unit_norm_inner and are_units_compatible(qty_unit_norm, sfp_unit_norm_inner):
                        qty_needed_converted = Decimal(str(
                            convert_to_base_unit(float(qty_needed), qty_unit_norm, sfp_unit_norm_inner)
                        ))
                except Exception:
                    pass

                scale = (
                    qty_needed_converted / Decimal(str(semi.yield_quantity))
                    if semi.yield_quantity else Decimal("1")
                )

                sub_ingredients = db.query(SemiFinishedIngredient).filter(
                    SemiFinishedIngredient.semi_finished_id == semi_id,
                    SemiFinishedIngredient.tenant_id        == tenant_id,
                ).all()

                result = []
                for sub in sub_ingredients:
                    if getattr(sub, "is_semi_finished", False) and sub.ingredient_id:
                        nested_qty  = Decimal(str(sub.quantity_required)) * scale
                        nested_sfp  = db.query(SemiFinishedProduct).filter(
                            SemiFinishedProduct.id        == sub.ingredient_id,
                            SemiFinishedProduct.tenant_id == tenant_id,
                            SemiFinishedProduct.is_active == True,
                        ).first()
                        sub_unit    = normalize_unit(sub.unit)
                        nested_unit = normalize_unit(nested_sfp.unit) if nested_sfp else sub_unit
                        if nested_sfp:
                            try:
                                if sub_unit != nested_unit and are_units_compatible(sub_unit, nested_unit):
                                    nested_qty = Decimal(str(
                                        convert_to_base_unit(float(nested_qty), sub_unit, nested_unit)
                                    ))
                            except Exception:
                                pass
                        result.extend(_resolve_sfp_to_raw(
                            semi_id    = sub.ingredient_id,
                            qty_needed = nested_qty,
                            qty_unit   = nested_unit,
                            visited    = visited,
                        ))
                    elif sub.ingredient_id:
                        result.append({
                            "ingredient_id":     sub.ingredient_id,
                            "ingredient_name":   sub.ingredient_name,
                            "qty_needed":        Decimal(str(sub.quantity_required)) * scale,
                            "unit":              sub.unit,
                            "fixed_cost_amount": sub.fixed_cost_amount,
                        })
                return result

            def _safe_unit_sfp(u) -> str:
                if u is None:
                    return ""
                return normalize_unit(u.value if hasattr(u, "value") else str(u))

            def _get_batches_sfp(ingredient_id: int) -> list:
                result = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == ingredient_id,
                        InventoryBatch.is_active         == True,
                        InventoryBatch.quantity_remaining > 0,
                        func.date(InventoryBatch.date_added) <= wastage_calendar_date,
                        or_(
                            InventoryBatch.expiry_date == None,
                            InventoryBatch.expiry_date >= wastage_calendar_date,
                        ),
                    )
                    .order_by(InventoryBatch.created_at.desc())
                    .all()
                )
                if result:
                    return result
                result = (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == ingredient_id,
                        InventoryBatch.is_active         == True,
                        InventoryBatch.quantity_remaining > 0,
                        func.date(InventoryBatch.date_added) > wastage_calendar_date,
                        or_(
                            InventoryBatch.expiry_date == None,
                            InventoryBatch.expiry_date >= wastage_calendar_date,
                        ),
                    )
                    .order_by(InventoryBatch.created_at.asc())
                    .all()
                )
                if result:
                    return result
                return (
                    db.query(InventoryBatch)
                    .filter(
                        InventoryBatch.tenant_id         == tenant_id,
                        InventoryBatch.inventory_item_id == ingredient_id,
                        InventoryBatch.is_active         == True,
                        InventoryBatch.quantity_remaining > 0,
                    )
                    .order_by(InventoryBatch.created_at.desc())
                    .all()
                )

            ingredients_flat = _resolve_sfp_to_raw(new_sfp_id, qty_in_sfp_unit, sfp_unit)

            PIECE_UNITS_SFP  = {"pcs", "piece", "pieces"}
            PACKET_UNITS_SFP = {"packet", "packets", "pkt"}

            # ── Aggregate for validation ──────────────────────────────────────────
            aggregated_sfp: dict = defaultdict(lambda: {
                "total_qty_needed":  Decimal(0),
                "unit":              None,
                "ingredient_name":   None,
                "fixed_cost_amount": None,
            })
            for ing in ingredients_flat:
                k = ing["ingredient_id"]
                aggregated_sfp[k]["total_qty_needed"] += ing["qty_needed"]
                aggregated_sfp[k]["unit"]              = ing["unit"]
                aggregated_sfp[k]["ingredient_name"]   = ing["ingredient_name"]
                if ing.get("fixed_cost_amount") is not None:
                    aggregated_sfp[k]["fixed_cost_amount"] = ing["fixed_cost_amount"]

            # ── PRE-VALIDATE stock ────────────────────────────────────────────────
            validation_errors_sfp = []
            for ing_id, agg in aggregated_sfp.items():
                if agg["fixed_cost_amount"] is not None:
                    continue
                batches = _get_batches_sfp(ing_id)
                if not batches:
                    validation_errors_sfp.append(
                        f"No stock available for '{agg['ingredient_name']}' on or before {wastage_calendar_date}."
                    )
                    continue

                ref_unit        = _safe_unit_sfp(batches[0].unit)
                ing_unit        = normalize_unit(agg["unit"])
                qty_needed_orig = agg["total_qty_needed"]

                if ing_unit in PIECE_UNITS_SFP and ref_unit in PACKET_UNITS_SFP:
                    total_avail_pcs = Decimal(0)
                    for b in batches:
                        b_pieces = Decimal(str(b.pieces)) if b.pieces else Decimal("1")
                        total_avail_pcs += Decimal(str(b.quantity_remaining)) * b_pieces
                    if qty_needed_orig > total_avail_pcs:
                        validation_errors_sfp.append(
                            f"Insufficient stock for '{agg['ingredient_name']}'. "
                            f"Requested: {round(float(qty_needed_orig), 4)} {ing_unit}, "
                            f"Available: {round(float(total_avail_pcs), 4)} {ing_unit}."
                        )
                    continue

                qty_check = qty_needed_orig
                try:
                    if ing_unit != ref_unit and are_units_compatible(ing_unit, ref_unit):
                        qty_check = Decimal(str(convert_to_base_unit(float(qty_check), ing_unit, ref_unit)))
                except Exception:
                    pass

                total_avail = Decimal(0)
                for b in batches:
                    b_unit = _safe_unit_sfp(b.unit)
                    b_qty  = Decimal(str(b.quantity_remaining))
                    try:
                        if b_unit != ref_unit and are_units_compatible(b_unit, ref_unit):
                            b_qty = Decimal(str(convert_to_base_unit(float(b_qty), b_unit, ref_unit)))
                    except Exception:
                        pass
                    total_avail += b_qty

                if qty_check > total_avail:
                    try:
                        available_in_ing_unit = (
                            float(convert_to_base_unit(float(total_avail), ref_unit, ing_unit))
                            if ing_unit != ref_unit and are_units_compatible(ref_unit, ing_unit)
                            else float(total_avail)
                        )
                    except Exception:
                        available_in_ing_unit = float(total_avail)
                    validation_errors_sfp.append(
                        f"Insufficient stock for '{agg['ingredient_name']}'. "
                        f"Requested: {round(float(qty_needed_orig), 4)} {agg['unit']}, "
                        f"Available: {round(available_in_ing_unit, 4)} {agg['unit']}."
                    )

            if validation_errors_sfp:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"errors": validation_errors_sfp},
                )

            # ── Compute SFP cost ──────────────────────────────────────────────────
            _COST_DP         = Decimal("0.01")
            sfp_unit_cost    = Decimal(str(sfp.unit_cost or 0)) if sfp else Decimal("0")
            total_sfp_cost   = (sfp_unit_cost * qty_in_sfp_unit).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            total_fixed_cost_sfp = Decimal("0")
            breakdown_data_sfp   = []

            for ing in ingredients_flat:
                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.id        == ing["ingredient_id"],
                        Inventory.tenant_id == tenant_id,
                        Inventory.is_active == True,
                    )
                    .first()
                )
                batches = _get_batches_sfp(ing["ingredient_id"]) if inventory else []

                if not batches:
                    breakdown_data_sfp.append({
                        "ingredient_id":   ing["ingredient_id"],
                        "ingredient_name": ing["ingredient_name"],
                        "qty_deducted":    ing["qty_needed"],
                        "unit":            normalize_unit(ing["unit"]),
                        "ingredient_cost": Decimal(0),
                    })
                    continue

                reference_unit    = _safe_unit_sfp(batches[0].unit)
                fixed_cost_amount = ing.get("fixed_cost_amount")

                # ── Fixed-cost ingredient ─────────────────────────────────────────
                if fixed_cost_amount is not None:
                    batch_unit_cost    = Decimal(str(batches[0].unit_cost or 0))
                    qty_recipe         = Decimal(str(ing["qty_needed"]))
                    qty_to_deduct      = (
                        (Decimal(str(fixed_cost_amount)) / batch_unit_cost) * qty_recipe
                        if batch_unit_cost > 0 else Decimal("0")
                    )
                    qty_remaining      = qty_to_deduct
                    ingredient_cost    = Decimal("0")

                    for batch in batches:
                        if qty_remaining <= Decimal("0.0000001"):
                            break
                        batch_unit         = _safe_unit_sfp(batch.unit)
                        batch_qty          = Decimal(str(batch.quantity_remaining))
                        batch_qty_received = Decimal(str(batch.quantity_received)) if batch.quantity_received else Decimal("0")
                        batch_total_cost   = Decimal(str(batch.total_cost))        if batch.total_cost        else Decimal("0")
                        qty_from_batch     = min(batch_qty, qty_remaining)
                        cost = (
                            (qty_from_batch / batch_qty_received) * batch_total_cost
                            if batch_qty_received > 0 else Decimal("0")
                        )
                        batch.quantity_remaining = float(max(Decimal(0), batch_qty - qty_from_batch))
                        ingredient_cost         += cost
                        if Decimal(str(batch.quantity_remaining)) <= 0:
                            batch.is_active = False
                        db.add(batch)
                        db.add(InventoryTransaction(
                            tenant_id         = tenant_id,
                            inventory_item_id = ing["ingredient_id"],
                            batch_id          = batch.id,
                            transaction_type  = TransactionType.WASTAGE,
                            quantity          = float(qty_from_batch),
                            unit              = batch_unit,
                            unit_cost         = float(batch_unit_cost),
                            total_value       = float(cost),
                            transaction_date  = recorded_at,
                            reference_id      = ref_id,
                        ))
                        qty_remaining -= qty_from_batch

                    db.flush()
                    if inventory:
                        sync_inventory_totals(ing["ingredient_id"], db)

                    actual_cost           = Decimal(str(fixed_cost_amount)) * qty_recipe
                    total_fixed_cost_sfp += actual_cost
                    breakdown_data_sfp.append({
                        "ingredient_id":   ing["ingredient_id"],
                        "ingredient_name": ing["ingredient_name"],
                        "qty_deducted":    qty_to_deduct,
                        "unit":            reference_unit,
                        "ingredient_cost": actual_cost,
                    })
                    continue

                # ── pcs → packet FIFO ─────────────────────────────────────────────
                dish_ing_unit = normalize_unit(ing["unit"])
                qty_needed    = ing["qty_needed"]

                if dish_ing_unit in PIECE_UNITS_SFP and reference_unit in PACKET_UNITS_SFP:
                    qty_remaining_pcs = qty_needed
                    ingredient_cost   = Decimal(0)
                    for batch in batches:
                        if qty_remaining_pcs <= Decimal("0.0000001"):
                            break
                        b_pieces        = Decimal(str(batch.pieces)) if batch.pieces else Decimal("1")
                        batch_unit      = _safe_unit_sfp(batch.unit)
                        batch_qty_pkts  = Decimal(str(batch.quantity_remaining))
                        batch_qty_pcs   = batch_qty_pkts * b_pieces
                        batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)
                        cost_per_pcs    = batch_unit_cost / b_pieces if b_pieces else Decimal(0)
                        pcs_from_batch  = min(batch_qty_pcs, qty_remaining_pcs)
                        pkts_from_batch = pcs_from_batch / b_pieces
                        batch.quantity_remaining = float(max(Decimal(0), batch_qty_pkts - pkts_from_batch))
                        cost             = pcs_from_batch * cost_per_pcs
                        ingredient_cost += cost
                        if Decimal(str(batch.quantity_remaining)) <= 0:
                            batch.is_active = False
                        db.add(batch)
                        db.add(InventoryTransaction(
                            tenant_id         = tenant_id,
                            inventory_item_id = ing["ingredient_id"],
                            batch_id          = batch.id,
                            transaction_type  = TransactionType.WASTAGE,
                            quantity          = float(pkts_from_batch),
                            unit              = batch_unit,
                            unit_cost         = float(batch_unit_cost),
                            total_value       = float(cost),
                            transaction_date  = recorded_at,
                            reference_id      = ref_id,
                        ))
                        qty_remaining_pcs -= pcs_from_batch

                    db.flush()
                    if inventory:
                        sync_inventory_totals(ing["ingredient_id"], db)

                    breakdown_data_sfp.append({
                        "ingredient_id":   ing["ingredient_id"],
                        "ingredient_name": ing["ingredient_name"],
                        "qty_deducted":    qty_needed,
                        "unit":            dish_ing_unit,
                        "ingredient_cost": ingredient_cost,
                    })
                    continue

                # ── Generic FIFO ──────────────────────────────────────────────────
                try:
                    if dish_ing_unit != reference_unit and are_units_compatible(dish_ing_unit, reference_unit):
                        qty_needed = Decimal(str(
                            convert_to_base_unit(float(qty_needed), dish_ing_unit, reference_unit)
                        ))
                except Exception:
                    pass

                qty_remaining   = qty_needed
                ingredient_cost = Decimal(0)

                for batch in batches:
                    if qty_remaining <= Decimal("0.0000001"):
                        break
                    batch_unit      = _safe_unit_sfp(batch.unit)
                    batch_qty       = Decimal(str(batch.quantity_remaining))
                    batch_unit_cost = Decimal(str(batch.unit_cost)) if batch.unit_cost else Decimal(0)
                    try:
                        qty_in_batch_unit = qty_remaining
                        if batch_unit != reference_unit and are_units_compatible(reference_unit, batch_unit):
                            qty_in_batch_unit = Decimal(str(
                                convert_to_base_unit(float(qty_remaining), reference_unit, batch_unit)
                            ))
                    except Exception:
                        qty_in_batch_unit = qty_remaining

                    qty_from_batch           = min(batch_qty, qty_in_batch_unit)
                    batch.quantity_remaining = float(max(Decimal(0), batch_qty - qty_from_batch))
                    cost                     = qty_from_batch * batch_unit_cost
                    ingredient_cost         += cost
                    if Decimal(str(batch.quantity_remaining)) <= 0:
                        batch.is_active = False
                    db.add(batch)
                    db.add(InventoryTransaction(
                        tenant_id         = tenant_id,
                        inventory_item_id = ing["ingredient_id"],
                        batch_id          = batch.id,
                        transaction_type  = TransactionType.WASTAGE,
                        quantity          = float(qty_from_batch),
                        unit              = batch_unit,
                        unit_cost         = float(batch_unit_cost),
                        total_value       = float(cost),
                        transaction_date  = recorded_at,
                        reference_id      = ref_id,
                    ))
                    try:
                        qty_deducted_ref = qty_from_batch
                        if batch_unit != reference_unit and are_units_compatible(batch_unit, reference_unit):
                            qty_deducted_ref = Decimal(str(
                                convert_to_base_unit(float(qty_from_batch), batch_unit, reference_unit)
                            ))
                    except Exception:
                        qty_deducted_ref = qty_from_batch
                    qty_remaining -= qty_deducted_ref

                db.flush()
                if inventory:
                    sync_inventory_totals(ing["ingredient_id"], db)

                breakdown_data_sfp.append({
                    "ingredient_id":   ing["ingredient_id"],
                    "ingredient_name": ing["ingredient_name"],
                    "qty_deducted":    qty_needed,
                    "unit":            reference_unit,
                    "ingredient_cost": ingredient_cost,
                })

            # ── Fold fixed costs, update wastage record ───────────────────────────
            total_sfp_cost = (total_sfp_cost + total_fixed_cost_sfp).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )

            wastage.semi_finished_product_id = new_sfp_id
            wastage.quantity_wasted          = float(new_qty)
            wastage.unit                     = wastage_unit_norm
            wastage.unit_cost                = float(sfp_unit_cost)
            wastage.cost_value               = float(total_sfp_cost)
            if wastage_date is not None:
                wastage.wastage_date = wastage_date_val

            db.add(wastage)
            db.flush()

            for bd in breakdown_data_sfp:
                qty_dec  = bd["qty_deducted"]    if isinstance(bd["qty_deducted"],    Decimal) else Decimal(str(bd["qty_deducted"]))
                cost_dec = bd["ingredient_cost"] if isinstance(bd["ingredient_cost"], Decimal) else Decimal(str(bd["ingredient_cost"]))
                db.add(Wastage(
                    tenant_id                = tenant_id,
                    wastage_type             = WastageType.INVENTORY,
                    inventory_item_id        = bd["ingredient_id"],
                    quantity_wasted          = float(qty_dec),
                    unit                     = bd["unit"],
                    unit_cost                = float(cost_dec / qty_dec) if qty_dec > 0 else 0,
                    cost_value               = float(cost_dec),
                    wastage_reason           = wastage.wastage_reason,
                    wastage_date             = wastage_date_val,
                    recorded_by_user_id      = user_id,
                    is_breakdown             = True,
                    parent_wastage_id        = wastage.id,
                    semi_finished_product_id = new_sfp_id,
                ))

            db.commit()
            db.refresh(wastage)
            logger.info(
                "[EDIT WASTAGE] SFP DONE wastage_id=%s total_cost=%s",
                wastage_id, total_sfp_cost,
            )
            return {
                "wastage_id":      str(wastage.id),
                "sfp_name":        sfp_name,
                "quantity_wasted": float(new_qty),
                "unit":            wastage_unit_norm,
                "total_cost":      float(total_sfp_cost),
                "wastage_reason":  wastage.wastage_reason.value,
                "wastage_date":    wastage.wastage_date,
                "photo_url":       wastage.photo_url,
            }

        # ════════════════════════════════════════════════════════════════════════
        # 6d. COMBO RE-DEDUCTION
        # ════════════════════════════════════════════════════════════════════════
        elif wastage_type == WastageType.COMBO:
            if not new_combo_id:
                raise ValueError("combo_id is required for combo wastage")

            combo = db.query(Combo).filter(
                Combo.id        == new_combo_id,
                Combo.tenant_id == tenant_id,
            ).first()
            combo_name = combo.name if combo else f"Combo#{new_combo_id}"

            # FIX 1: Keep quantity as Decimal for fractional-safe math.
            # quantity_wasted_int is only used for display / cost scaling, NOT
            # for the per-item qty passed to child record calls.
            quantity_wasted_decimal = Decimal(str(new_qty))
            quantity_wasted_int     = int(new_qty)   # display / parent record only

            combo_items = db.query(ComboItem).filter(
                ComboItem.combo_id  == new_combo_id,
                ComboItem.tenant_id == tenant_id,
            ).all() if combo else []

            if not combo_items:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Combo {new_combo_id} has no items or does not exist.",
                )

            # ── Recompute cost snapshot ───────────────────────────────────────────
            combo_unit_cost = Decimal("0")
            for ci in combo_items:
                try:
                    snapshot  = _resolve_item(
                        db, tenant_id,
                        ci.dish_id, ci.semi_finished_id, ci.ingredient_id,
                        user_unit=ci.unit or "",
                    )
                    line_cost = Decimal(str(snapshot["cost_per_unit"])) * Decimal(str(ci.quantity or 1))
                except Exception:
                    line_cost = Decimal(str(ci.cost_per_unit or 0)) * Decimal(str(ci.quantity or 1))
                combo_unit_cost += line_cost

            total_combo_cost = (combo_unit_cost * quantity_wasted_decimal).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            )

            # ── Deduct each combo item by delegating to existing record methods ───
            breakdown = []

            for ci in combo_items:
                # FIX 1 (continued): use Decimal for qty_for_item so fractional
                # quantities (e.g. 0.5 kg) are not silently truncated to zero.
                qty_for_item = Decimal(str(ci.quantity or 1)) * quantity_wasted_decimal

                # ── Dish item ─────────────────────────────────────────────────────
                if ci.dish_id:
                    # FIX 3: guard against zero after int() cast
                    qty_dish_int = int(qty_for_item)
                    if qty_dish_int <= 0:
                        logger.warning(
                            "[EDIT WASTAGE] Skipping combo dish_id=%s — computed qty=%s rounds to 0",
                            ci.dish_id, qty_for_item,
                        )
                        continue

                    try:
                        result = WastageService.record_dish_wastage(
                            db              = db,
                            tenant_id       = tenant_id,
                            dish_id         = ci.dish_id,
                            quantity_wasted = qty_dish_int,
                            wastage_reason  = wastage.wastage_reason.value,
                            user_id         = user_id,
                            wastage_date    = wastage_date_val,
                        )
                        child = db.query(Wastage).filter(Wastage.id == result["wastage_id"]).first()
                        if child:
                            child.parent_wastage_id = wastage_id
                            child.is_breakdown      = True
                            db.add(child)
                        breakdown.append({
                            "type": "dish",
                            "id":   ci.dish_id,
                            "name": result.get("dish_name"),
                            "qty":  float(qty_for_item),
                            "cost": result.get("total_cost", 0),
                        })
                    except HTTPException as e:
                        raise HTTPException(
                            status_code=e.status_code,
                            detail=f"Combo item (dish_id={ci.dish_id}): {e.detail}",
                        )

                # ── Semi-finished item ────────────────────────────────────────────
                elif ci.semi_finished_id:
                    # FIX 3: guard against zero qty
                    if qty_for_item <= Decimal("0.0000001"):
                        logger.warning(
                            "[EDIT WASTAGE] Skipping combo semi_finished_id=%s — computed qty=%s <= 0",
                            ci.semi_finished_id, qty_for_item,
                        )
                        continue

                    _sfp = db.query(SemiFinishedProduct).filter(
                        SemiFinishedProduct.id        == ci.semi_finished_id,
                        SemiFinishedProduct.tenant_id == tenant_id,
                        SemiFinishedProduct.is_active == True,
                    ).first()
                    _sfp_unit = (
                        (_sfp.unit.value if hasattr(_sfp.unit, "value") else str(_sfp.unit))
                        if _sfp and _sfp.unit else "gm"
                    )
                    _wastage_unit = ci.unit if ci.unit else _sfp_unit

                    try:
                        result = WastageService.record_semi_finished_wastage(
                            db               = db,
                            tenant_id        = tenant_id,
                            semi_finished_id = ci.semi_finished_id,
                            quantity_wasted  = float(qty_for_item),
                            wastage_unit     = _wastage_unit,
                            wastage_reason   = wastage.wastage_reason.value,
                            user_id          = user_id,
                            wastage_date     = wastage_date_val,
                        )
                        child = db.query(Wastage).filter(Wastage.id == result["wastage_id"]).first()
                        if child:
                            child.parent_wastage_id = wastage_id
                            child.is_breakdown      = True
                            db.add(child)
                        breakdown.append({
                            "type": "semi_finished",
                            "id":   ci.semi_finished_id,
                            "name": result.get("sfp_name"),
                            "qty":  float(qty_for_item),
                            "cost": result.get("total_cost", 0),
                        })
                    except HTTPException as e:
                        raise HTTPException(
                            status_code=e.status_code,
                            detail=f"Combo item (semi_finished_id={ci.semi_finished_id}): {e.detail}",
                        )

                # ── Raw inventory item ────────────────────────────────────────────
                elif ci.ingredient_id:
                    # FIX 2 + FIX 3: guard against zero BEFORE constructing the
                    # Pydantic schema — Pydantic validates quantity_wasted > 0.
                    if qty_for_item <= Decimal("0.0000001"):
                        logger.warning(
                            "[EDIT WASTAGE] Skipping combo ingredient_id=%s — computed qty=%s <= 0",
                            ci.ingredient_id, qty_for_item,
                        )
                        continue

                    if not ci.unit:
                        _inv_item = db.query(Inventory).filter(
                            Inventory.id        == ci.ingredient_id,
                            Inventory.tenant_id == tenant_id,
                        ).first()
                        _inv_unit = (
                            (_inv_item.unit.value if hasattr(_inv_item.unit, "value") else str(_inv_item.unit))
                            if _inv_item and _inv_item.unit else "gm"
                        )
                    else:
                        _inv_unit = ci.unit

                    data = RecordInventoryWastage(
                        inventory_item_id  = ci.ingredient_id,
                        inventory_batch_id = None,
                        quantity_wasted    = qty_for_item,   # Decimal, always > 0
                        unit               = _inv_unit,
                        wastage_reason     = wastage.wastage_reason,
                        wastage_date       = wastage_date_val,
                    )
                    try:
                        record = WastageService.record_inventory_wastage(
                            db        = db,
                            tenant_id = tenant_id,
                            data      = data,
                            user_id   = user_id,
                        )
                        record.parent_wastage_id = wastage_id
                        record.is_breakdown      = True
                        db.add(record)
                        breakdown.append({
                            "type": "inventory",
                            "id":   ci.ingredient_id,
                            "name": ci.item_name,
                            "qty":  float(qty_for_item),
                            "cost": float(record.cost_value or 0),
                        })
                    except HTTPException as e:
                        raise HTTPException(
                            status_code=e.status_code,
                            detail=f"Combo item (ingredient_id={ci.ingredient_id}): {e.detail}",
                        )

            # ── Update parent wastage record ──────────────────────────────────────
            wastage.combo_id        = new_combo_id
            wastage.quantity_wasted = float(quantity_wasted_decimal)
            wastage.unit_cost       = float(combo_unit_cost)
            wastage.cost_value      = float(total_combo_cost)
            if wastage_date is not None:
                wastage.wastage_date = wastage_date_val

            db.add(wastage)
            db.commit()

            logger.info(
                "[EDIT WASTAGE] Combo DONE wastage_id=%s total_cost=%s",
                wastage_id, total_combo_cost,
            )
            return {
                "wastage_id":      str(wastage_id),
                "combo_name":      combo_name,
                "quantity_wasted": float(quantity_wasted_decimal),
                "total_cost":      float(total_combo_cost),
                "wastage_reason":  wastage.wastage_reason.value,
                "wastage_date":    wastage_date_val,
                "photo_url":       wastage.photo_url,
                "breakdown":       breakdown,
            }

        else:
            raise ValueError(f"Unsupported wastage_type '{wastage_type}' for edit")
    
    @staticmethod
    def _format_wastage_response(wastage: Wastage) -> dict:
        return {
            "wastage_id":      str(wastage.id),
            "wastage_type":    wastage.wastage_type.value,
            "quantity_wasted": float(wastage.quantity_wasted),
            "unit":            wastage.unit,
            "cost_value":      float(wastage.cost_value or 0),
            "wastage_reason":  wastage.wastage_reason.value if wastage.wastage_reason else None,
            "notes":           wastage.notes,
            "photo_url":       wastage.photo_url,
            "wastage_date":    wastage.wastage_date,
        }