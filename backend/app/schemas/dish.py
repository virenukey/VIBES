from pydantic import BaseModel, ConfigDict, Field, field_validator , model_validator, validator
from typing import List, Optional
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from uuid import UUID
from app.models.dish import PrePreparedProductType
from app.models.inventory import UnitType

#enums
class PerishableLifeCycle(str, Enum):
    FRESH = "FRESH"
    NEAR_EXPIRY = "NEAR_EXPIRY"
    EXPIRED = "EXPIRED"

class DishIngredientType(str, Enum):
    """Type of ingredient - raw from inventory or semi-finished"""
    RAW = "RAW"                    # Direct from inventory
    SEMI_FINISHED = "SEMI_FINISHED"  # From intermediate ingredient stock

class PreparationBatchStatus(str, Enum):
    """Status of preparation batch"""
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    CANCELLED = "CANCELLED"

#batch and ingredinet schema
class BatchInfo(BaseModel):
    batch_id: int
    batch_number: str
    expiry_date: Optional[date]
    quantity_remaining: Decimal
    days_until_expiry: Optional[int]
    lifecycle_stage: Optional[str]
    unit_cost: Decimal
    is_near_expiry: bool
    priority_rank: int
    suggestion_reason: str  
    warning_message: Optional[str] = None
    allocated_quantity: Optional[float] = None

    class Config:
        from_attributes = True

#schema for pre prepared food 
class SemiFinishedIngredientAdd(BaseModel):
    """Raw ingredient for semi-finished product"""
    ingredient_id: int
    quantity_required: float
    unit: str = "gm"
    preferred_batch_id: Optional[int] = None

class SemiFinishedProductCreate(BaseModel):
    """Create semi-finished product recipe"""
    name: str
    product_type: PrePreparedProductType
    description: Optional[str] = None
    unit: str = "gm"
    shelf_life_hours: Optional[int] = None
    preparation_time_minutes: Optional[int] = None
    storage_location_id: int
    yield_quantity: float  # How much this recipe produces
    ingredients: List[SemiFinishedIngredientAdd]

class ProduceSemiFinished(BaseModel):
    """Produce batch of semi-finished product"""
    product_id: UUID
    quantity_to_produce: float
    notes: Optional[str] = None

# dish ingredients schema
class AddDishIngredient(BaseModel):
    """Add single ingredient to dish - supports both RAW and SEMI_FINISHED"""
    ingredient_type: DishIngredientType = DishIngredientType.RAW
    
    # For RAW ingredients from inventory
    ingredient_id: Optional[int] = Field (
        None, 
        description="Required if ingredient_type is RAW"
    )
    # ingredient_data:UUID
    # For SEMI_FINISHED ingredients
    preprepred_material_id: Optional[UUID] = Field(
        None,
        description="Required if ingredient_type is SEMI_FINISHED"
    )
    quantity_required: float
    unit: str = "gm"
    # preferred_batch_id: Optional[int] = Field(
    #     None,
    #     description="Optional: Specify a preferred batch to use"
    # )

    @model_validator(mode='after')
    def validate_ingredient_type(self):
        """Ensure correct fields are provided based on ingredient_type"""
        if self.ingredient_type == DishIngredientType.RAW:
            if not self.ingredient_id:
                raise ValueError("ingredient_id is required when ingredient_type is RAW")
        elif self.ingredient_type == DishIngredientType.SEMI_FINISHED:
            if not self.preprepred_material_id:
                raise ValueError("semi_finished_product_id is required when ingredient_type is SEMI_FINISHED")
        return self
    class Config:
        use_enum_values = True

class BulkDishIngredientAdd(BaseModel):
    """Add multiple ingredients to dish at once"""
    ingredients: List[AddDishIngredient]

class UpdateDishIngredient(BaseModel):
    """Update dish ingredient"""
    quantity_required: Optional[float] = None
    new_batch_id: Optional[int] = None

class DishIngredientResponse(BaseModel):
    """Response for dish ingredient with batch info"""
    id: int
    dish_id: int
    ingredient_id: Optional[int]
    semi_finished_product_id: Optional[int]
    ingredient_name: str
    ingredient_type: str  # "RAW" or "SEMI_FINISHED"
    quantity_required: float
    unit: str
    cost_per_unit: float
    batch_info: Optional[BatchInfo]
    created_at: datetime

