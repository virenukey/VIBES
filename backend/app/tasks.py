from decimal import Decimal

from sqlalchemy import or_

from app.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.inventory import InventoryBatch,Inventory, InventoryTransaction,ItemCategory, ItemPerishableNonPerishable, TransactionType
from sqlalchemy.orm import Session
from datetime import datetime,date, timedelta, timezone
import logging
from app.models.wastage_model import Wastage, WastageType, WastageReason
from app.models.dish import IngredientForPrePreparedIngredients, PrePreparedMaterialStock, PrePreparedMaterial
from app.utils.inventory_batch_helper import sync_inventory_totals

logger = logging.getLogger(__name__)


def calculate_days_until_expiry(expiry_date=None, shelf_life_in_days=None, date_added=None) -> int | None:
    today = datetime.utcnow().date()
    
    if expiry_date:
        expiry = expiry_date.date() if hasattr(expiry_date, "date") else expiry_date
        return (expiry - today).days
    
    if shelf_life_in_days is not None:
        # Fall back to date_added or today if date_added is missing
        base_date = date_added.date() if date_added and hasattr(date_added, "date") else today
        expiry = base_date + timedelta(days=shelf_life_in_days)
        return (expiry - today).days
    
    return None

def find_lifecycle_stage(
    days_until_expiry: int,
    fresh_threshold: int,
) -> str:
    if days_until_expiry < 0:
        return "EXPIRED"
    elif days_until_expiry <= fresh_threshold:
        return "NEAR_EXPIRY"
    else:
        return "FRESH" 
    
def update_batch_lifecycle(batch:InventoryBatch, item:Inventory, db:Session):
    if not batch.expiry_date and item.shelf_life_in_days is None:
        return
    
    days_until_expiry = calculate_days_until_expiry(
    expiry_date=batch.expiry_date,
    shelf_life_in_days=item.shelf_life_in_days,
    date_added=batch.date_added
    )

    if days_until_expiry is None:  
        return
    
    old_stage = batch.lifecycle_stage

    batch.lifecycle_stage = find_lifecycle_stage(
        days_until_expiry,
        item.fresh_threshold_days or 3,
    )

    if old_stage != batch.lifecycle_stage:
        logger.info(
            f"Batch {batch.id} lifecycle updated: {old_stage} -> {batch.lifecycle_stage}"
            f"(expires in {days_until_expiry} days)"
        )
        db.commit()

def update_inventory_lifecycle(item: Inventory, db: Session):
    # Must have at least one of these to calculate lifecycle
    if not item.expiry_date and item.shelf_life_in_days is None:
        return

    days_until_expiry = calculate_days_until_expiry(
        expiry_date=item.expiry_date,
        shelf_life_in_days=item.shelf_life_in_days,
        date_added=item.date_added
    )

    if days_until_expiry is None:
        return

    old_stage = item.lifecycle_stage

    item.lifecycle_stage = find_lifecycle_stage(
        days_until_expiry,
        item.fresh_threshold_days or 3
    )

    if old_stage != item.lifecycle_stage:
        logger.info(
            f"Inventory {item.id} lifecycle updated: "
            f"{old_stage} -> {item.lifecycle_stage} "
            f"(expires in {days_until_expiry} days)"
        )

@celery_app.task(name="app.tasks.update_all_batch_lifecycles")
def update_batch_lifecycles_status():
    db = SessionLocal()

    try:
        batches = (
            db.query(InventoryBatch)
            .join(Inventory)
            .join(ItemCategory, Inventory.item_category_id == ItemCategory.id)
            .filter(
                InventoryBatch.expiry_date.isnot(None),
                ItemCategory.category_type == ItemPerishableNonPerishable.PERISHABLE
            )
            .all()
)


        updated_count = 0

        for batch in batches:
            previous_stage = batch.lifecycle_stage
            update_batch_lifecycle(batch, batch.item, db)

            if previous_stage != batch.lifecycle_stage:
                updated_count += 1

        db.commit()

        logger.info(
            f"Batch lifecycle update completed. "
            f"Updated {updated_count}/{len(batches)} batches."
        )

        return {
            "status": "success",
            "total_batches": len(batches),
            "updated_batches": updated_count
        }

    except Exception as e:
        db.rollback()
        logger.exception("Error updating batch lifecycles")
        raise
    finally:
        db.close()

