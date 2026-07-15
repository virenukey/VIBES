"""
app/schemas/order.py
Pydantic schemas for Order Management
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator, validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum

class AddSaleIngredientItem(BaseModel):
    dish_id: int = Field(..., description="Dish ID")
    qty_sold: int = Field(..., gt=0, description="Quantity sold")
    date : datetime | None = None

class ComboSaleItem(BaseModel):
    combo_id: int
    qty_sold: int
    date: Optional[datetime] = None

class OrderSaleRequest(BaseModel):
    sales: List[AddSaleIngredientItem] = []
    combo_sales: List[ComboSaleItem] = []
    sale_date: Optional[datetime] = Field(None, description="Sale date (defaults to now if not provided)")