class IngredientAddResult(BaseModel):
    """Result of adding a single ingredient"""
    success: bool
    ingredient_data: Optional[DishIngredientResponse] = None
    error_message: Optional[str] = None
    warning_message: Optional[str] = None

class BulkAddResponse(BaseModel):
    """Response for bulk ingredient addition"""
    dish_id: int
    dish_name: str
    total_requested: int
    successful: int
    failed: int
    results: List[IngredientAddResult]
    total_cost: float
    overall_warning: Optional[str] = None

class AvailableBatchesResponse(BaseModel):
    """Available batches for an ingredient"""
    ingredient_id: int
    ingredient_name: str
    unit: str
    total_batches: int
    total_available_quantity: Decimal
    fresh_batches: int
    near_expiry_batches: int
    expired_batches: int
    batches: List[BatchInfo]
    recommended_batch: Optional[BatchInfo]
    warning: Optional[str] = None

# dish type schema
class DishTypeBase(BaseModel):
    name: str

class DishTypeCreate(DishTypeBase):
    pass

class DishTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)

class DishTypeOut(BaseModel):
    id: int
    name: str
    tenant_id: UUID
    
    model_config = ConfigDict(from_attributes=True)

# dish schema
class DishBase(BaseModel):
    tenant_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    type_id: int
    standard_portion_size: Optional[str] = Field(None, max_length=50)
    yield_quantity: Optional[Decimal] = None
    preparation_time_minutes: Optional[int] = Field(None, ge=0)
    selling_price: Optional[Decimal] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)

class DishCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type_id: int
    standard_portion_size: Optional[str] = Field(None, max_length=50)
    yield_quantity: Optional[Decimal] = None
    preparation_time_minutes: Optional[int] = Field(None, ge=0)
    selling_price: Optional[Decimal] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)

class DishUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    type_id: Optional[int] = None
    standard_portion_size: Optional[str] = Field(None, max_length=50)
    yield_quantity: Optional[Decimal] = None
    preparation_time_minutes: Optional[int] = Field(None, ge=0)
    selling_price: Optional[Decimal] = None
    is_active: Optional[bool] = None

# schema for preparation dish
class SingleDishPreparation(BaseModel):
    """Prepare single dish"""
    dish_id: int
    quantity: int = Field(gt=0, description="Number of dishes to prepare")
    notes: Optional[str] = None

class BatchDishPreparation(BaseModel):
    """Prepare multiple dishes simultaneously"""
    preparations: List[SingleDishPreparation]
    batch_notes: Optional[str] = None

class PreparationResult(BaseModel):
    """Result of dish preparation"""
    preparation_log_id: int
    dish_id: int
    dish_name: str
    quantity_prepared: int
    ingredients_consumed: List[dict]
    total_cost: float
    inventory_deducted: bool
    preparation_date: datetime

class BatchPreparationResult(BaseModel):
    """Result of batch preparation"""
    batch_id: int
    batch_number: str
    status: str
    total_dishes_prepared: int
    successful: int
    failed: int
    total_cost: float
    started_at: datetime
    completed_at: Optional[datetime]
    duration_minutes: Optional[int]
    preparations: List[PreparationResult]
    warnings: List[str]

class PreparationHistoryResponse(BaseModel):
    """Preparation history log entry"""
    id: int
    dish_id: int
    dish_name: str
    quantity_prepared: int
    user_id: int
    user_name: Optional[str]
    preparation_date: datetime
    batch_number: Optional[str]
    notes: Optional[str]
    ingredients_consumed: List[dict]
    total_cost: float
    inventory_deducted: bool

class DishIngredientOut(BaseModel):
    ingredient_name: str
    quantity_required: float
    unit: str
    cost_per_unit: float

    class Config:
        from_attributes = True    

