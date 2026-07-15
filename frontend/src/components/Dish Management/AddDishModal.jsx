import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { FiX, FiPlus, FiTrash2, FiChevronDown } from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";

let _rowCounter = 0;

const newRow = (overrides = {}) => ({
  rowId: ++_rowCounter,
  item: "",
  itemName: "",
  qty: "",
  unit: "",
  cost: "",
  fixedCost: "",
  isFixedCostItem: false,

  isCustomItem: false,
  customItemType: "",

  ...overrides,
});

const getInitialFormData = () => ({
  name: "",
  categoryId: "",
  sellingPrice: "",
});

const UNIT_CATEGORIES = {
  weight: ["kg", "gm", "mg"],
  volume: ["liter", "ml"],
  length: ["m", "cm", "mm"],
  count: [
    "pcs",
    "packet",
    "box",
    "carton",
    "dozen",
    "bundle",
    "roll",
    "sheet",
    "sachet",
    "bottle",
    "can",
    "bag",
  ],
  currency: ["rupee"],
  single: ["unit"],
};

const getUnitCategory = (unit) => {
  for (const category in UNIT_CATEGORIES) {
    if (UNIT_CATEGORIES[category].includes(unit)) {
      return category;
    }
  }
  return null;
};

const convertCost = (baseUnit, targetUnit, baseCost) => {
  let cost = baseCost;

  if (baseUnit === "kg" && targetUnit === "gm") cost /= 1000;
  if (baseUnit === "gm" && targetUnit === "kg") cost *= 1000;
  if (baseUnit === "kg" && targetUnit === "mg") cost /= 1000000;
  if (baseUnit === "mg" && targetUnit === "kg") cost *= 1000000;

  if (baseUnit === "liter" && targetUnit === "ml") cost /= 1000;
  if (baseUnit === "ml" && targetUnit === "liter") cost *= 1000;

  if (baseUnit === "m" && targetUnit === "cm") cost /= 100;
  if (baseUnit === "cm" && targetUnit === "m") cost *= 100;
  if (baseUnit === "m" && targetUnit === "mm") cost /= 1000;
  if (baseUnit === "mm" && targetUnit === "m") cost *= 1000;

  return cost;
};

const calculateWeightedAvg = (batches = []) => {
  let totalQty = 0;
  let totalCost = 0;

  batches.forEach((b) => {
    const qtyRemaining = Number(b.quantity_remaining || 0);
    const qtyReceived = Number(b.quantity_received || 0);
    const batchTotalCost = Number(b.total_cost || 0);

    let remainingCost = 0;
    if (qtyReceived > 0) {
      remainingCost = (qtyRemaining / qtyReceived) * batchTotalCost;
    }

    totalQty += qtyRemaining;
    totalCost += remainingCost;
  });

  return totalQty > 0 ? totalCost / totalQty : 0;
};

const UNIT_OPTIONS = [
  { label: "Kilogram", value: "kg" },
  { label: "Gram", value: "gm" },
  { label: "Milligram", value: "mg" },
  { label: "Liter", value: "liter" },
  { label: "Milliliter", value: "ml" },
  { label: "Piece", value: "pcs" },
  { label: "Packet", value: "packet" },
  { label: "Box", value: "box" },
  { label: "Carton", value: "carton" },
  { label: "Dozen", value: "dozen" },
  { label: "Bundle", value: "bundle" },
  { label: "Roll", value: "roll" },
  { label: "Sheet", value: "sheet" },
  { label: "Sachet", value: "sachet" },
  { label: "Bottle", value: "bottle" },
  { label: "Can", value: "can" },
  { label: "Bag", value: "bag" },
  { label: "Meter", value: "m" },
  { label: "Centimeter", value: "cm" },
  { label: "Millimeter", value: "mm" },
  { label: "Rupee", value: "rupee" },
  { label: "Unit", value: "unit" },
];