@celery_app.task(name="app.tasks.update_all_inventory_lifecycles")
def update_inventory_lifecycle_status():
    db = SessionLocal()

    try:
        items = (
            db.query(Inventory)
            .join(ItemCategory)
            .filter(
                # Include items with either expiry_date OR shelf_life_in_days
                or_(
                    Inventory.expiry_date.isnot(None),
                    Inventory.shelf_life_in_days.isnot(None)
                ),
                Inventory.is_active == True,
                # ItemCategory.category_type == ItemPerishableNonPerishable.PERISHABLE
            )
            .all()
        )

        updated_count = 0

        for item in items:
            previous_stage = item.lifecycle_stage
            update_inventory_lifecycle(item, db)

            if previous_stage != item.lifecycle_stage:
                updated_count += 1

        db.commit()

        logger.info(
            f"Inventory lifecycle update completed. "
            f"Updated {updated_count}/{len(items)} items."
        )

        return {
            "status": "success",
            "total_items": len(items),
            "updated_items": updated_count
        }

    except Exception:
        db.rollback()
        logger.exception("Error updating inventory lifecycles")
        raise
    finally:
        db.close()

@celery_app.task(name="app.tasks.auto_saved_expired_semi_finished")
def auto_saved_expired_semi_finished():
    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)
        created_count = 0

        # Find expired semi-finished batches with remaining quantity
        expired_batches = db.query(PrePreparedMaterialStock).filter(
            PrePreparedMaterialStock.expiry_date < now,
            PrePreparedMaterialStock.quantity_remaining > 0,
        ).all()

        for batch in expired_batches:

            # Skip if already wastaged
            existing = db.query(Wastage).filter(
                Wastage.semi_finished_batch_id == batch.id,
                Wastage.wastage_reason == WastageReason.EXPIRY,
                Wastage.is_breakdown == False,
            ).first()
            if existing:
                continue

            product = db.query(PrePreparedMaterial).filter(
                PrePreparedMaterial.id == batch.product_id
            ).first()
            if not product:
                continue

            qty_remaining = Decimal(str(batch.quantity_remaining))
            qty_produced = Decimal(str(batch.quantity_produced)) if batch.quantity_produced else Decimal(1)

            unit_cost = (
                Decimal(str(batch.total_cost)) / qty_produced
                if batch.quantity_produced else Decimal(0)
            )

            # ── Parent wastage record (semi-finished level) ──────────
            parent_wastage = Wastage(
                tenant_id=batch.tenant_id,
                wastage_type=WastageType.SEMI_FINISHED,
                semi_finished_product_id=batch.product_id,
                semi_finished_batch_id=batch.id,
                quantity_wasted=float(qty_remaining),
                unit=batch.unit,
                unit_cost=float(unit_cost),
                cost_value=float(qty_remaining * unit_cost),
                wastage_reason=WastageReason.EXPIRY,
                wastage_date=now,
                is_breakdown=False,
                notes=(
                    f"Auto-flagged: {product.name} batch {batch.batch_number} "
                    f"expired (shelf life: {product.shelf_life_hours}hrs)"
                ),
            )
            db.add(parent_wastage)
            db.flush()  # ← get parent_wastage.id before adding children

            # ── Ingredient breakdown records ─────────────────────────
            # Get the recipe ingredients for this semi-finished product
            ingredients = db.query(IngredientForPrePreparedIngredients).filter(
                IngredientForPrePreparedIngredients.semi_finished_product_id == product.id
            ).all()

            # Total recipe yield (what 100% of ingredients produces)
            # e.g. Rice 3000gm + Urad Dal 1000gm + Fenugreek 10gm → 5000gm batter
            total_recipe_yield = Decimal(str(product.yield_quantity)) if product.yield_quantity else qty_produced

            # Proportion of batch remaining vs total produced
            # e.g. 490gm remaining out of 5000gm produced = 9.8% remaining
            remaining_ratio = qty_remaining / qty_produced

            for ing in ingredients:
                # How much of this ingredient is locked in the remaining batch
                # e.g. Rice: 3000gm × (490/5000) = 294gm wasted
                ing_qty_wasted = Decimal(str(ing.quantity_required)) * remaining_ratio
                ing_unit_cost = Decimal(str(ing.cost_per_unit or 0))
                ing_cost_value = ing_qty_wasted * ing_unit_cost

                child_wastage = Wastage(
                    tenant_id=batch.tenant_id,
                    wastage_type=WastageType.INVENTORY,
                    inventory_item_id=ing.ingredient_id if not getattr(ing, 'is_semi_finished', False) else None,
                    semi_finished_product_id=batch.product_id,
                    quantity_wasted=float(ing_qty_wasted),
                    unit=ing.unit,
                    unit_cost=float(ing_unit_cost),
                    cost_value=float(ing_cost_value),
                    wastage_reason=WastageReason.EXPIRY,
                    wastage_date=now,
                    is_breakdown=True,
                    parent_wastage_id=parent_wastage.id,  # ← links to parent
                    notes=(
                        f"Ingredient breakdown: {ing.ingredient_name} lost in "
                        f"expired {product.name} batch {batch.batch_number}"
                    ),
                )
                db.add(child_wastage)

            # Zero out the batch
            batch.quantity_remaining = 0
            created_count += 1

        db.commit()
        logger.info(f"Semi-finished auto-wastage: flagged {created_count} expired batches")
        return {"status": "success", "wastage_records_created": created_count}

    except Exception:
        db.rollback()
        logger.exception("Error in auto_saved_expired_semi_finished")
        raise
    finally:
        db.close()

