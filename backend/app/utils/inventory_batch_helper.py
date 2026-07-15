from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import and_, or_
from app.models.dish import DishIngredient
from app.models.inventory import Inventory, InventoryBatch, PerishableLifecycle
from sqlalchemy.orm import Session

from app.utils.common_unit_converter import convert_quantity_unit


def calculate_days_until_expiry(expiry_date: date) -> int:
    """Calculate days until expiry (negative if expired)"""
    today = date.today()
    delta = expiry_date - today
    return delta.days

def calculate_hours_until_expiry(expiry_date: date) -> int:
    """Calculate hours until expiry (negative if expired)"""
    today = datetime.now()
    expiry_datetime = datetime.combine(expiry_date, datetime.min.time())
    delta = expiry_datetime - today
    return int(delta.total_seconds() / 3600)

def determine_lifecycle_stage(
    days_until_expiry: int,
    fresh_threshold: int = 3,
    near_expiry_threshold: int = 1
) -> PerishableLifecycle:
    """
    Determine lifecycle stage based on days until expiry
    
    Fresh: More than fresh_threshold days
    Near Expiry: Between near_expiry_threshold and fresh_threshold days
    Expired: Past expiry date (negative days)
    """
    if days_until_expiry < 0:
        return PerishableLifecycle.EXPIRED
    elif days_until_expiry <= near_expiry_threshold:
        return PerishableLifecycle.NEAR_EXPIRY
    elif days_until_expiry <= fresh_threshold:
        return PerishableLifecycle.NEAR_EXPIRY
    else:
        return PerishableLifecycle.FRESH

def update_batch_lifecycle(batch: InventoryBatch, item: Inventory):
    """Update batch lifecycle stage based on current date"""
    if not batch.expiry_date:
        return
    
    days_until_expiry = calculate_days_until_expiry(batch.expiry_date)
    
    batch.lifecycle_stage = determine_lifecycle_stage(
        days_until_expiry,
        item.fresh_threshold_days or 3,
        item.near_expiry_threshold_days or 1
    )

