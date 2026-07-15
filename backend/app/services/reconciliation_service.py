"""
app/services/reconciliation_service.py
"""
from datetime import date, datetime
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from fastapi import HTTPException, status

from app.models.reconciliation import (
    ReconciliationPeriod,
    ReconciliationLineItem,
    PhysicalCount,
    ReconciliationAdjustment,
    ReconciliationStatus,
    VarianceStatus,
    CostingMethod,
    AdjustmentReason,
)
from app.models.inventory import (
    Inventory,
    InventoryBatch,
    InventoryTransaction,
    TransactionType,
    ItemCategory,
)
from app.models.wastage_model import Wastage, WastageType
from app.models.order import OrderPackaging, Order, OrderStatus
from app.models.dish import PreparationIngredientHistory, DishPreparationBatchLog
from app.schemas.reconciliation import (
    ReconciliationPeriodCreate,
    PhysicalCountEntry,
    AdjustmentCreate,
)


TWO_PLACES  = Decimal("0.01")
THREE_PLACES = Decimal("0.001")

def _weighted_average_cost(
    db: Session,
    inventory_item_id: int,
    tenant_id: int,
    as_of_date: date,
) -> Decimal:
    """
    Weighted-average unit cost = SUM(purchase_qty * unit_cost) / SUM(purchase_qty)
    for all PURCHASE transactions up to as_of_date.
    Falls back to inventory.unit_cost if no purchase transactions exist.
    """
    result = (
        db.query(
            func.sum(InventoryTransaction.quantity * InventoryTransaction.unit_cost).label("total_value"),
            func.sum(InventoryTransaction.quantity).label("total_qty"),
        )
        .filter(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.inventory_item_id == inventory_item_id,
            InventoryTransaction.transaction_type == TransactionType.PURCHASE,
            InventoryTransaction.transaction_date <= datetime.combine(as_of_date, datetime.max.time()),
        )
        .one()
    )
    if result.total_qty and result.total_qty > 0:
        return (Decimal(str(result.total_value)) / Decimal(str(result.total_qty))).quantize(TWO_PLACES)

    # Fallback: item-level unit cost
    item = db.query(Inventory).filter(Inventory.id == inventory_item_id).first()
    if item and item.unit_cost:
        return Decimal(str(item.unit_cost))
    return Decimal("0.00")


def _fifo_cost(
    db: Session,
    inventory_item_id: int,
    tenant_id: int,
    as_of_date: date,
) -> Decimal:
    """Oldest active batch with remaining stock (FIFO proxy)."""
    batch = (
        db.query(InventoryBatch)
        .filter(
            InventoryBatch.tenant_id == tenant_id,
            InventoryBatch.inventory_item_id == inventory_item_id,
            InventoryBatch.is_active == True,
            InventoryBatch.quantity_remaining > 0,
        )
        .order_by(InventoryBatch.created_at.asc())
        .first()
    )
    if batch and batch.unit_cost:
        return Decimal(str(batch.unit_cost))
    return _weighted_average_cost(db, inventory_item_id, tenant_id, as_of_date)


def _get_unit_cost(
    db: Session,
    inventory_item_id: int,
    tenant_id: int,
    as_of_date: date,
    method: CostingMethod,
) -> Decimal:
    if method == CostingMethod.FIFO:
        return _fifo_cost(db, inventory_item_id, tenant_id, as_of_date)
    return _weighted_average_cost(db, inventory_item_id, tenant_id, as_of_date)