# @celery_app.task(name="app.tasks.auto_saved_expired_wastage")
# def auto_saved_expired_wastage():
#     db = SessionLocal()

#     try:
#         today = date.today()

#         expired_batches = (
#             db.query(InventoryBatch)
#             .filter(
#                 InventoryBatch.expiry_date < today,
#                 InventoryBatch.quantity_remaining > 0,
#                 InventoryBatch.is_active == True,
#             )
#             .all()
#         )

#         created_count = 0

#         for batch in expired_batches:
#             # Skip if already has an expiry wastage record
#             existing = db.query(Wastage).filter(
#                 Wastage.inventory_batch_id == batch.id,
#                 Wastage.wastage_reason == WastageReason.EXPIRY.value,
#             ).first()

#             if existing:
#                 continue

#             item = db.query(Inventory).filter(
#                 Inventory.id == batch.inventory_item_id
#             ).with_for_update().first()

#             if not item:
#                 continue

#             unit_cost  = Decimal(str(batch.unit_cost or item.unit_cost or 0))
#             qty        = Decimal(str(batch.quantity_remaining))
#             cost_value = qty * unit_cost
#             recorded_at = datetime.now(timezone.utc)

#             # ── Create wastage record ──
#             wastage = Wastage(
#                 tenant_id=batch.tenant_id,
#                 wastage_type=WastageType.INVENTORY,
#                 inventory_item_id=batch.inventory_item_id,
#                 inventory_batch_id=batch.id,
#                 quantity_wasted=float(qty),
#                 unit=item.unit,
#                 unit_cost=float(unit_cost),
#                 cost_value=float(cost_value),
#                 wastage_reason=WastageReason.EXPIRY,
#                 wastage_date=recorded_at,
#                 notes=f"Auto-flagged: Batch {batch.batch_number} expired on {batch.expiry_date}",
#             )
#             db.add(wastage)
#             db.flush() 

#             # ── Zero out the batch ──
#             batch.quantity_remaining = 0
#             batch.is_active = False

#             inv_quantity         = Decimal(str(item.quantity         or 0))
#             inv_current_quantity = Decimal(str(item.current_quantity or 0))

#             # ── Deduct from item current_quantity ──
#             item.quantity = float(max(Decimal(0), inv_quantity         - qty))
#             item.current_quantity = float(max(Decimal(0), inv_current_quantity - qty))

#             db.add(item)

#             logger.info(
#                 f"Batch {batch.batch_number} | item={item.name} | "
#                 f"expired_qty={float(qty)} {item.unit} | "
#                 f"quantity: {float(inv_quantity)} → {item.quantity} | "
#                 f"current_quantity: {float(inv_current_quantity)} → {item.current_quantity}"
#             )

#             db.add(InventoryTransaction(
#                 tenant_id=batch.tenant_id,
#                 inventory_item_id=batch.inventory_item_id,
#                 batch_id=batch.id,
#                 transaction_type=TransactionType.WASTAGE,     
#                 quantity=float(qty),                         
#                 unit=batch.unit,                              
#                 unit_cost=float(unit_cost),
#                 total_value=float(cost_value),                  
#                 transaction_date=recorded_at,                   
#                 reference_id=f"wastage:{wastage.id}",           
#             ))

#             sync_inventory_totals(batch.inventory_item_id, db)
#             created_count += 1

#         db.commit()

#         logger.info(
#             f"Auto-wastage completed. "
#             f"Flagged {created_count}/{len(expired_batches)} expired batches."
#         )

#         return {
#             "status": "success",
#             "total_expired_batches": len(expired_batches),
#             "wastage_records_created": created_count,
#         }

#     except Exception as e:
#         db.rollback()
#         logger.exception("Error in auto_flag_expired_wastage")
#         raise
#     finally:
#         db.close()   