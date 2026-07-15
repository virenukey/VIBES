from enum import Enum as PyEnum
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Numeric, ForeignKey, Text, CheckConstraint, Index, Enum, func
from app.db.base import Base
from app.db.mixins import TenantMixin
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.orm import relationship

class WastageReason(PyEnum):
    EXPIRY = "expiry"
    DAMAGE = "damage"
    CONTAMINATION = "contamination"
    UNSOLD_DISH = "unsold_dish"
    PREPARATION_ERROR = "preparation_error"
    SPILLAGE = "spillage"
    STAFF_MEAL = "staff_meal"
    SAMPLING = "sampling"
    DISH_NOT_ORDRED = "dish_not_ordered"
    OTHER = "other"

class WastageType(PyEnum):
    DISH = "dish"
    INVENTORY = "inventory"
    SEMI_FINISHED = "semi_finished" 
    COMBO = "combo"
class ReportPeriod(PyEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"

class Wastage(TenantMixin, Base):
    __tablename__ = "wastage_management"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    wastage_type = Column(Enum(WastageType, name="wastagetype", values_callable=lambda x: [e.value for e in x]), nullable=False)

    inventory_item_id = Column(Integer, ForeignKey("inventory.id", ondelete="CASCADE"), nullable=True)
    inventory_batch_id = Column(Integer, ForeignKey("inventory_batches.id", ondelete="SET NULL"), nullable=True)

    semi_finished_product_id = Column(Integer, ForeignKey("semi_finished_products.id", ondelete="SET NULL"), nullable=True)
    semi_finished_batch_id = Column(Integer, ForeignKey("pre_prepared_material_stock.id", ondelete="SET NULL"), nullable=True)

    dish_id = Column(Integer, ForeignKey("dishes.id", ondelete="CASCADE"), nullable=True)
    preparation_log_id = Column(Integer, ForeignKey("dish_preparation_batch_logs.id", ondelete="SET NULL"), nullable=True)

    quantity_wasted = Column(Numeric(12, 3), nullable=False)
    unit = Column(String(50), nullable=True)
    unit_cost = Column(Numeric(12, 4), nullable=True)
    cost_value = Column(Numeric(12, 4), nullable=True)  # quantity_wasted * unit_cost

    wastage_reason = Column(Enum(WastageReason, name="wastagereason",values_callable=lambda x: [e.value for e in x]), nullable=False)
    wastage_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    combo_id = Column(Integer, ForeignKey("combos.id", ondelete="SET NULL"), nullable=True)

    notes = Column(Text, nullable=True)
    photo_url = Column(String(500), nullable=True)

    is_breakdown = Column(Boolean, default=False)  # True = this row is a constituent ingredient of an unsold dish
    parent_wastage_id = Column(UUID(as_uuid=True), ForeignKey("wastage_management.id", ondelete="CASCADE"), nullable=True)

    recorded_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    semi_finished_qty  = Column(Numeric(12, 3), nullable=True)
    semi_finished_unit_used = Column(String(50), nullable=True)
    is_active = Column(Boolean,default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    parent_wastage = relationship("Wastage",foreign_keys=[parent_wastage_id],remote_side=[id],back_populates="breakdown_items",)
    breakdown_items = relationship("Wastage",foreign_keys=[parent_wastage_id],back_populates="parent_wastage",)
    dish = relationship("Dish", back_populates="wastage")
    inventory_item = relationship("Inventory")
    inventory_batch = relationship("InventoryBatch")
    recorded_by = relationship("User")
    inventory_item = relationship("Inventory", backref="wastage_records")
    semi_finished_product = relationship("SemiFinishedProduct", foreign_keys=[semi_finished_product_id])
    semi_finished_batch = relationship("PrePreparedMaterialStock", foreign_keys=[semi_finished_batch_id])
    combo = relationship("Combo", foreign_keys=[combo_id])
    # __table_args__ = (
    #     Index("idx_wastage_tenant", "tenant_id"),
    #     Index("idx_wastage_tenant_date", "tenant_id", "wastage_date"),
    #     Index("idx_wastage_tenant_type", "tenant_id", "wastage_type"),
    #     Index("idx_wastage_tenant_reason", "tenant_id", "wastage_reason"),

    #     CheckConstraint("quantity_wasted > 0", name="ck_wastage_qty_positive"),
    #     CheckConstraint("unit_cost >= 0", name="ck_wastage_unit_cost_non_negative"),

    #     CheckConstraint(
    #         """
    #         (wastage_type = 'dish' AND dish_id IS NOT NULL AND inventory_item_id IS NULL)
    #         OR
    #         (wastage_type = 'inventory' AND inventory_item_id IS NOT NULL AND dish_id IS NULL)
    #         """,
    #         name="ck_wastage_type_target"
    #     ),
    # )