def generate_batch_number_sequential(
    item_id: int,
    db: Session,
    prefix: str = "BATCH"   
) -> str:
    # Get highest batch number for this item
    last_batch = db.query(InventoryBatch.batch_number)\
        .filter(InventoryBatch.inventory_item_id == item_id)\
        .filter(InventoryBatch.batch_number.like(f"{prefix}-%"))\
        .order_by(InventoryBatch.batch_number.desc())\
        .first()
    
    if last_batch:
        try:
            # Extract number from "BATCH-000001"
            last_num = int(last_batch[0].split("-")[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    
    batch_number = f"{prefix}-{str(new_num).zfill(6)}"
    
    return batch_number   

def sync_inventory_totals(item_id: int, db: Session) -> None:
    today = date.today()

    # Deactivate exhausted batches
    exhausted_batches = db.query(InventoryBatch).filter(
        InventoryBatch.inventory_item_id == item_id,
        InventoryBatch.is_active == True,
        InventoryBatch.quantity_remaining <= 0,
    ).all()

    for batch in exhausted_batches:
        batch.is_active = False

    batches = db.query(InventoryBatch).filter(
        InventoryBatch.inventory_item_id == item_id,
        InventoryBatch.is_active == True,
        InventoryBatch.quantity_remaining > 0,
        or_(
            InventoryBatch.expiry_date == None,
            InventoryBatch.expiry_date >= today,
        )
    ).all()

    item = db.query(Inventory).filter(Inventory.id == item_id).first()
    if not item:
        return

    item_unit = item.unit

    total_qty = Decimal("0")
    total_cost = Decimal("0")

    for b in batches:
        qty = Decimal(str(b.quantity_remaining))
        qty_received = Decimal(str(b.quantity_received)) if b.quantity_received else qty
        batch_unit = b.unit or item_unit

        try:
            converted_qty = convert_quantity_unit(qty, batch_unit, item_unit)
        except ValueError:
            converted_qty = qty

        total_qty += converted_qty

        #  FIX: Use proportional cost from total_cost, never multiply unit_cost * qty
        batch_total_cost = Decimal(str(b.total_cost)) if b.total_cost else Decimal("0")
        if qty_received > 0:
            # proportional remaining cost = (qty_remaining / qty_received) * total_cost
            remaining_cost = (qty / qty_received) * batch_total_cost  #  exact
        else:
            remaining_cost = Decimal("0")

        total_cost += remaining_cost

    avg_price = total_cost / total_qty if total_qty > 0 else Decimal("0")

    #  Round only at the final display/storage step
    item.current_quantity = float(total_qty)
    item.total_cost = float(total_cost.quantize(Decimal("0.01")))   #  exact ₹200.00
    item.price_per_unit = float(avg_price)
    item.unit_cost = float(avg_price.quantize(Decimal("0.01")))     #  round only here
    item.quantity = float(total_qty)

    dish_ingredients = db.query(DishIngredient).filter(
        DishIngredient.ingredient_id == item_id,
        DishIngredient.tenant_id == item.tenant_id,
    ).all()

    for di in dish_ingredients:
        di.cost_per_unit = float(avg_price)

    if dish_ingredients:
        db.flush()

    sync_dish_ingredient_costs(item_id, db, item.tenant_id)    

def _get_valid_batches(db: Session, tenant_id: int, inventory_item_id: int):
    """
    Get active, non-expired batches with remaining stock.
    Sorted FEFO first (earliest expiry), then FIFO (oldest created).
    """
    today = date.today()
    return (
        db.query(InventoryBatch)
        .filter(
            and_(
                InventoryBatch.tenant_id == tenant_id,
                InventoryBatch.inventory_item_id == inventory_item_id,
                InventoryBatch.is_active == True,
                InventoryBatch.quantity_remaining > 0,
                or_(
                    InventoryBatch.expiry_date == None,      # no expiry — always valid
                    InventoryBatch.expiry_date >= today,     # not yet expired
                ),
            )
        )
        .order_by(
            InventoryBatch.expiry_date.asc().nullslast(),
            InventoryBatch.created_at.asc(),
        )
        .all()
    )

def sync_dish_ingredient_costs(ingredient_id: int, db: Session, tenant_id: str) -> None:
    """
    Jab bhi kisi ingredient ka batch change ho —
    us ingredient wale sare dish_ingredients ka cost_per_unit update karo
    """
    #  Sirf active, non-expired batches lo
    active_batches = db.query(InventoryBatch).filter(
        InventoryBatch.inventory_item_id == ingredient_id,
        InventoryBatch.is_active == True,
        InventoryBatch.quantity_remaining > 0,
        or_(
            InventoryBatch.expiry_date == None,
            InventoryBatch.expiry_date >= date.today()
        )
    ).all()

    # Is ingredient ka inventory item lo
    inv = db.query(Inventory).filter(Inventory.id == ingredient_id).first()
    if not inv:
        return

    item_unit = inv.unit.value if hasattr(inv.unit, "value") else str(inv.unit)

    # Is ingredient wale sare dish_ingredients lo
    dish_ingredients = db.query(DishIngredient).filter(
        DishIngredient.ingredient_id == ingredient_id,
        DishIngredient.tenant_id == tenant_id,
    ).all()

    for ing in dish_ingredients:
        fallback_cost = Decimal(str(ing.cost_per_unit or 0))

        #  Active batches se weighted avg calculate karo
        new_cost, _ = calc_weighted_avg_cost(
            ingredient_batches=active_batches,
            dish_unit=ing.unit,
            item_unit=item_unit,
            fallback_cost=fallback_cost,
        )

        ing.cost_per_unit = new_cost  #  DB update

    db.flush()

def calc_weighted_avg_cost(
    ingredient_batches: list,
    dish_unit: str,
    item_unit: str,
    fallback_cost: Decimal,
) -> tuple[Decimal, bool]:
    """
    Returns (cost_per_dish_unit, is_zero_cost).

    Logic:
    1. Sare active batches ka proportional remaining cost nikalo
    2. Sab quantities ko item master unit mein convert karo (fair comparison)
    3. Weighted avg cost per master unit nikalo
    4. Master unit se dish unit mein convert karo

    Rule: Kabhi bhi unit_cost * qty mat karo — hamesha total_cost se proportional nikalo
    """

    if not ingredient_batches:
        return fallback_cost, fallback_cost == Decimal("0")

    # ── Unit normalize ────────────────────────────────────────────────────────
    dish_unit_normalized = str(dish_unit).lower().strip() if dish_unit else ""
    item_unit_normalized = str(item_unit).lower().strip() if item_unit else ""

    PIECE_UNITS  = {"pcs", "piece", "pieces"}
    PACKET_UNITS = {"packet", "packets", "pkt"}

    #  Special case: dish needs pieces but inventory stored in packets
    # Never trust stored price_per_piece — always derive from total_cost + pieces_per_packet
    if dish_unit_normalized in PIECE_UNITS and item_unit_normalized in PACKET_UNITS:
        total_pieces = Decimal("0")
        total_cost   = Decimal("0")

        for b in ingredient_batches:
            b_qty_remaining   = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
            b_qty_received    = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
            b_total_cost      = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")
            pieces_per_packet = Decimal(str(b.pieces))             if b.pieces             else Decimal("1")

            # Proportional remaining cost for this batch
            if b_qty_received > Decimal("0"):
                remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
            else:
                remaining_cost = Decimal("0")

            # Total pieces remaining in this batch
            pieces_remaining = b_qty_remaining * pieces_per_packet

            total_pieces += pieces_remaining
            total_cost   += remaining_cost

        if total_pieces == Decimal("0"):
            return fallback_cost, True

        # cost per piece = total remaining cost / total remaining pieces
        cost_per_piece = total_cost / total_pieces
        is_zero        = cost_per_piece == Decimal("0")
        return cost_per_piece, is_zero

    # ── Original logic untouched below ───────────────────────────────────────

    total_qty_in_item_unit = Decimal("0")
    total_cost             = Decimal("0")

    for b in ingredient_batches:
        b_unit = b.unit.value if hasattr(b.unit, "value") else str(b.unit)

        b_qty_remaining = Decimal(str(b.quantity_remaining)) if b.quantity_remaining else Decimal("0")
        b_qty_received  = Decimal(str(b.quantity_received))  if b.quantity_received  else Decimal("0")
        b_total_cost    = Decimal(str(b.total_cost))         if b.total_cost         else Decimal("0")

        # Proportional remaining cost
        if b_qty_received > Decimal("0"):
            remaining_cost = (b_qty_remaining / b_qty_received) * b_total_cost
        else:
            remaining_cost = Decimal("0")

        # Convert qty to item master unit
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

    is_zero = cost_per_dish_unit == Decimal("0")
    return cost_per_dish_unit, is_zero


def _handle_post_upload_expiry(
    db: Session,
    tenant_id: str,
    affected_batch_ids: set,
) -> None:
    """
    After order deductions, check if any affected batch has expired
    with remaining stock → create WASTAGE record + transaction.
    """
    today = date.today()

    for batch_id in affected_batch_ids:
        batch = db.query(InventoryBatch).filter(
            InventoryBatch.id == batch_id,
            InventoryBatch.is_active == True,
            InventoryBatch.quantity_remaining > 0,
            InventoryBatch.expiry_date < today,  # already expired
        ).first()

        if not batch:
            continue

        unit_cost  = Decimal(str(batch.unit_cost or 0))
        qty        = Decimal(str(batch.quantity_remaining))
        cost_value = qty * unit_cost
        expiry_dt  = datetime.combine(
            batch.expiry_date,
            datetime.max.time()
        ).replace(tzinfo=timezone.utc)

        # Check if wastage already exists for this batch
        existing_wastage = db.query(Wastage).filter(
            Wastage.inventory_batch_id == batch.id,
            Wastage.wastage_reason == WastageReason.EXPIRY.value,
        ).first()

        if existing_wastage:
            continue

        # Create wastage record
        wastage_record = Wastage(
            tenant_id=tenant_id,
            wastage_type=WastageType.INVENTORY,
            inventory_item_id=batch.inventory_item_id,
            inventory_batch_id=batch.id,
            quantity_wasted=float(qty),
            unit=batch.unit,
            unit_cost=float(unit_cost),
            cost_value=float(cost_value),
            wastage_reason=WastageReason.EXPIRY,
            wastage_date=expiry_dt,
            notes=(
                f"Auto-expired after backdated order upload. "
                f"Batch {batch.batch_number} expired {batch.expiry_date}. "
                f"Remaining {float(qty)} {batch.unit} written off."
            ),
        )
        db.add(wastage_record)
        db.flush()

        # Create WASTAGE transaction
        db.add(InventoryTransaction(
            tenant_id=tenant_id,
            inventory_item_id=batch.inventory_item_id,
            batch_id=batch.id,
            transaction_type=TransactionType.WASTAGE,
            quantity=float(qty),
            unit_cost=float(unit_cost),
            unit=batch.unit,
            total_value=float(cost_value),
            transaction_date=expiry_dt,  # dated at expiry
            reference_id=f"wastage:{wastage_record.id}",
        ))

        # Zero out batch
        batch.quantity_remaining = 0
        batch.is_active = False

        sync_inventory_totals(batch.inventory_item_id, db)   