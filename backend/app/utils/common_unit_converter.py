from decimal import Decimal
from enum import Enum

UNIT_CONVERT = {
    "kg": Decimal("1000"),
    "gm": Decimal("1"),
    "mg": Decimal("0.001"),
    "liter": Decimal("1000"),
    "ml": Decimal("1"),
    "pcs": Decimal("1"),
    "packet": Decimal("1"),
    "unit":   Decimal("1"), 
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
    "m": Decimal("1000"),   # 1 meter = 1000 mm (base: mm)
    "mm": Decimal("1"),  
    "cm": Decimal("10"),
    "rupee": Decimal("100"),   
    "paise": Decimal("1"),
}


def _normalize_unit(unit) -> str:
    if isinstance(unit, Enum):
        return unit.value.lower()
    return str(unit).strip().lower()


def convert_quantity_unit(value: Decimal, from_unit, to_unit) -> Decimal:
    
    # Normalize both units to plain strings first
    from_unit_str = _normalize_unit(from_unit)
    to_unit_str = _normalize_unit(to_unit)

    # Same unit — no conversion needed
    if from_unit_str == to_unit_str:
        return value

    from_unit_factor = UNIT_CONVERT.get(from_unit_str)
    to_unit_factor = UNIT_CONVERT.get(to_unit_str)

    if from_unit_factor is None:
        raise ValueError(f"Unknown unit: {from_unit_str}")
    if to_unit_factor is None:
        raise ValueError(f"Unknown unit: {to_unit_str}")

    weight_units = {"kg", "gm", "mg"}
    volume_units = {"liter", "ml"}
    length_units = {"m", "mm","cm"}
    currency_units = {"rupee", "paise"}

    from_is_weight = from_unit_str in weight_units
    to_is_weight = to_unit_str in weight_units
    from_is_volume = from_unit_str in volume_units
    to_is_volume = to_unit_str in volume_units
    from_is_length = from_unit_str in length_units 
    to_is_length = to_unit_str in length_units  
    from_is_currency = from_unit_str in currency_units
    to_is_currency   = to_unit_str in currency_units    

    if (from_is_weight != to_is_weight) and \
       (from_is_volume != to_is_volume) and \
       (from_is_length != to_is_length) and \
       (from_is_currency != to_is_currency):
        raise ValueError(
            f"Incompatible units: cannot convert {from_unit_str} to {to_unit_str}"
        )

    base_value = value * from_unit_factor
    return base_value / to_unit_factor


UNIT_ENUM = {
    "kilogram": "kg",
    "gram": "gm",
    "milligram": "mg",
    "liter": "liter",
    "milliliter": "ml",
    "piece": "pcs",
    "packet": "packet",
    "box": "box",
    "carton": "carton",
    "dozen": "dozen",
    "bundle": "bundle",
    "roll": "roll",
    "sheet": "sheet",
    "sachet": "sachet",
    "bottle": "bottle",
    "can": "can",
    "bag": "bag",
    "m":"m",
    "mm":"m",
    "cm":"cm",
}

def _normalize_unit(unit) -> str:
    """
    Safely normalize unit to plain string.
    Handles: str, Enum object, stringified enum like 'UnitType.KILOGRAM'
    """
    if unit is None:
        return "gm"

    # Enum object → extract .value directly
    if hasattr(unit, "value"):
        return unit.value.strip().lower()

    raw = str(unit).strip()

    # Stringified enum like "UnitType.KILOGRAM" stored in DB
    if "." in raw:
        raw = raw.split(".")[-1]    # "UnitType.KILOGRAM" → "KILOGRAM"

    # Map enum member name to actual unit value
    return UNIT_ENUM.get(raw.lower(), raw.lower())

#function to normalize name
def normalize_name(value: str) -> str:
    if not value:
        return ""
    return " ".join(word.capitalize() for word in value.strip().split())    