def _get_purchases_qty(
    db: Session,
    tenant_id: int,
    inventory_item_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> Decimal:
    """
    Source: inventory_transactions WHERE transaction_type = PURCHASE
    Written by: POST /items/{item_id}/batches  (batch creation)
    """
    result = (
        db.query(func.coalesce(func.sum(InventoryTransaction.quantity), 0))
        .filter(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.inventory_item_id == inventory_item_id,
            InventoryTransaction.transaction_type == TransactionType.PURCHASE,
            InventoryTransaction.transaction_date >= start_dt,
            InventoryTransaction.transaction_date <= end_dt,
        )
        .scalar()
    )
    return Decimal(str(result or 0)).quantize(THREE_PLACES)


def _get_consumption_qty(
    db: Session,
    tenant_id: int,
    inventory_item_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> Decimal:
    """
    Source 1: preparation_ingredient_history
      - ingredient_id matches the inventory item
      - joined to dish_preparation_batch_logs for the date filter
      - captures all raw ingredient usage during dish preparation

    Source 2: order_packaging
      - inventory_item_id matches
      - order must not be CANCELLED
      - captures packaging materials consumed per order (plastic boxes, cartons, etc.)
    """
    # Source 1: preparation_ingredient_history
    prep_qty = (
        db.query(func.coalesce(func.sum(PreparationIngredientHistory.quantity_consumed), 0))
        .join(
            DishPreparationBatchLog,
            PreparationIngredientHistory.preparation_log_id == DishPreparationBatchLog.id,
        )
        .filter(
            PreparationIngredientHistory.ingredient_id == inventory_item_id,
            DishPreparationBatchLog.tenant_id == tenant_id,
            DishPreparationBatchLog.preparation_date >= start_dt,
            DishPreparationBatchLog.preparation_date <= end_dt,
        )
        .scalar()
    )

    # Source 2: order_packaging
    packaging_qty = (
        db.query(func.coalesce(func.sum(OrderPackaging.quantity), 0))
        .join(Order, OrderPackaging.order_id == Order.id)
        .filter(
            OrderPackaging.tenant_id == tenant_id,
            OrderPackaging.inventory_item_id == inventory_item_id,
            Order.order_date >= start_dt,
            Order.order_date <= end_dt,
            Order.status != OrderStatus.CANCELLED,
        )
        .scalar()
    )

    total = Decimal(str(prep_qty or 0)) + Decimal(str(packaging_qty or 0))
    return total.quantize(THREE_PLACES)


def _get_wastage_qty(
    db: Session,
    tenant_id: int,
    inventory_item_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> Decimal:
    """
    Source: wastage_management

    Case 1 — wastage_type = 'inventory'
      Direct raw material wastage (spillage, damage, expiry of raw stock).
      inventory_item_id is set directly on the row.

    Case 2 — wastage_type = 'dish' AND is_breakdown = True
      When a dish is wasted (unsold), the system creates child rows with
      is_breakdown = True for each ingredient in that dish.
      Those child rows carry inventory_item_id + quantity_wasted at ingredient level.

    Excluded:
      - wastage_type = 'dish' with is_breakdown = False  (parent dish row, no inventory_item_id)
      - wastage_type = 'semi_finished'  (tracked via pre_prepared_material_stock separately)
    """
    result = (
        db.query(func.coalesce(func.sum(Wastage.quantity_wasted), 0))
        .filter(
            Wastage.tenant_id == tenant_id,
            Wastage.inventory_item_id == inventory_item_id,
            Wastage.wastage_date >= start_dt,
            Wastage.wastage_date <= end_dt,
            (
                (Wastage.wastage_type == WastageType.INVENTORY) |
                (
                    (Wastage.wastage_type == WastageType.DISH) &
                    (Wastage.is_breakdown == True)
                )
            ),
        )
        .scalar()
    )
    return Decimal(str(result or 0)).quantize(THREE_PLACES)


def _get_adjustment_qty_signed(
    db: Session,
    tenant_id: int,
    inventory_item_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> Decimal:
    """
    Source: inventory_transactions WHERE transaction_type = ADJUSTMENT
    Written by: batch update, batch delete, reconciliation approval
    Positive = stock added, Negative = stock removed.
    """
    result = (
        db.query(func.coalesce(func.sum(InventoryTransaction.quantity), 0))
        .filter(
            InventoryTransaction.tenant_id == tenant_id,
            InventoryTransaction.inventory_item_id == inventory_item_id,
            InventoryTransaction.transaction_type == TransactionType.ADJUSTMENT,
            InventoryTransaction.transaction_date >= start_dt,
            InventoryTransaction.transaction_date <= end_dt,
        )
        .scalar()
    )
    return Decimal(str(result or 0)).quantize(THREE_PLACES)

class ReconciliationService:

    def __init__(self, db: Session):
        self.db = db

    def create_period(
        self,
        tenant_id: int,
        user_id: int,
        data: ReconciliationPeriodCreate,
    ) -> ReconciliationPeriod:
        existing = (
            self.db.query(ReconciliationPeriod)
            .filter(
                ReconciliationPeriod.tenant_id == tenant_id,
                ReconciliationPeriod.period_year == data.period_year,
                ReconciliationPeriod.period_month == data.period_month,
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reconciliation period for {data.period_year}-{data.period_month:02d} already exists",
            )

        _, last_day = monthrange(data.period_year, data.period_month)
        period = ReconciliationPeriod(
            tenant_id=tenant_id,
            user_id=user_id,
            period_year=data.period_year,
            period_month=data.period_month,
            period_start_date=date(data.period_year, data.period_month, 1),
            period_end_date=date(data.period_year, data.period_month, last_day),
            costing_method=data.costing_method,
            variance_threshold_pct=data.variance_threshold_pct or Decimal("5.00"),
            notes=data.notes,
            status=ReconciliationStatus.DRAFT,
        )
        self.db.add(period)
        self.db.commit()
        self.db.refresh(period)
        return period

    def initialize_period(
        self,
        period_id: int,
        tenant_id: int,
    ) -> ReconciliationPeriod:
        """
        For every active inventory item compute:

          opening      = prev period physical_closing  OR  inventory.current_quantity
          purchases    = inventory_transactions (PURCHASE)
          consumption  = preparation_ingredient_history + order_packaging
          wastage      = wastage_management (inventory type + dish breakdown rows)
          adjustment   = inventory_transactions (ADJUSTMENT, signed)
          theoretical  = opening + purchases - consumption - wastage ± adjustment
        """
        period = self._get_period_or_404(period_id, tenant_id)

        if period.status not in (ReconciliationStatus.DRAFT, ReconciliationStatus.IN_PROGRESS):
            raise HTTPException(
                status_code=400,
                detail="Period can only be initialized in DRAFT or IN_PROGRESS status",
            )

        start_dt = datetime.combine(period.period_start_date, datetime.min.time())
        end_dt   = datetime.combine(period.period_end_date,   datetime.max.time())

        items = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            )
            .all()
        )

        # Clear stale line items if re-initializing
        self.db.query(ReconciliationLineItem).filter(
            ReconciliationLineItem.period_id == period_id
        ).delete()

        total_opening     = Decimal("0")
        total_purchases   = Decimal("0")
        total_consumption = Decimal("0")
        total_wastage     = Decimal("0")
        total_adjustment  = Decimal("0")

        for item in items:

            # Opening quantity
            prev_period = self._get_previous_period(tenant_id, period.period_year, period.period_month)
            if prev_period:
                prev_line = (
                    self.db.query(ReconciliationLineItem)
                    .filter(
                        ReconciliationLineItem.period_id == prev_period.id,
                        ReconciliationLineItem.inventory_item_id == item.id,
                    )
                    .first()
                )
                opening_qty = (
                    Decimal(str(prev_line.physical_closing_quantity))
                    if prev_line and prev_line.physical_closing_quantity is not None
                    else Decimal(str(item.current_quantity or 0))
                )
            else:
                opening_qty = Decimal(str(item.current_quantity or 0))

            unit_cost = _get_unit_cost(
                self.db, item.id, tenant_id,
                period.period_end_date,
                period.costing_method,
            )

            purchases_qty   = _get_purchases_qty(self.db, tenant_id, item.id, start_dt, end_dt)
            consumption_qty = _get_consumption_qty(self.db, tenant_id, item.id, start_dt, end_dt)
            wastage_qty     = _get_wastage_qty(self.db, tenant_id, item.id, start_dt, end_dt)
            adjustment_qty  = _get_adjustment_qty_signed(self.db, tenant_id, item.id, start_dt, end_dt)

            theoretical_closing = (
                opening_qty
                + purchases_qty
                - consumption_qty
                - wastage_qty
                + adjustment_qty
            )

            opening_value             = (opening_qty         * unit_cost).quantize(TWO_PLACES)
            purchases_value           = (purchases_qty       * unit_cost).quantize(TWO_PLACES)
            consumption_value         = (consumption_qty     * unit_cost).quantize(TWO_PLACES)
            wastage_value             = (wastage_qty         * unit_cost).quantize(TWO_PLACES)
            adjustment_value          = (adjustment_qty      * unit_cost).quantize(TWO_PLACES)
            theoretical_closing_value = (theoretical_closing * unit_cost).quantize(TWO_PLACES)

            category_name = item.item_category.name if item.item_category else None

            line_item = ReconciliationLineItem(
                tenant_id=tenant_id,
                period_id=period_id,
                inventory_item_id=item.id,
                item_name=item.name,
                item_sku=item.sku,
                unit=item.unit,
                item_category=category_name,
                opening_quantity=opening_qty,
                purchases_quantity=purchases_qty,
                consumption_quantity=consumption_qty,
                wastage_quantity=wastage_qty,
                adjustment_quantity=adjustment_qty,
                theoretical_closing_quantity=theoretical_closing,
                unit_cost=unit_cost,
                opening_value=opening_value,
                purchases_value=purchases_value,
                consumption_value=consumption_value,
                wastage_value=wastage_value,
                adjustment_value=adjustment_value,
                theoretical_closing_value=theoretical_closing_value,
            )
            self.db.add(line_item)

            total_opening     += opening_value
            total_purchases   += purchases_value
            total_consumption += consumption_value
            total_wastage     += wastage_value
            total_adjustment  += adjustment_value

        period.total_opening_value             = total_opening.quantize(TWO_PLACES)
        period.total_purchases_value           = total_purchases.quantize(TWO_PLACES)
        period.total_consumption_value         = total_consumption.quantize(TWO_PLACES)
        period.total_wastage_value             = total_wastage.quantize(TWO_PLACES)
        period.total_adjustment_value          = total_adjustment.quantize(TWO_PLACES)
        period.total_theoretical_closing_value = (
            total_opening + total_purchases - total_consumption - total_wastage + total_adjustment
        ).quantize(TWO_PLACES)
        period.status = ReconciliationStatus.IN_PROGRESS

        self.db.commit()
        self.db.refresh(period)
        return period

    def submit_physical_counts(
        self,
        period_id: int,
        tenant_id: int,
        user_id: int,
        counts: List[PhysicalCountEntry],
    ) -> dict:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status != ReconciliationStatus.IN_PROGRESS:
            raise HTTPException(400, "Physical counts can only be entered while period is IN_PROGRESS")

        created = []
        for entry in counts:
            item = self.db.query(Inventory).filter(
                Inventory.id == entry.inventory_item_id,
                Inventory.tenant_id == tenant_id,
                Inventory.is_active == True,
            ).first()
            if not item:
                raise HTTPException(
                    status_code=404,
                    detail=f"Inventory item with id {entry.inventory_item_id} not found or does not belong to this tenant",
                )

            pc = PhysicalCount(
                tenant_id=tenant_id,
                period_id=period_id,
                inventory_item_id=entry.inventory_item_id,
                counted_by_user_id=user_id,
                count_type=entry.count_type.value,
                counted_quantity=entry.counted_quantity,
                unit=entry.unit or item.unit,
                storage_location=entry.storage_location,
                batch_number=entry.batch_number,
                notes=entry.notes,
            )
            self.db.add(pc)
            created.append(pc)

        self.db.commit()
        return {"created_count": len(created)}

    def finalize_physical_count(
        self,
        period_id: int,
        tenant_id: int,
    ) -> ReconciliationPeriod:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status != ReconciliationStatus.IN_PROGRESS:
            raise HTTPException(400, "Period must be IN_PROGRESS to finalize physical count")

        closing_totals = (
            self.db.query(
                PhysicalCount.inventory_item_id,
                func.sum(PhysicalCount.counted_quantity).label("total_qty"),
            )
            .filter(
                PhysicalCount.period_id == period_id,
                PhysicalCount.tenant_id == tenant_id,
                PhysicalCount.count_type == "closing",
            )
            .group_by(PhysicalCount.inventory_item_id)
            .all()
        )

        closing_map = {
            row.inventory_item_id: Decimal(str(row.total_qty))
            for row in closing_totals
        }

        line_items = (
            self.db.query(ReconciliationLineItem)
            .filter(ReconciliationLineItem.period_id == period_id)
            .all()
        )

        total_physical = Decimal("0")
        total_variance = Decimal("0")

        for li in line_items:
            physical_qty    = closing_map.get(li.inventory_item_id, Decimal("0"))
            theoretical_qty = Decimal(str(li.theoretical_closing_quantity or 0))
            unit_cost       = Decimal(str(li.unit_cost or 0))

            variance_qty   = physical_qty - theoretical_qty
            physical_value = (physical_qty * unit_cost).quantize(TWO_PLACES)
            variance_value = (variance_qty * unit_cost).quantize(TWO_PLACES)

            if theoretical_qty != 0:
                variance_pct = (
                    abs(variance_qty) / abs(theoretical_qty) * 100
                ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            else:
                variance_pct = Decimal("0") if variance_qty == 0 else Decimal("100")

            threshold = Decimal(str(period.variance_threshold_pct or 5))
            v_status = (
                VarianceStatus.EXCEEDS_THRESHOLD
                if variance_pct > threshold
                else VarianceStatus.WITHIN_THRESHOLD
            )

            li.physical_closing_quantity = physical_qty
            li.physical_closing_value    = physical_value
            li.variance_quantity         = variance_qty
            li.variance_value            = variance_value
            li.variance_pct              = variance_pct
            li.variance_status           = v_status

            total_physical += physical_value
            total_variance += variance_value

        period.total_physical_closing_value = total_physical.quantize(TWO_PLACES)
        period.total_variance_value         = total_variance.quantize(TWO_PLACES)

        self.db.commit()
        self.db.refresh(period)
        return period

    def update_line_item_physical_count(
        self,
        period_id: int,
        line_item_id: int,
        tenant_id: int,
        physical_qty: Decimal,
        variance_notes: Optional[str] = None,
    ) -> ReconciliationLineItem:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status not in (ReconciliationStatus.IN_PROGRESS,):
            raise HTTPException(400, "Period must be IN_PROGRESS to update physical count")

        li = (
            self.db.query(ReconciliationLineItem)
            .filter(
                ReconciliationLineItem.id == line_item_id,
                ReconciliationLineItem.period_id == period_id,
            )
            .first()
        )
        if not li:
            raise HTTPException(404, "Line item not found")

        theoretical_qty = Decimal(str(li.theoretical_closing_quantity or 0))
        unit_cost       = Decimal(str(li.unit_cost or 0))
        variance_qty    = physical_qty - theoretical_qty
        physical_value  = (physical_qty * unit_cost).quantize(TWO_PLACES)
        variance_value  = (variance_qty * unit_cost).quantize(TWO_PLACES)

        if theoretical_qty != 0:
            variance_pct = (
                abs(variance_qty) / abs(theoretical_qty) * 100
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        else:
            variance_pct = Decimal("0") if variance_qty == 0 else Decimal("100")

        threshold = Decimal(str(period.variance_threshold_pct or 5))
        v_status = (
            VarianceStatus.EXCEEDS_THRESHOLD if variance_pct > threshold
            else VarianceStatus.WITHIN_THRESHOLD
        )

        li.physical_closing_quantity = physical_qty
        li.physical_closing_value    = physical_value
        li.variance_quantity         = variance_qty
        li.variance_value            = variance_value
        li.variance_pct              = variance_pct
        li.variance_status           = v_status
        if variance_notes:
            li.variance_notes = variance_notes

        self.db.commit()
        self.db.refresh(li)
        return li

    def submit_for_approval(
        self,
        period_id: int,
        tenant_id: int,
        user_id: int,
        notes: Optional[str] = None,
    ) -> ReconciliationPeriod:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status != ReconciliationStatus.IN_PROGRESS:
            raise HTTPException(400, "Period must be IN_PROGRESS to submit for approval")

        missing = (
            self.db.query(ReconciliationLineItem)
            .filter(
                ReconciliationLineItem.period_id == period_id,
                ReconciliationLineItem.physical_closing_quantity == None,
            )
            .count()
        )
        if missing > 0:
            raise HTTPException(
                400,
                f"{missing} line item(s) still missing physical count. Complete all counts before submitting.",
            )

        period.status               = ReconciliationStatus.PENDING_APPROVAL
        period.submitted_by_user_id = user_id
        period.submitted_at         = datetime.utcnow()
        if notes:
            period.notes = notes

        self.db.commit()
        self.db.refresh(period)
        return period

    def approve_period(
        self,
        period_id: int,
        tenant_id: int,
        approver_user_id: int,
        notes: Optional[str] = None,
    ) -> ReconciliationPeriod:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status != ReconciliationStatus.PENDING_APPROVAL:
            raise HTTPException(400, "Period must be PENDING_APPROVAL to approve")

        # Process ALL line items — every item current_quantity must be set
        # directly to its physical_closing_quantity (the verified ground truth).
        # We must NOT add variance on top of current_quantity because
        # current_quantity has already moved during the month due to consumption
        # and batch changes — adding a delta would cause drift or zero out stock.
        all_line_items = (
            self.db.query(ReconciliationLineItem)
            .filter(ReconciliationLineItem.period_id == period_id)
            .all()
        )

        for li in all_line_items:
            if li.physical_closing_quantity is None:
                continue  # submit_for_approval already blocks this

            physical_qty = Decimal(str(li.physical_closing_quantity))
            unit_cost    = Decimal(str(li.unit_cost or 0))
            variance     = Decimal(str(li.variance_quantity or 0))

            # Create adjustment transaction only when there is a real variance
            if variance != 0 and li.inventory_item_id:
                tx = InventoryTransaction(
                    tenant_id=tenant_id,
                    inventory_item_id=li.inventory_item_id,
                    transaction_type=TransactionType.ADJUSTMENT,
                    quantity=float(variance),
                    unit_cost=float(unit_cost),
                    total_value=float(variance * unit_cost),
                    reference_id=f"Reconciliation {period.period_year}-{period.period_month:02d} variance adjustment",
                )
                self.db.add(tx)
                self.db.flush()
                li.adjustment_transaction_id = tx.id

            # Always set current_quantity = physical count.
            # Physical count IS the verified reality — set it directly,
            # never compute it by adding/subtracting from the old value.
            if li.inventory_item_id:
                inv_item = self.db.query(Inventory).filter(
                    Inventory.id == li.inventory_item_id
                ).first()
                if inv_item:
                    inv_item.current_quantity = float(physical_qty)

            li.variance_status = VarianceStatus.ADJUSTED

        period.status               = ReconciliationStatus.APPROVED
        period.approved_by_user_id  = approver_user_id
        period.approved_at          = datetime.utcnow()
        if notes:
            period.notes = (period.notes or "") + f"\nApproval note: {notes}"

        self.db.commit()
        self.db.refresh(period)
        return period

    def reject_period(
        self,
        period_id: int,
        tenant_id: int,
        rejection_reason: str,
    ) -> ReconciliationPeriod:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status != ReconciliationStatus.PENDING_APPROVAL:
            raise HTTPException(400, "Period must be PENDING_APPROVAL to reject")

        period.status           = ReconciliationStatus.REJECTED
        period.rejection_reason = rejection_reason
        self.db.commit()
        self.db.refresh(period)
        return period

    def close_period(
        self,
        period_id: int,
        tenant_id: int,
    ) -> ReconciliationPeriod:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status != ReconciliationStatus.APPROVED:
            raise HTTPException(400, "Period must be APPROVED before closing")

        period.status = ReconciliationStatus.CLOSED
        self.db.commit()
        self.db.refresh(period)
        return period


    def add_adjustment(
        self,
        period_id: int,
        tenant_id: int,
        user_id: int,
        data: AdjustmentCreate,
    ) -> ReconciliationAdjustment:
        period = self._get_period_or_404(period_id, tenant_id)
        if period.status not in (
            ReconciliationStatus.IN_PROGRESS,
            ReconciliationStatus.PENDING_APPROVAL,
        ):
            raise HTTPException(400, "Adjustments can only be added while period is IN_PROGRESS or PENDING_APPROVAL")

        unit_cost = _get_unit_cost(
            self.db, data.inventory_item_id, tenant_id,
            period.period_end_date, period.costing_method,
        )
        qty   = Decimal(str(data.quantity_adjusted))
        value = (qty * unit_cost).quantize(TWO_PLACES)

        li = (
            self.db.query(ReconciliationLineItem)
            .filter(
                ReconciliationLineItem.period_id == period_id,
                ReconciliationLineItem.inventory_item_id == data.inventory_item_id,
            )
            .first()
        )

        adj = ReconciliationAdjustment(
            tenant_id=tenant_id,
            period_id=period_id,
            line_item_id=li.id if li else None,
            inventory_item_id=data.inventory_item_id,
            created_by_user_id=user_id,
            reason=data.reason,
            quantity_adjusted=qty,
            unit_cost=unit_cost,
            value_adjusted=value,
            notes=data.notes,
        )
        self.db.add(adj)

        if li:
            current_adj            = Decimal(str(li.adjustment_quantity or 0))
            li.adjustment_quantity = current_adj + qty
            li.adjustment_value    = (
                Decimal(str(li.adjustment_value or 0)) + value
            ).quantize(TWO_PLACES)
            theoretical = (
                Decimal(str(li.opening_quantity     or 0))
                + Decimal(str(li.purchases_quantity   or 0))
                - Decimal(str(li.consumption_quantity or 0))
                - Decimal(str(li.wastage_quantity     or 0))
                + li.adjustment_quantity
            )
            li.theoretical_closing_quantity = theoretical
            li.theoretical_closing_value    = (theoretical * unit_cost).quantize(TWO_PLACES)

        self.db.commit()
        self.db.refresh(adj)
        return adj


    def get_monthly_summary(
        self,
        period_id: int,
        tenant_id: int,
    ) -> dict:
        period = self._get_period_or_404(period_id, tenant_id)
        line_items = (
            self.db.query(ReconciliationLineItem)
            .filter(ReconciliationLineItem.period_id == period_id)
            .order_by(ReconciliationLineItem.item_name)
            .all()
        )
        flagged = [li for li in line_items if li.variance_status == VarianceStatus.EXCEEDS_THRESHOLD]

        theoretical_total = Decimal(str(period.total_theoretical_closing_value or 0))
        variance_total    = Decimal(str(period.total_variance_value or 0))

        total_variance_pct = (
            (abs(variance_total) / theoretical_total * 100).quantize(Decimal("0.01"))
            if theoretical_total != 0
            else Decimal("0")
        )

        return {
            "period": period,
            "line_items": line_items,
            "flagged_items": flagged,
            "flagged_items_count": len(flagged),
            "total_variance_pct": total_variance_pct,
        }


    def list_periods(
        self,
        tenant_id: int,
        status_filter: Optional[ReconciliationStatus] = None,
    ) -> List[ReconciliationPeriod]:
        q = self.db.query(ReconciliationPeriod).filter(
            ReconciliationPeriod.tenant_id == tenant_id
        )
        if status_filter:
            q = q.filter(ReconciliationPeriod.status == status_filter)
        return q.order_by(
            ReconciliationPeriod.period_year.desc(),
            ReconciliationPeriod.period_month.desc(),
        ).all()

#helper
    def _get_period_or_404(self, period_id: int, tenant_id: int) -> ReconciliationPeriod:
        period = (
            self.db.query(ReconciliationPeriod)
            .filter(
                ReconciliationPeriod.id == period_id,
                ReconciliationPeriod.tenant_id == tenant_id,
            )
            .first()
        )
        if not period:
            raise HTTPException(404, "Reconciliation period not found")
        return period

    def _get_previous_period(
        self,
        tenant_id: int,
        year: int,
        month: int,
    ) -> Optional[ReconciliationPeriod]:
        prev_month = month - 1
        prev_year  = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1

        return (
            self.db.query(ReconciliationPeriod)
            .filter(
                ReconciliationPeriod.tenant_id == tenant_id,
                ReconciliationPeriod.period_year  == prev_year,
                ReconciliationPeriod.period_month == prev_month,
                ReconciliationPeriod.status == ReconciliationStatus.CLOSED,
            )
            .first()
        )