class DishTypeOut(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True        

class DishOut(DishBase):
    id: int
    name: str
    type: DishTypeOut
    ingredients: List[DishIngredientOut]

    model_config = ConfigDict(from_attributes=True)        

class SemiFinishedIngredientUpdate(BaseModel):
    ingredient_id: int = Field(..., gt=0)
    quantity_required: Decimal = Field(..., gt=0)
    unit: str = Field(..., min_length=1)
    preferred_batch_id: Optional[int] = None    

class SemiFinishedProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    product_type: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    shelf_life_hours: Optional[int] = Field(None, ge=0)
    preparation_time_minutes: Optional[int] = Field(None, ge=0)
    storage_location_id: Optional[int] = None
    yield_quantity: Optional[Decimal] = Field(None, gt=0)

    ingredients: Optional[List[SemiFinishedIngredientUpdate]] = None

    class Config:
        orm_mode = True    
class UpdateDishIngredient(BaseModel):
    dish_ingredient_id: int 
    quantity_required: Optional[Decimal] = None
    unit: Optional[str] = None
    ingredient_id: Optional[int] = None
    preprepred_material_id: Optional[int] = None

class BulkDishIngredientUpdate(BaseModel):
    ingredients: List[UpdateDishIngredient]        

class BulkDishIngredientDelete(BaseModel):
    dish_ingredient_ids: List[int]    
    
# schema for new flow management of dish ingredients
class DishIngredientItem(BaseModel):
    ingredient_id: int = Field(..., description="Inventory item ID")
    quantity_required: float = Field(..., gt=0)
    unit: UnitType = Field(default=UnitType.GRAM)

class CreateDishWithIngredientsRequest(BaseModel):
    dish_name: str = Field(..., min_length=1, max_length=255)
    type_id: int = Field(..., description="DishType ID")
    selling_price: Optional[float] = Field(default=None, ge=0)
    ingredients: List[DishIngredientItem] = Field(..., min_items=1)

    @validator("ingredients")
    def no_duplicate_ingredient_ids(cls, v):
        ids = [i.ingredient_id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate ingredient_id entries are not allowed")
        return v
class DishIngredientResponse(BaseModel):
    id: int
    dish_id: int
    ingredient_id: Optional[int]
    ingredient_name: str
    quantity_required: float
    unit: str
    cost_per_unit: float
    created_at: datetime

    class Config:
        orm_mode = True
class CreateDishWithIngredientsResponse(BaseModel):
    dish_id: int
    dish_name: str
    type_id: int
    added_count: int
    ingredients: List[DishIngredientResponse]

    class Config:
        orm_mode = True    

class UpdateIngredientItem(BaseModel):
    ingredient_id: int
    quantity_required: float
    unit: str

class UpdateDishWithIngredientsRequest(BaseModel):
    dish_name: Optional[str] = None
    type_id: Optional[int] = None
    selling_price: Optional[float] = None
    is_active: Optional[bool] = None
    ingredients: Optional[List[UpdateIngredientItem]] = None        

############# new schema ###############
class SemiFinishedIngredientItem(BaseModel):
    ingredient_id: Optional[int] = None
    ingredient_name: Optional[str] = None 
    quantity_required: float
    unit: str
    fixed_cost_amount: Optional[float] = None  

    @model_validator(mode="after")
    def validate_id_or_name(self):
        if not self.ingredient_id and not self.ingredient_name:
            raise ValueError("Either ingredient_id or ingredient_name must be provided.")
        return self
    
class CreateSemiFinishedRequest(BaseModel):
    name: str
    yield_quantity: float        # how much output this recipe produces
    yield_unit: str              # unit of that output (e.g. "gm", "ml")
    ingredients: List[SemiFinishedIngredientItem]

class RawIngredientItem(BaseModel):
    ingredient_id: Optional[int] = None
    ingredient_name: Optional[str] = None
    cost_per_unit: Optional[float] = None
    quantity_required: float
    unit: str
    fixed_cost_amount: Optional[float] = None  

    @model_validator(mode="after")
    def validate_id_or_name(self):
        if not self.ingredient_id and not self.ingredient_name:
            raise ValueError("Either ingredient_id or ingredient_name must be provided.")
        return self

class SemiFinishedIngredientItem(BaseModel):
    semi_finished_id: Optional[int] = None 
    semi_finished_name: Optional[str] = None 
    semi_finished_name: Optional[str] = None 
    quantity_required: float
    unit: str
    fixed_cost_amount: Optional[float] = None  

    @model_validator(mode="after")
    def validate_id_or_name(self):
        if not self.semi_finished_id and not self.semi_finished_name:
            raise ValueError("Either semi_finished_id or semi_finished_name must be provided.")
        return self

class CreateDishWithIngredientsRequest(BaseModel):
    dish_name: str
    type_id: int
    type_name: Optional[str] = None
    selling_price: float
    raw_ingredients: list[RawIngredientItem] = []
    semi_finished_ingredients: list[SemiFinishedIngredientItem] = []   

# class UpdateIngredientItem(BaseModel):
#     ingredient_id: Optional[int] = None 
#     quantity_required: float
#     unit: str
#     cost_per_unit: Optional[float] = None
#     fixed_cost_amount: Optional[float] = None       


# class UpdateSemiFinishedRequest(BaseModel):
#     name: Optional[str] = None
#     yield_quantity: Optional[float] = None
#     yield_unit: Optional[str] = None
#     ingredients: Optional[List[UpdateIngredientItem]] = None     
    
class IngredientItemUpdate(BaseModel):
    ingredient_id:     Optional[int]   = None   # optional for brand-new items
    ingredient_name:   Optional[str]   = None
    semi_finished_id:  Optional[int]   = None
    quantity_required: float
    unit:              str
    cost_per_unit:     Optional[float] = None
    fixed_cost_amount: Optional[float] = None
    is_semi_finished:  Optional[bool]  = False

    @field_validator("ingredient_id", "semi_finished_id", mode="before")
    @classmethod
    def zero_to_none(cls, v):
        # Frontend sends 0 when no ID — treat as None
        return None if v == 0 else v

    @model_validator(mode="after")
    def resolve_ids(self) -> "IngredientItemUpdate":
        # If is_semi_finished=True but ingredient_id is missing,
        # promote semi_finished_id → ingredient_id
        if self.is_semi_finished and not self.ingredient_id and self.semi_finished_id:
            self.ingredient_id = self.semi_finished_id

        # If is_semi_finished=False but semi_finished_id leaked in,
        # clear it so it doesn't cause confusion
        if not self.is_semi_finished and self.semi_finished_id:
            self.semi_finished_id = None

        return self
class UpdateSemiFinishedRequest(BaseModel):
    name:           Optional[str]                        = None
    yield_quantity: Optional[float]                      = None
    yield_unit:     Optional[str]                        = None
    ingredients:    Optional[List[IngredientItemUpdate]] = None


####################Combos#############
class ComboItemCreate(BaseModel):
    dish_id: Optional[int] = None
    semi_finished_id:Optional[int] = None
    ingredient_id:Optional[int] = None
    quantity:Decimal = Decimal("1")
    unit:Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_source(self):
        sources = [self.dish_id, self.semi_finished_id, self.ingredient_id]
        if sum(s is not None for s in sources) != 1:
            raise ValueError(
                "Exactly one of dish_id, semi_finished_id, ingredient_id must be provided."
            )
        return self
class ComboCreate(BaseModel):
    name:    str
    type_id: Optional[int] = None
    selling_price: Optional[Decimal] = None
    items:   list[ComboItemCreate]
class ComboItemUpdate(BaseModel):
    dish_id:           Optional[int] = None
    semi_finished_id:  Optional[int] = None
    ingredient_id:     Optional[int] = None
    quantity:          Decimal = Decimal("1")
    unit:              Optional[str] = None  # user-provided unit

    @model_validator(mode="after")
    def exactly_one_source(self):
        sources = [self.dish_id, self.semi_finished_id, self.ingredient_id]
        if sum(s is not None for s in sources) != 1:
            raise ValueError(
                "Exactly one of dish_id, semi_finished_id, ingredient_id must be provided."
            )
        return self
class ComboUpdate(BaseModel):
    name:      Optional[str] = None
    type_id:   Optional[int] = None
    is_active: Optional[bool] = None
    selling_price: Optional[Decimal] = None
    items:     Optional[list[ComboItemUpdate]] = None 