export default function AddDishModal({ isOpen, onClose, editData, onSuccess }) {
  const [formData, setFormData] = useState(getInitialFormData());
  const [categories, setCategories] = useState([]);
  const [inventoryItems, setInventoryItems] = useState([]);
  const [preparedItems, setPreparedItems] = useState([]);
  const [openIngredientIndex, setOpenIngredientIndex] = useState(null);
  const ingredientsContainerRef = useRef(null);
  const hasPrefilledRef = useRef(false); // ✅ FIX 1: guard against double prefill
  const [openUnitIndex, setOpenUnitIndex] = useState(null);
  const [ingredientSearch, setIngredientSearch] = useState("");
  const [loadingIngredients, setLoadingIngredients] = useState(false);
  const [ingredients, setIngredients] = useState([newRow()]);
  const [batchesMap, setBatchesMap] = useState({});
  const [dropdownPosition, setDropdownPosition] = useState({
    top: 0,
    left: 0,
    width: 0,
  });

  /* ================= FETCH INVENTORY ================= */

  const fetchInventoryItems = async (search = "") => {
    try {
      setLoadingIngredients(true);
      const res = await api.get("/inventory/", {
        params: {
          page: 1,
          page_size: 20,
          search: search || undefined,
        },
      });
      setInventoryItems(res.data.data || res.data || []);
    } catch (err) {
      console.error("Failed to fetch inventory items", err);
    } finally {
      setLoadingIngredients(false);
    }
  };

  const fetchPreparedItems = async (search = "") => {
    try {
      setLoadingIngredients(true);
      const res = await api.get("/dish/semi-finished-ingredients", {
        params: {
          page: 1,
          page_size: 20,
          search: search || undefined,
        },
      });
      setPreparedItems(res.data.data || []);
    } catch (err) {
      console.error("Failed to fetch prepared items", err);
    } finally {
      setLoadingIngredients(false);
    }
  };

  /* ================= RESET ================= */

  // ✅ FIX 1: Reset prefill guard when modal closes
  useEffect(() => {
    if (!isOpen) {
      hasPrefilledRef.current = false;
      setFormData(getInitialFormData());
      setIngredients([newRow()]);
    }
  }, [isOpen]);

  useEffect(() => {
    const activeIndex =
      openIngredientIndex !== null
        ? openIngredientIndex
        : openUnitIndex !== null
          ? openUnitIndex
          : null;

    if (activeIndex !== null) {
      setTimeout(() => {
        const container = ingredientsContainerRef.current;
        const activeRow = container?.children[activeIndex];

        if (container && activeRow) {
          const rowBottom = activeRow.offsetTop + activeRow.offsetHeight;
          const containerBottom = container.scrollTop + container.clientHeight;

          if (rowBottom > containerBottom) {
            container.scrollTo({
              top: rowBottom - container.clientHeight + 20,
              behavior: "smooth",
            });
          }
        }
      }, 100);
    }
  }, [openIngredientIndex, openUnitIndex]);

  /* ================= PREFILL EDIT ================= */

  // ✅ FIX 1: Only prefill once using hasPrefilledRef guard
  useEffect(() => {
    if (!editData) return;
    if (!categories.length) return; // wait for categories to load
    if (!inventoryItems.length) return;
    if (hasPrefilledRef.current) return; // already prefilled, skip
    // console.log("PREFILL RUNNING", inventoryItems.length);
    hasPrefilledRef.current = true; // mark as done

    const categoryMatch = categories.find(
      (c) => c.name === editData.category_name,
    );

    setFormData({
      name: editData.name || "",
      categoryId: categoryMatch?.id || "",
      sellingPrice: editData.selling_price || "",
    });

    if (editData.ingredients && editData.ingredients.length > 0) {
      const mappedIngredients = editData.ingredients.map((ing) => {
        if (ing.item?.startsWith("inv-")) {
          const id = ing.item.replace("inv-", "");
          const inventoryMatch = inventoryItems.find(
            (inv) => String(inv.id) === String(id),
          );

          // console.log("FIXED COST VALUE", ing.fixed_cost_amount);
          // console.log("COST VALUE", ing.cost);
          // console.log("FULL ING OBJECT", ing);

          const isFixedCost =
            inventoryMatch?.is_fixed_cost ||
            Number(ing.fixed_cost_amount || 0) > 0;

          return newRow({
            item: `inv-${id}`,
            itemName: ing.name || "",
            qty: isFixedCost ? "" : ing.qty || "",
            unit: ing.unit || "",
            cost: isFixedCost ? "" : ing.cost_per_unit || "",
            fixedCost: isFixedCost
              ? String(ing.fixed_cost_amount || ing.cost || "")
              : "",
            isFixedCostItem: isFixedCost,
          });
        }

        if (ing.item?.startsWith("prep-")) {
          const id = ing.item.replace("prep-", "");
          const preparedMatch = preparedItems.find(
            (item) => String(item.semi_finished_id) === String(id),
          );
          if (preparedMatch) {
            return newRow({
              item: `prep-${preparedMatch.semi_finished_id}`,
              itemName: ing.name || "",
              qty: ing.qty || "",
              unit: ing.unit || "",
              cost: preparedMatch.unit_cost || "",
            });
          }
          // ID found in data but not yet loaded in preparedItems — still prefill with what we have
          return newRow({
            item: ing.item,
            itemName: ing.name || "",
            qty: ing.qty || "",
            unit: ing.unit || "",
            cost: ing.cost_per_unit || "",
          });
        }
        return newRow({
          qty: ing.qty || "",
          unit: ing.unit || "",
          cost: ing.cost || "",
        });
      });

      setIngredients(mappedIngredients.length ? mappedIngredients : [newRow()]);
    }
  }, [editData, categories, inventoryItems]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      const isDropdown = e.target.closest(".custom-dropdown");
      const isPortalDropdown = e.target.closest(".portal-dropdown");

      if (!isDropdown && !isPortalDropdown) {
        setOpenIngredientIndex(null);
        setOpenUnitIndex(null);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  /* ================= FETCH DATA ================= */

  useEffect(() => {
    if (isOpen) {
      fetchCategories();
      fetchInventoryItems();
      fetchPreparedItems();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || openIngredientIndex === null) return;

    const delayDebounce = setTimeout(() => {
      fetchInventoryItems(ingredientSearch);
      fetchPreparedItems(ingredientSearch);
    }, 400);

    return () => clearTimeout(delayDebounce);
  }, [ingredientSearch, isOpen, openIngredientIndex]);

  const fetchCategories = async () => {
    try {
      const res = await api.get("/dish/get_dish_types");
      setCategories(res.data.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  /* ================= FORM CHANGE ================= */

  const handleChange = (e) => {
    const { name, value } = e.target;

    if (value !== "" && Number(value) < 0) {
      toast.error("Negative values not allowed ❌");
      return;
    }

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  /* ================= ADD INGREDIENT ================= */

  const addIngredientRow = () => {
    setIngredients((prev) => [...prev, newRow()]);

    setTimeout(() => {
      if (ingredientsContainerRef.current) {
        ingredientsContainerRef.current.scrollTo({
          top: ingredientsContainerRef.current.scrollHeight,
          behavior: "smooth",
        });
      }
    }, 100);
  };

  /* ================= REMOVE INGREDIENT ================= */

  const removeIngredientRow = (rowId) => {
    setIngredients((prev) => prev.filter((item) => item.rowId !== rowId));
  };

  /* ================= UPDATE INGREDIENT ================= */

  // ✅ FIX 2: All setIngredients use functional updates to prevent stale closure duplicates
  const updateIngredient = async (rowId, field, value) => {
    // 1. Apply simple field change immediately
    setIngredients((prev) =>
      prev.map((item) => {
        if (item.rowId !== rowId) return item;
        const updatedItem = { ...item, [field]: value };

        if (field === "item") {
          let selected = null;
          if (value.startsWith("inv-")) {
            const id = value.replace("inv-", "");
            selected = inventoryItems.find(
              (inv) => String(inv.id) === String(id),
            );
          }
          if (value.startsWith("prep-")) {
            const id = value.replace("prep-", "");
            selected = preparedItems.find(
              (p) => String(p.semi_finished_id) === String(id),
            );
          }
          updatedItem.itemName = selected?.name || "";
          updatedItem.unit = "";
          updatedItem.cost = "";
          updatedItem.isCustomItem = false;
          updatedItem.customItemType = "";
        }

        if (field === "itemName") {
          const typedValue = value.trim();

          const inventoryMatch = inventoryItems.find(
            (item) =>
              item.name?.toLowerCase().trim() === typedValue.toLowerCase(),
          );

          const preparedMatch = preparedItems.find(
            (item) =>
              item.name?.toLowerCase().trim() === typedValue.toLowerCase(),
          );

          if (typedValue && !inventoryMatch && !preparedMatch) {
            updatedItem.isCustomItem = true;
          } else {
            updatedItem.isCustomItem = false;
            updatedItem.customItemType = "";
          }
        }

        return updatedItem;
      }),
    );

    // 2. INV — fetch batches and compute cost
    if (field === "item" && value?.startsWith("inv-")) {
      const id = value.replace("inv-", "");
      try {
        const res = await api.get(`/inventory/items/${id}/batches`);
        const batches = res.data.data || res.data || [];
        setBatchesMap((prev) => ({ ...prev, [id]: batches }));

        setIngredients((prev) =>
          prev.map((item) => {
            if (item.rowId !== rowId) return item;

            const selectedItem = inventoryItems.find(
              (inv) => String(inv.id) === String(id),
            );
            if (!selectedItem) return item;

            const isFixedCost = selectedItem.is_fixed_cost || false;
            if (isFixedCost) {
              return {
                ...item,
                isFixedCostItem: true,
                qty: 0,
                cost: 0,
                fixedCost: "",
              };
            }

            // don't compute cost yet if unit not selected
            if (!item.unit) return { ...item, isFixedCostItem: false };

            let costPerUnit =
              batches.length > 0
                ? calculateWeightedAvg(batches)
                : selectedItem.price_per_unit ||
                  selectedItem.cost_per_unit ||
                  0;

            const inventoryUnit = selectedItem.unit;
            const dishUnit = item.unit;
            const inventoryCategory = getUnitCategory(inventoryUnit);
            const dishCategory = getUnitCategory(dishUnit);

            if (inventoryCategory !== dishCategory) return item;

            costPerUnit = convertCost(inventoryUnit, dishUnit, costPerUnit);
            return {
              ...item,
              isFixedCostItem: false,
              cost: Number(costPerUnit.toFixed(3)),
            };
          }),
        );
      } catch (err) {
        console.error("Batch fetch failed", err);
      }
    }

    // 3. PREP — compute cost directly (no API call needed)
    if (field === "item" && value?.startsWith("prep-")) {
      const id = value.replace("prep-", "");
      const selectedItem = preparedItems.find(
        (p) => String(p.semi_finished_id) === String(id),
      );

      if (selectedItem) {
        setIngredients((prev) =>
          prev.map((item) => {
            if (item.rowId !== rowId) return item;

            if (!item.unit) return item; // wait for unit selection

            let costPerUnit = selectedItem.unit_cost || 0;
            const inventoryUnit = selectedItem.unit || selectedItem.yield_unit;
            const dishUnit = item.unit;
            const inventoryCategory = getUnitCategory(inventoryUnit);
            const dishCategory = getUnitCategory(dishUnit);

            if (inventoryCategory !== dishCategory) {
              toast.error(
                `Invalid unit conversion: ${inventoryUnit} → ${dishUnit}`,
              );
              return { ...item, unit: "", cost: "" };
            }

            costPerUnit = convertCost(inventoryUnit, dishUnit, costPerUnit);
            return { ...item, cost: Number(costPerUnit.toFixed(4)) };
          }),
        );
      }
    }

    // 4. UNIT change — recompute cost for both inv and prep
    if (field === "unit") {
      setIngredients((prev) =>
        prev.map((item) => {
          if (item.rowId !== rowId) return item;

          const itemValue = item.item;

          // INV
          if (itemValue?.startsWith("inv-")) {
            const id = itemValue.replace("inv-", "");
            const selectedItem = inventoryItems.find(
              (inv) => String(inv.id) === String(id),
            );
            if (!selectedItem) return { ...item, unit: value };

            const batches = batchesMap[id] || [];
            let costPerUnit =
              batches.length > 0
                ? calculateWeightedAvg(batches)
                : selectedItem.price_per_unit ||
                  selectedItem.cost_per_unit ||
                  0;

            const inventoryUnit = selectedItem.unit;
            const inventoryCategory = getUnitCategory(inventoryUnit);
            const dishCategory = getUnitCategory(value);

            if (inventoryUnit === "rupee" || value === "rupee") {
              if (inventoryUnit !== value) {
                toast.error("Rupee unit must match exactly ❌");
                return { ...item, unit: "", cost: "" };
              }
            } else if (inventoryCategory !== dishCategory) {
              toast.error(
                `Invalid unit conversion: ${inventoryUnit} → ${value}`,
              );
              return { ...item, unit: "", cost: "" };
            }

            if (value === "pcs" && inventoryUnit === "packet") {
              let totalPieces = 0;
              let totalCost = 0;

              batches.forEach((b) => {
                const qtyRemaining = Number(b.quantity_remaining || 0);
                const qtyReceived = Number(b.quantity_received || 0);
                const batchTotalCost = Number(b.total_cost || 0);
                const pieces = Number(b.pieces || 1);

                let remainingCost = 0;

                if (qtyReceived > 0) {
                  remainingCost = (qtyRemaining / qtyReceived) * batchTotalCost;
                }

                totalPieces += qtyRemaining * pieces;
                totalCost += remainingCost;
              });

              costPerUnit = totalPieces > 0 ? totalCost / totalPieces : 0;
            } else {
              costPerUnit = convertCost(inventoryUnit, value, costPerUnit);
            }
            return {
              ...item,
              unit: value,
              cost: Number(costPerUnit.toFixed(3)),
            };
          }

          // PREP
          if (itemValue?.startsWith("prep-")) {
            const id = itemValue.replace("prep-", "");
            const selectedItem = preparedItems.find(
              (p) => String(p.semi_finished_id) === String(id),
            );
            if (!selectedItem) return { ...item, unit: value };

            let costPerUnit = selectedItem.unit_cost || 0;
            const inventoryUnit = selectedItem.unit || selectedItem.yield_unit;
            const inventoryCategory = getUnitCategory(inventoryUnit);
            const dishCategory = getUnitCategory(value);

            if (inventoryUnit === "rupee" || value === "rupee") {
              if (inventoryUnit !== value) {
                toast.error("Rupee unit must match exactly ❌");
                return { ...item, unit: "", cost: "" };
              }
            } else if (inventoryCategory !== dishCategory) {
              toast.error(
                `Invalid unit conversion: ${inventoryUnit} → ${value}`,
              );

              return { ...item, unit: "", cost: "" };
            }

            costPerUnit = convertCost(inventoryUnit, value, costPerUnit);
            return {
              ...item,
              unit: value,
              cost: Number(costPerUnit.toFixed(4)),
            };
          }

          return { ...item, unit: value };
        }),
      );
    }
  };

  /* ================= SUBMIT ================= */

  const handleSubmit = async (e) => {
    e.preventDefault();

    const formattedName =
      formData.name.charAt(0).toUpperCase() +
      formData.name.slice(1).toLowerCase();

    if (Number(formData.sellingPrice || 0) < 0) {
      toast.error("Selling price cannot be negative ❌");
      return;
    }

    for (const ing of ingredients) {
      // Ingredient selected but unit not selected
      if (ing.item && !ing.unit) {
        toast.error(`Please select unit for ${ing.itemName} ❌`);
        return;
      }

      if (ing.isCustomItem && !ing.customItemType) {
        toast.error(`Please select type for ${ing.itemName}`);
        return;
      }
    }

    for (let ing of ingredients) {
      if (Number(ing.qty || 0) < 0 || Number(ing.cost || 0) < 0) {
        toast.error("Negative values in ingredients not allowed ❌");
        return;
      }
    }

    const payload = {
      dish_name: formattedName,
      type_id: Number(formData.categoryId),
      selling_price: Number(formData.sellingPrice),
      raw_ingredients: [],
      semi_finished_ingredients: [],
    };

    // Deduplicate: keep only the last row per ingredient item key
    const seenItems = new Map();
    ingredients.forEach((ing) => {
      const key = ing.isCustomItem ? `custom-${ing.itemName}` : ing.item;

      if (!key) return;

      seenItems.set(key, ing);
    });
    const dedupedIngredients = Array.from(seenItems.values());

    dedupedIngredients
      .filter((ing) => {
        // Custom item
        if (ing.isCustomItem) {
          return ing.itemName && ing.customItemType && ing.qty && ing.unit;
        }

        // Existing item
        if (!ing.item) return false;

        if (ing.isFixedCostItem) {
          return ing.fixedCost && Number(ing.fixedCost) > 0;
        }

        return ing.qty && ing.unit;
      })
      .forEach((ing) => {
        if (ing.isCustomItem) {
          if (ing.customItemType === "raw") {
            payload.raw_ingredients.push({
              ingredient_name: ing.itemName,
              quantity_required: Number(ing.qty),
              unit: ing.unit,
            });
          }

          if (ing.customItemType === "semi_finished") {
            payload.semi_finished_ingredients.push({
              semi_finished_name: ing.itemName,
              quantity_required: Number(ing.qty),
              unit: ing.unit,
            });
          }

          return;
        }
        if (String(ing.item).startsWith("inv-")) {
          payload.raw_ingredients.push({
            ...(editData && { id: ing.id }),
            ingredient_id: Number(ing.item.replace("inv-", "")),
            unit: ing.unit,
            quantity_required: ing.isFixedCostItem ? 0 : Number(ing.qty),
            cost_per_unit: ing.isFixedCostItem ? 0 : Number(ing.cost),
            fixed_cost_amount: ing.isFixedCostItem
              ? Number(ing.fixedCost || 0)
              : 0,
          });
        }

        if (String(ing.item).startsWith("prep-")) {
          payload.semi_finished_ingredients.push({
            ...(editData && { id: ing.id }),
            semi_finished_id: Number(ing.item.replace("prep-", "")),
            quantity_required: Number(ing.qty),
            unit: ing.unit,
            cost_per_unit: Number(ing.cost),
          });
        }
      });

    if (
      payload.raw_ingredients.length === 0 &&
      payload.semi_finished_ingredients.length === 0
    ) {
      toast.error("Please add at least one ingredient");
      return;
    }

    try {
      for (let ing of ingredients) {
        if (ing.isFixedCostItem && !ing.fixedCost) {
          toast.error("Please enter fixed cost amount ❌");
          return;
        }
      }
      // console.log(
      //   "FINAL PAYLOAD",
      //   JSON.stringify(payload, null, 2)
      // );
      if (editData) {
        await api.put(
          `/dish/update-dishes-with-ingredients/${editData.id}`,
          payload,
        );
        toast.success("Dish updated successfully");
      } else {
        await api.post("/dish/add-ingredients-to-dish", payload);
        toast.success("Dish added successfully");
      }

      onSuccess();
      onClose();
    } catch (err) {
      console.error(err);
      toast.error("Failed to save dish");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

      {/* Modal */}
      <div
        className="relative w-full max-w-4xl bg-white dark:bg-[#0f172a] rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {editData ? `Edit ${editData.name || "Dish"}` : "Add Dish"}
          </h2>

          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            <FiX className="text-xl text-gray-700 dark:text-gray-200" />
          </button>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          className="px-6 py-6 space-y-6 max-h-[60vh] overflow-y-auto"
        >
          {/* Dish Name + Category */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Dish Name
              </label>
              <input
                name="name"
                value={formData.name}
                onChange={handleChange}
                placeholder="Enter dish name"
                className="mt-2 w-full px-4 py-2 rounded-xl border border-gray-300
                dark:border-gray-700 bg-white dark:bg-[#0b1220]
                text-gray-800 dark:text-gray-200
                focus:ring-2 focus:ring-orange-400 outline-none"
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Category
              </label>
              <select
                name="categoryId"
                value={formData.categoryId}
                onChange={handleChange}
                className="mt-2 w-full px-4 py-2 rounded-xl border border-gray-300
                dark:border-gray-700 bg-white dark:bg-[#0b1220]
                text-gray-800 dark:text-gray-200
                focus:ring-2 focus:ring-orange-400 outline-none"
                required
              >
                <option value="">Select category</option>
                {categories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Price */}
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Selling Price
            </label>
            <input
              type="number"
              name="sellingPrice"
              value={formData.sellingPrice}
              min="0"
              onKeyDown={(e) => {
                if (e.key === "-" || e.key === "e") e.preventDefault();
              }}
              onChange={handleChange}
              placeholder="Enter price"
              className="mt-2 w-full px-4 py-2 rounded-xl border border-gray-300
              dark:border-gray-700 bg-white dark:bg-[#0b1220]
              text-gray-800 dark:text-gray-200
              focus:ring-2 focus:ring-orange-400 outline-none"
            />
          </div>

          {/* Ingredients */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Ingredients{" "}
                <span className="text-gray-400">(From Inventory)</span>
              </label>

              <button
                type="button"
                onClick={addIngredientRow}
                className="flex items-center gap-1 px-3 py-1 rounded-full
                bg-gray-200 dark:bg-gray-700 text-sm dark:text-white
                hover:bg-gray-300 dark:hover:bg-gray-600 transition"
              >
                <FiPlus /> Add
              </button>
            </div>

            <div
              ref={ingredientsContainerRef}
              className="max-h-[250px] overflow-y-auto pr-2 relative"
            >
              {ingredients.map((row, index) => {
                // console.log("ROW DATA", row);
                let selectedItem = null;
                let selectedUnit = null;

                if (row.item?.startsWith("inv-")) {
                  selectedItem = inventoryItems.find(
                    (inv) => `inv-${inv.id}` === row.item,
                  );
                  selectedUnit = selectedItem?.unit || selectedItem?.yield_unit;
                } else if (row.item?.startsWith("prep-")) {
                  selectedItem = preparedItems.find(
                    (p) => `prep-${p.semi_finished_id}` === row.item,
                  );
                  selectedUnit = selectedItem?.unit || selectedItem?.yield_unit;
                }

                const allowedCategory = getUnitCategory(selectedUnit);
                const filteredUnits = allowedCategory
                  ? UNIT_OPTIONS.filter(
                      (u) => getUnitCategory(u.value) === allowedCategory,
                    )
                  : UNIT_OPTIONS;

                return (
                  <div key={index} className="mb-3">
                    <div className="grid grid-cols-[170px_180px_160px_140px_120px_50px] gap-3 items-center">
                      {/* Ingredient */}
                      <div className="relative custom-dropdown">
                        <div
                          onClick={(e) => {
                            const rect =
                              e.currentTarget.getBoundingClientRect();
                            const spaceBelow = window.innerHeight - rect.bottom;
                            const dropdownHeight = 240;
                            const openUp = spaceBelow < dropdownHeight;

                            setDropdownPosition({
                              top: openUp
                                ? rect.top + window.scrollY - dropdownHeight
                                : rect.bottom + window.scrollY,
                              left: rect.left + window.scrollX,
                              width: rect.width,
                            });

                            setOpenUnitIndex(null);
                            setIngredientSearch("");
                            setOpenIngredientIndex(index);
                          }}
                          className="px-3 py-2 rounded-xl border border-gray-300
                        dark:border-gray-700 bg-white dark:bg-[#0b1220]
                        text-gray-800 dark:text-gray-200
                        cursor-pointer flex items-center justify-between"
                        >
                          <span>{row.itemName || "Select Item"}</span>

                          <FiChevronDown
                            className={`transition-transform ${
                              openIngredientIndex === index ? "rotate-180" : ""
                            }`}
                          />
                        </div>

                        {openIngredientIndex === index &&
                          createPortal(
                            <div
                              className="portal-dropdown fixed max-h-60 overflow-y-auto
                            bg-white dark:bg-[#020617]
                            border border-gray-200 dark:border-gray-700
                            rounded-xl shadow-2xl z-[9999]"
                              style={{
                                top: dropdownPosition.top,
                                left: dropdownPosition.left,
                                width: dropdownPosition.width,
                              }}
                            >
                              <div className="p-2">
                                <input
                                  type="text"
                                  placeholder="Search item..."
                                  value={ingredientSearch}
                                  onChange={(e) => {
                                    const value = e.target.value;

                                    setIngredientSearch(value);

                                    const inventoryMatch = inventoryItems.find(
                                      (item) =>
                                        item.name?.toLowerCase().trim() ===
                                        value.toLowerCase().trim(),
                                    );

                                    const preparedMatch = preparedItems.find(
                                      (item) =>
                                        item.name?.toLowerCase().trim() ===
                                        value.toLowerCase().trim(),
                                    );

                                    if (
                                      value.trim() &&
                                      !inventoryMatch &&
                                      !preparedMatch
                                    ) {
                                      updateIngredient(
                                        row.rowId,
                                        "itemName",
                                        value.trim(),
                                      );
                                    }
                                  }}
                                  className="w-full px-2 py-1 text-sm rounded-md border border-gray-300
                                dark:border-gray-700 bg-white dark:bg-[#020617]
                                text-gray-800 dark:text-gray-200 outline-none"
                                />
                              </div>

                              <div className="px-3 py-1 text-xs text-gray-400">
                                Inventory Items
                              </div>

                              {inventoryItems.map((item) => (
                                <div
                                  key={`inv-${item.id}`}
                                  onClick={() => {
                                    updateIngredient(
                                      row.rowId,
                                      "item",
                                      `inv-${item.id}`,
                                    );
                                    setOpenIngredientIndex(null);
                                    setIngredientSearch("");
                                  }}
                                  className="px-3 py-2 text-sm text-gray-800 dark:text-gray-200 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                                >
                                  {item.name}
                                </div>
                              ))}

                              <div className="px-3 py-1 text-xs text-gray-400 border-t dark:border-gray-700">
                                Prepared Items
                              </div>

                              {preparedItems.map((item) => (
                                <div
                                  key={`prep-${item.semi_finished_id}`}
                                  onClick={() => {
                                    updateIngredient(
                                      row.rowId,
                                      "item",
                                      `prep-${item.semi_finished_id}`,
                                    );
                                    setOpenIngredientIndex(null);
                                    setIngredientSearch("");
                                  }}
                                  className="px-3 py-2 text-sm text-gray-800 dark:text-gray-200 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                                >
                                  {item.name}
                                </div>
                              ))}
                            </div>,
                            document.body,
                          )}
                      </div>
                      {row.isCustomItem && (
                        <select
                          value={row.customItemType}
                          onChange={(e) =>
                            updateIngredient(
                              row.rowId,
                              "customItemType",
                              e.target.value,
                            )
                          }
                          className="px-3 py-2 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#0b1220]"
                        >
                          <option value="">Select Item Type</option>
                          <option value="raw">Raw Ingredient</option>
                          <option value="semi_finished">
                            Semi Finished Item
                          </option>
                        </select>
                      )}

                      {/* Qty */}
                      <input
                        type="number"
                        placeholder="Qty"
                        value={row.isFixedCostItem ? 0 : row.qty}
                        disabled={row.isFixedCostItem}
                        min="0.001"
                        step="any"
                        onKeyDown={(e) => {
                          if (e.key === "-" || e.key === "e" || e.key === "E") {
                            e.preventDefault();
                          }
                        }}
                        onChange={(e) => {
                          const value = e.target.value;

                          if (value === "") {
                            updateIngredient(row.rowId, "qty", "");
                            return;
                          }

                          if (Number(value) > 0) {
                            updateIngredient(row.rowId, "qty", value);
                          }
                        }}
                        className={`px-3 py-2 rounded-xl border
    ${
      row.isFixedCostItem
        ? "bg-gray-100 cursor-not-allowed"
        : "bg-white dark:bg-[#0b1220]"
    }
    border-gray-300 dark:border-gray-700 dark:placeholder:text-gray-500`}
                      />

                      {/* Unit */}
                      <div className="relative custom-dropdown">
                        <div
                          onClick={(e) => {
                            const rect =
                              e.currentTarget.getBoundingClientRect();
                            const spaceBelow = window.innerHeight - rect.bottom;
                            const dropdownHeight = 240;
                            const openUp = spaceBelow < dropdownHeight;

                            setDropdownPosition({
                              top: openUp
                                ? rect.top + window.scrollY - dropdownHeight
                                : rect.bottom + window.scrollY,
                              left: rect.left + window.scrollX,
                              width: rect.width,
                            });

                            setOpenIngredientIndex(null);
                            setOpenUnitIndex(
                              openUnitIndex === index ? null : index,
                            );
                          }}
                          className="px-3 py-2 rounded-xl border border-gray-300
                        dark:border-gray-700 bg-white dark:bg-[#0b1220]
                        text-gray-800 dark:text-gray-200
                        cursor-pointer flex items-center justify-between"
                        >
                          <span>
                            {(() => {
                              const selected = UNIT_OPTIONS.find(
                                (u) => u.value === row.unit,
                              );
                              return selected
                                ? `${selected.label} (${selected.value})`
                                : "Select Unit";
                            })()}
                          </span>
                          <FiChevronDown
                            className={`transition-transform ${
                              openUnitIndex === index ? "rotate-180" : ""
                            }`}
                          />
                        </div>

                        {openUnitIndex === index &&
                          createPortal(
                            <div
                              className="portal-dropdown fixed max-h-60 overflow-y-auto
                            bg-white dark:bg-[#020617]
                            border border-gray-200 dark:border-gray-700
                            rounded-xl shadow-2xl z-[9999]"
                              style={{
                                top: dropdownPosition.top,
                                left: dropdownPosition.left,
                                width: dropdownPosition.width,
                              }}
                            >
                              {(() => {
                                let selectedUnit = null;

                                if (row.item?.startsWith("inv-")) {
                                  const item = inventoryItems.find(
                                    (inv) => `inv-${inv.id}` === row.item,
                                  );
                                  selectedUnit = item?.unit || item?.yield_unit;
                                } else if (row.item?.startsWith("prep-")) {
                                  const item = preparedItems.find(
                                    (p) =>
                                      `prep-${p.semi_finished_id}` === row.item,
                                  );
                                  selectedUnit = item?.unit || item?.yield_unit;
                                }

                                const allowedCategory = getUnitCategory(
                                  selectedUnit || row.unit,
                                );
                                if (row.isCustomItem) {
                                  return UNIT_OPTIONS.map((unit) => (
                                    <div
                                      key={unit.value}
                                      onClick={() => {
                                        updateIngredient(
                                          row.rowId,
                                          "unit",
                                          unit.value,
                                        );
                                        setOpenUnitIndex(null);
                                      }}
                                      className={`px-3 py-2 text-sm cursor-pointer ${
                                        row.unit === unit.value
                                          ? "bg-orange-500 text-white"
                                          : "hover:bg-gray-100 dark:hover:bg-gray-800"
                                      }`}
                                    >
                                      {unit.label} ({unit.value})
                                    </div>
                                  ));
                                }

                                const filteredUnits = UNIT_OPTIONS.filter(
                                  (u) =>
                                    getUnitCategory(u.value) ===
                                    allowedCategory,
                                );

                                return filteredUnits.map((unit) => (
                                  <div
                                    key={unit.value}
                                    onClick={() => {
                                      updateIngredient(
                                        row.rowId,
                                        "unit",
                                        unit.value,
                                      );
                                      setOpenUnitIndex(null);
                                    }}
                                    className={`px-3 py-2 text-sm text-gray-800 dark:text-gray-200 cursor-pointer
                                  ${
                                    row.unit === unit.value
                                      ? "bg-orange-500 text-white"
                                      : "hover:bg-gray-100 dark:hover:bg-gray-800"
                                  }`}
                                  >
                                    {unit.label} ({unit.value})
                                  </div>
                                ));
                              })()}
                            </div>,
                            document.body,
                          )}
                      </div>

                      {/* COST */}
                      {row.isFixedCostItem ? (
                        <input
                          type="number"
                          min="0.001"
                          step="any"
                          placeholder="Fixed Cost"
                          value={row.fixedCost}
                          onKeyDown={(e) => {
                            if (
                              e.key === "-" ||
                              e.key === "e" ||
                              e.key === "E"
                            ) {
                              e.preventDefault();
                            }
                          }}
                          onChange={(e) => {
                            const value = e.target.value;

                            if (value === "") {
                              updateIngredient(row.rowId, "fixedCost", "");
                              return;
                            }

                            if (Number(value) > 0) {
                              updateIngredient(row.rowId, "fixedCost", value);
                            }
                          }}
                          className="px-3 py-2 rounded-xl border border-gray-300
  dark:border-gray-700 bg-white dark:bg-[#0b1220]
  text-gray-800 dark:text-gray-200
  focus:ring-2 focus:ring-orange-400 outline-none"
                        />
                      ) : (
                        <input
                          type="number"
                          placeholder="Cost/unit"
                          value={row.cost}
                          readOnly
                          className="px-3 py-2 rounded-xl border border-gray-300
                        dark:border-gray-700 bg-gray-100 dark:bg-[#020617]
                        text-gray-500 cursor-not-allowed outline-none"
                        />
                      )}

                      {/* Delete */}
                      <button
                        type="button"
                        onClick={() => removeIngredientRow(row.rowId)}
                        className="flex justify-center items-center p-2
                      rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20"
                      >
                        <FiTrash2 className="text-red-600 text-lg" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Submit */}
          <button
            type="submit"
            className="w-full py-3 rounded-xl bg-orange-500
            hover:bg-orange-600 text-white font-semibold transition"
          >
            {editData ? "Update Dish" : "Add Dish"}
          </button>
        </form>
      </div>
    </div>
  );
}
