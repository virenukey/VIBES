import React, { useState, useEffect, useRef } from "react";
import { X } from "lucide-react";
import api from "../../api/axios";
import { toast } from "react-toastify";
import { createPortal } from "react-dom";

// ================= UNIT CATEGORY =================
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

// ================= COMMON CONVERSION =================
const convertCost = (baseUnit, targetUnit, baseCost) => {
  let cost = baseCost;

  if (baseUnit === "kg" && targetUnit === "gm") cost /= 1000;
  if (baseUnit === "gm" && targetUnit === "kg") cost *= 1000;

  if (baseUnit === "liter" && targetUnit === "ml") cost /= 1000;
  if (baseUnit === "ml" && targetUnit === "liter") cost *= 1000;

  if (baseUnit === "m" && targetUnit === "cm") cost /= 100;
  if (baseUnit === "cm" && targetUnit === "m") cost *= 100;

  if (baseUnit === "m" && targetUnit === "mm") cost /= 1000;
  if (baseUnit === "mm" && targetUnit === "m") cost *= 1000;

  return cost;
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

const AddPreparedItemModal = ({ onClose, onSuccess, editData }) => {
  const modalRef = useRef();

  const [inventory, setInventory] = useState([]);
  const [preparedItems, setPreparedItems] = useState([]);
  const [initialDataLoaded, setInitialDataLoaded] = useState(false);
  const [loadingIngredients, setLoadingIngredients] = useState(false);
  const [activeDropdown, setActiveDropdown] = useState(null);
  const [openMainUnit, setOpenMainUnit] = useState(false);
  const [openUnitIndex, setOpenUnitIndex] = useState(null);
  const ingredientsContainerRef = useRef(null);

  const [batchesMap, setBatchesMap] = useState({});
  const [form, setForm] = useState({
    name: "",
    quantity: "",
    unit: "",
    ingredients: [
      {
        ingredient_id: "",
        ingredient_name: "",
        quantity_required: "",
        unit: "",
        search: "",
        cost: "",
        fixedCost: "",
        isFixedCostItem: false,
        isCustomItem: false,
      },
    ],
  });

  const [dropdownPosition, setDropdownPosition] = useState({
    top: 0,
    left: 0,
    width: 0,
  });

  const fetchInventory = async (search = "") => {
    try {
      setLoadingIngredients(true);

      const res = await api.get("/inventory/", {
        params: {
          page: 1,
          page_size: 20,
          search: search || undefined,
        },
      });

      setInventory(res.data.data || []);
    } catch (err) {
      console.error(err);
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
      console.error(err);
    } finally {
      setLoadingIngredients(false);
    }
  };

  useEffect(() => {
    const loadInitialData = async () => {
      await Promise.all([fetchInventory(), fetchPreparedItems()]);

      setInitialDataLoaded(true);
    };

    loadInitialData();
  }, []);

  useEffect(() => {
    if (activeDropdown === null) return;

    const currentSearch = form.ingredients[activeDropdown]?.search || "";

    const delayDebounce = setTimeout(() => {
      fetchInventory(currentSearch);
      fetchPreparedItems(currentSearch);
    }, 400);

    return () => clearTimeout(delayDebounce);
  }, [form.ingredients, activeDropdown]);

  useEffect(() => {
    if (!editData || !initialDataLoaded) return;

    const loadEditData = async () => {
      const updatedIngredients = await Promise.all(
        editData.ingredients.map(async (ing) => {
          let selectedItem = null;

          if (ing.is_semi_finished) {
            const preparedId = ing.semi_finished_id || ing.ingredient_id;

            selectedItem = preparedItems.find(
              (item) => Number(item.semi_finished_id) === Number(preparedId),
            );
          } else {
            selectedItem = inventory.find(
              (inv) => Number(inv.id) === Number(ing.ingredient_id),
            );

            if (!selectedItem) {
              try {
                const res = await api.get(`/inventory/${ing.ingredient_id}`);
                /// console.log("FULL INVENTORY ITEM:", res.data?.data || res.data);

                selectedItem = res.data?.data || res.data;
              } catch (err) {
                console.error("Failed to fetch inventory item", err);
              }
            }
          }
          console.log(
  "SELECTED INVENTORY ITEM",
  selectedItem?.name,
  selectedItem?.unit,
  selectedItem
);
          let costPerUnit = ing.cost_per_unit || 0;
          let batches = [];

          //  fetch batches for each ingredient
          try {
            const res = await api.get(
              `/inventory/items/${ing.ingredient_id}/batches`,
            );

            batches = res.data.data || res.data || [];
            console.log(
  "BATCH UNIT",
  ing.ingredient_name,
  batches[0]?.unit
);

            // store in map
            setBatchesMap((prev) => ({
              ...prev,
              [`inv-${ing.ingredient_id}`]: batches,
            }));

            //  calculate weighted avg
            if (batches.length > 0) {
              costPerUnit = calculateWeightedAvg(batches);
            }
          } catch (err) {
            console.error("Batch fetch failed (edit)", err);
          }

          const rawCostPerUnit = costPerUnit;

          // unit conversion only for display
          if (selectedItem && ing.unit) {
            console.log("======== OIL DEBUG ========");
// console.log("INGREDIENT", ing.ingredient_name);
// console.log("ING UNIT", ing.unit);
// console.log("SELECTED ITEM UNIT", selectedItem?.unit);
// console.log("API COST PER UNIT", ing.cost_per_unit);
// console.log("WEIGHTED AVG BEFORE CONVERSION", costPerUnit);
            const inventoryUnit =
  batches?.[0]?.unit || selectedItem.unit;
            const selectedUnit = ing.unit;

            //  packet -> pcs conversion during edit load
            if (
              inventoryUnit === "packet" &&
              selectedUnit === "pcs" &&
              batches.length > 0
            ) {
              const totalPieces = batches.reduce(
                (sum, b) => sum + Number(b.pieces || 0),
                0,
              );

              const totalPacketCost = batches.reduce(
                (sum, b) => sum + Number(b.total_cost || 0),
                0,
              );

              costPerUnit =
                totalPieces > 0 ? totalPacketCost / totalPieces : costPerUnit;
            }

            // NORMAL CONVERSIONS
            else if (inventoryUnit !== "rupee" && selectedUnit !== "rupee") {
              costPerUnit = convertCost(
                inventoryUnit,
                selectedUnit,
                costPerUnit,
              );
              console.log("AFTER CONVERSION", costPerUnit);
            }
          }
          //   console.log("EDIT INGREDIENT:", ing);
          // console.log("EDIT ING", ing);
          // console.log("SELECTED ITEM", selectedItem);
          // console.log("IS FIXED COST", selectedItem?.is_fixed_cost);
          const isFixedCost =
            selectedItem?.is_fixed_cost === true ||
            Number(ing.fixed_cost_amount || 0) > 0;

          return {
            ingredient_id: ing.is_semi_finished
              ? `prep-${ing.semi_finished_id || ing.ingredient_id}`
              : `inv-${ing.ingredient_id}`,

            ingredient_name: ing.ingredient_name || "",

            quantity_required: isFixedCost ? 0 : ing.quantity_required,

            unit: ing.unit,

            search: ing.ingredient_name,

            cost: isFixedCost ? 0 : Number(costPerUnit.toFixed(5)),

            fixedCost: isFixedCost
              ? String(ing.fixed_cost_amount || ing.line_cost || ing.cost || "")
              : "",

            isFixedCostItem: isFixedCost,

            isCustomItem: false,

            baseUnit: ing.is_semi_finished
              ? selectedItem?.yield_unit || selectedItem?.unit
              : selectedItem?.unit,

            originalCostPerUnit: rawCostPerUnit,
          };
        }),
      );

      setForm({
        name: editData.name,
        quantity: editData.yield_quantity,
        unit: editData.yield_unit,
        ingredients: updatedIngredients,
      });
    };

    loadEditData();
  }, [editData, initialDataLoaded]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (
        !e.target.closest(".custom-dropdown") &&
        !e.target.closest(".ingredient-search") &&
        !e.target.closest(".portal-dropdown")
      ) {
        setOpenMainUnit(false);
        setOpenUnitIndex(null);
        setActiveDropdown(null);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // ================= HANDLERS =================
  const handleChange = (e) => {
    const { name, value } = e.target;

    if (value !== "" && Number(value) < 0) {
      toast.error("Negative values not allowed ❌");
      return;
    }

    setForm({ ...form, [name]: value });
  };

  const calculateWeightedAvg = (batches = []) => {
    let totalQty = 0;
    let totalCost = 0;

    batches.forEach((b) => {
      console.log("BATCH", b);
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
  const handleIngredientChange = async (
    index,
    field,
    value,
    skipCustomCheck = false,
  ) => {
    const updated = [...form.ingredients];
    updated[index][field] = value;

    // CUSTOM ITEM DETECTION (ONLY IN EDIT MODE)
    // CUSTOM ITEM DETECTION
    if (field === "search" && !skipCustomCheck) {
      const typedValue = value.trim();

      const inventoryMatch = inventory.find(
        (item) => item.name?.toLowerCase().trim() === typedValue.toLowerCase(),
      );

      if (!inventoryMatch && typedValue) {
        updated[index].ingredient_id = "";
        updated[index].ingredient_name = typedValue;
        updated[index].isCustomItem = true;
        updated[index].cost = 0;
      } else {
        updated[index].isCustomItem = false;
      }
    }

    if (field === "ingredient_id" || field === "unit") {
      //console.log("========== UNIT CHANGE DEBUG ==========");
      // console.log("FIELD:", field);
      // console.log("VALUE:", value);
      //console.log("UPDATED ROW:", updated[index]);
      if (
        field === "ingredient_id" &&
        value &&
        String(value).startsWith("inv-")
      ) {
        try {
          const inventoryId = value.replace("inv-", "");

          const res = await api.get(`/inventory/items/${inventoryId}/batches`);

          const batches = res.data.data || res.data || [];

          //  update state
          setBatchesMap((prev) => ({
            ...prev,
            [value]: batches,
          }));

          updated[index].__tempBatches = batches;
        } catch (err) {
          console.error("Batch fetch failed", err);
        }
      }

      let selectedItem = null;
      //console.log("INGREDIENT VALUE:", updated[index].ingredient_id);
      let isPreparedItem = false;

      const ingredientValue = updated[index].ingredient_id;

      if (String(ingredientValue).startsWith("inv-")) {
        const id = ingredientValue.replace("inv-", "");

        selectedItem = inventory.find((inv) => String(inv.id) === String(id));
      } else if (String(ingredientValue).startsWith("prep-")) {
        const id = ingredientValue.replace("prep-", "");

        selectedItem = preparedItems.find(
          (item) => String(item.semi_finished_id) === String(id),
        );

        isPreparedItem = true;
        // console.log("SELECTED ITEM:", selectedItem);
        // console.log("IS PREPARED:", isPreparedItem);
      }
      updated[index].isFixedCostItem = selectedItem?.is_fixed_cost || false;

      if (selectedItem?.is_fixed_cost) {
        updated[index].quantity_required = 0;
        updated[index].cost = 0;

        if (!updated[index].fixedCost) {
          updated[index].fixedCost = "";
        }
      }
      //console.log("BASE UNIT:", updated[index].baseUnit);
      //console.log("CURRENT UNIT:", updated[index].unit);
      if ((!selectedItem && !updated[index].baseUnit) || !updated[index].unit) {
        updated[index].cost = "";
        setForm({ ...form, ingredients: updated });
        return;
      }
     

      const selectedUnit = updated[index].unit;
      // console.log("INVENTORY UNIT:", inventoryUnit);
      // console.log("SELECTED UNIT:", selectedUnit);

      let costPerUnit = 0;

      const batches =
        updated[index].__tempBatches ||
        batchesMap[updated[index].ingredient_id] ||
        [];

         const batchUnit =
  batches.length > 0 ? batches[0].unit : null;

const inventoryUnit = selectedItem
  ? isPreparedItem
    ? selectedItem.yield_unit || selectedItem.unit
    : batchUnit || selectedItem.unit
  : updated[index].baseUnit;


      if (batches.length > 0) {
        costPerUnit = calculateWeightedAvg(batches);
      }

      //   console.log("BATCHES:", batches);
      //  console.log("WEIGHTED COST:", costPerUnit);
      // pcs logic

      if (selectedUnit === "pcs" && inventoryUnit === "packet") {
        let totalPieces = 0;
        let totalCost = 0;

        if (batches.length > 0) {
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
        }

        // FALLBACK FOR EDIT MODE
        else {
          const packetCost =
            selectedItem?.price_per_unit ||
            selectedItem?.cost_per_unit ||
            updated[index].originalCostPerUnit ||
            0;

          const piecesPerPacket = Number(selectedItem?.pieces || 1);

          costPerUnit =
            piecesPerPacket > 0 ? packetCost / piecesPerPacket : packetCost;
        }
      }

      if (
        batches.length === 0 &&
        !(selectedUnit === "pcs" && inventoryUnit === "packet")
      ) {
        // INVENTORY ITEM
        if (!isPreparedItem) {
          costPerUnit =
            selectedItem?.price_per_unit ||
            selectedItem?.cost_per_unit ||
            updated[index].originalCostPerUnit ||
            0;
        }

        // PREPARED ITEM
        else {
          costPerUnit = Number(selectedItem.unit_cost || 0);
        }
      }
      const inventoryCategory = getUnitCategory(inventoryUnit);
      const selectedCategory = getUnitCategory(selectedUnit);

      if (inventoryUnit === "rupee" || selectedUnit === "rupee") {
        if (inventoryUnit !== selectedUnit) {
          toast.error("Rupee unit must match exactly ❌");

          updated[index].unit = "";
          updated[index].cost = "";

          setForm({ ...form, ingredients: updated });
          return;
        }
      } else {
        if (inventoryCategory !== selectedCategory) {
          toast.error(
            `Invalid unit conversion: ${inventoryUnit} → ${selectedUnit}`,
          );

          updated[index].unit = "";
          updated[index].cost = "";

          setForm({ ...form, ingredients: updated });
          return;
        }
      }

      if (inventoryUnit !== "rupee" && selectedUnit !== "rupee") {
        // DO NOT reconvert prepared items wrongly
        if (!isPreparedItem) {
          costPerUnit = convertCost(inventoryUnit, selectedUnit, costPerUnit);
        } else {
          // prepared item conversion
          if (inventoryUnit === "kg" && selectedUnit === "gm") {
            costPerUnit = costPerUnit / 1000;
          } else if (inventoryUnit === "gm" && selectedUnit === "kg") {
            costPerUnit = costPerUnit * 1000;
          } else if (inventoryUnit === "liter" && selectedUnit === "ml") {
            costPerUnit = costPerUnit / 1000;
          } else if (inventoryUnit === "ml" && selectedUnit === "liter") {
            costPerUnit = costPerUnit * 1000;
          }
        }
      }
      updated[index].cost = Number(costPerUnit.toFixed(5));
      // console.log("FINAL COST:", costPerUnit);
      // console.log("FINAL TYPE:", typeof costPerUnit);
    }

    setForm({ ...form, ingredients: updated });
  };
  const addIngredient = () => {
    setForm((prev) => ({
      ...prev,
      ingredients: [
        ...prev.ingredients,
        {
          ingredient_id: "",
          ingredient_name: "",
          quantity_required: "",
          unit: "",
          search: "",
          cost: "",
          fixedCost: "",
          isFixedCostItem: false,
          isCustomItem: false,
        },
      ],
    }));

    setTimeout(() => {
      if (ingredientsContainerRef.current) {
        ingredientsContainerRef.current.scrollTop =
          ingredientsContainerRef.current.scrollHeight;
      }
    }, 100);
  };

  const removeIngredient = (index) => {
    const updated = form.ingredients.filter((_, i) => i !== index);
    setForm({ ...form, ingredients: updated });
  };

  const handleSubmit = async () => {
    try {
      // ================= FORM VALIDATIONS =================

      // Prepared item name validation
      if (!form.name.trim()) {
        toast.error("Prepared item name is required ❌");
        return;
      }

      // Quantity validation
      if (!form.quantity || Number(form.quantity) <= 0) {
        toast.error("Yield quantity must be greater than 0 ❌");
        return;
      }

      // Unit validation
      if (!form.unit) {
        toast.error("Please select yield unit ❌");
        return;
      }

      // Ingredient validation
      if (!form.ingredients.length) {
        toast.error("Please add at least one ingredient ❌");
        return;
      }

      // Validate every ingredient row
      for (let i = 0; i < form.ingredients.length; i++) {
        const ing = form.ingredients[i];

        const rowNumber = i + 1;

        // Ingredient selection validation
        const hasIngredient =
          ing.ingredient_id || (ing.isCustomItem && ing.ingredient_name);

        if (!hasIngredient) {
          toast.error(`Please select ingredient in row ${rowNumber} ❌`);
          return;
        }

        // Unit validation
        if (!ing.unit) {
          toast.error(`Please select unit in row ${rowNumber} ❌`);
          return;
        }

        // Fixed cost item validation
        if (ing.isFixedCostItem) {
          if (!ing.fixedCost || Number(ing.fixedCost) <= 0) {
            toast.error(`Please enter valid fixed cost in row ${rowNumber} ❌`);
            return;
          }
        }

        // Normal ingredient validation
        else {
          if (!ing.quantity_required || Number(ing.quantity_required) <= 0) {
            toast.error(`Please enter valid quantity in row ${rowNumber} ❌`);
            return;
          }
        }
      }

      // ================= PAYLOAD =================

      const payload = {
        name: form.name,
        yield_quantity: Number(form.quantity),
        yield_unit: form.unit,
        ingredients: form.ingredients
          .filter((ing) => {
            // VALID INVENTORY ITEM
            const isInventory = String(ing.ingredient_id).startsWith("inv-");

            // VALID PREPARED ITEM
            const isPrepared = String(ing.ingredient_id).startsWith("prep-");

            // VALID CUSTOM ITEM
            const isCustom = ing.isCustomItem && ing.ingredient_name;

            // skip invalid rows
            if (!isInventory && !isPrepared && !isCustom) {
              return false;
            }

            if (ing.isFixedCostItem) {
              return ing.fixedCost && Number(ing.fixedCost) > 0;
            }

            return ing.quantity_required && ing.unit;
          })
          .map((ing) => {
            if (ing.isCustomItem) {
              return {
                ingredient_name: ing.ingredient_name,

                unit: ing.unit,

                quantity_required: Number(ing.quantity_required),

                fixed_cost_amount: 0,
              };
            }
            // INVENTORY ITEM
            if (String(ing.ingredient_id).startsWith("inv-")) {
              const inventoryId = Number(ing.ingredient_id.replace("inv-", ""));

              const inventoryItem = inventory.find(
                (item) => Number(item.id) === inventoryId,
              );

              return {
                ingredient_id: inventoryId,

                ingredient_name: inventoryItem?.name || "",

                semi_finished_id: 0,

                is_semi_finished: false,

                unit: ing.unit,

                quantity_required: ing.isFixedCostItem
                  ? 0
                  : Number(ing.quantity_required),

                cost_per_unit: ing.isFixedCostItem ? 0 : Number(ing.cost),

                fixed_cost_amount: ing.isFixedCostItem
                  ? Number(ing.fixedCost || 0)
                  : 0,
              };
            }

            // PREPARED ITEM
            if (String(ing.ingredient_id).startsWith("prep-")) {
              const semiId = Number(ing.ingredient_id.replace("prep-", ""));

              const preparedItem = preparedItems.find(
                (item) => Number(item.semi_finished_id) === semiId,
              );

              return {
                ingredient_id: semiId,

                ingredient_name: preparedItem?.name || "",

                semi_finished_id: semiId,

                is_semi_finished: true,

                unit: ing.unit,

                quantity_required: Number(ing.quantity_required),

                cost_per_unit: Number(ing.cost),

                fixed_cost_amount: 0,
              };
            }

            return null;
          })
          .filter(Boolean),
      };

      if (Number(form.quantity || 0) < 0) {
        toast.error("Quantity cannot be negative ❌");
        return;
      }

      for (let ing of form.ingredients) {
        if (
          Number(ing.quantity_required || 0) < 0 ||
          Number(ing.cost || 0) < 0
        ) {
          toast.error("Negative values in ingredients not allowed ❌");
          return;
        }
      }

      if (editData) {
        for (let ing of form.ingredients) {
          if (ing.isFixedCostItem && !ing.fixedCost) {
            toast.error("Please enter fixed cost amount ❌");
            return;
          }
        }
        // console.log("FINAL PAYLOAD:", payload);
        const res = await api.patch(
          `/dish/update-semi-finished-ingredients/${editData.semi_finished_id}`,
          payload,
        );

        // console.log("UPDATED PREPARED ITEM:", res.data);

        toast.success("Prepared item Updated successfully");
      } else {
        for (let ing of form.ingredients) {
          if (ing.isFixedCostItem && !ing.fixedCost) {
            toast.error("Please enter fixed cost amount ❌");
            return;
          }
        }
        await api.post("/dish/add-semi-finished-ingredients", payload);

        toast.success(" Prepared item Added successfully ✅");
      }

      await onSuccess();
      onClose();
    } catch (err) {
      console.error("BACKEND ERROR:", err);

      // Backend message handling
      const backendMessage =
        err?.response?.data?.message ||
        err?.response?.data?.detail ||
        err?.response?.data?.error;

      // Validation errors array/object handling
      const validationErrors = err?.response?.data?.errors;

      // If backend sends validation errors array
      if (Array.isArray(validationErrors)) {
        validationErrors.forEach((msg) => {
          toast.error(msg);
        });

        return;
      }

      // If backend sends validation errors object
      if (validationErrors && typeof validationErrors === "object") {
        Object.values(validationErrors).forEach((msg) => {
          if (Array.isArray(msg)) {
            msg.forEach((m) => toast.error(m));
          } else {
            toast.error(msg);
          }
        });

        return;
      }

      // Single backend message
      if (backendMessage) {
        toast.error(backendMessage);
        return;
      }

      // Fallback
      toast.error("Something went wrong ❌");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex justify-center items-center z-50">
      <div
        ref={modalRef}
        onClick={(e) => e.stopPropagation()}
        className="bg-white dark:bg-[#020617] w-full max-w-3xl rounded-2xl p-6 relative border border-gray-200 dark:border-gray-800 shadow-xl"
      >
        {/* CLOSE */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-500 dark:text-gray-300 hover:text-black dark:hover:text-white"
        >
          <X />
        </button>

        <h2 className="text-lg font-semibold mb-4 text-gray-900 dark:text-white">
          {editData
            ? `Edit ${editData.name || "Prepared Item"}`
            : "Add Prepared Item"}
        </h2>

        <div className="space-y-4">
          {/* NAME */}
          <input
            type="text"
            name="name"
            placeholder="Item Name"
            value={form.name}
            onChange={handleChange}
            className="w-full px-3 py-2.5 rounded-xl border border-gray-300 
dark:border-gray-700 
bg-white dark:bg-[#020617]
text-gray-800 dark:text-gray-200
focus:ring-2 focus:ring-orange-400 outline-none"
          />

          {/* QUANTITY + UNIT */}
          <div className="flex gap-4">
            <input
              type="number"
              name="quantity"
              placeholder="Quantity"
              value={form.quantity}
              min="0.001"
              onKeyDown={(e) => {
                if (e.key === "-" || e.key === "e") e.preventDefault();
              }}
              onChange={handleChange}
              className="w-1/2 px-3 py-2.5 rounded-xl border border-gray-300 
  dark:border-gray-700 
  bg-white dark:bg-[#020617]
  text-gray-800 dark:text-gray-200
  focus:ring-2 focus:ring-orange-400 outline-none"
            />
            <div className="w-1/2 relative custom-dropdown">
              <div
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect();

                  setDropdownPosition({
                    top: rect.bottom + window.scrollY,
                    left: rect.left + window.scrollX,
                    width: rect.width,
                  });

                  setActiveDropdown(null);
                  setOpenUnitIndex(null);
                  setOpenMainUnit((prev) => !prev);
                }}
                className="px-3 py-2.5 rounded-xl border border-gray-300 
dark:border-gray-700 
bg-white dark:bg-[#020617]
text-gray-800 dark:text-gray-200
cursor-pointer flex justify-between items-center"
              >
                <span>
                  {(() => {
                    const selected = UNIT_OPTIONS.find(
                      (u) => u.value === form.unit,
                    );
                    return selected
                      ? `${selected.label} (${selected.value})`
                      : "Select Unit";
                  })()}
                </span>

                <span
                  className={`transition ${openMainUnit ? "rotate-180" : ""}`}
                >
                  ▼
                </span>
              </div>
              {openMainUnit &&
                createPortal(
                  <div
                    className="portal-dropdown fixed max-h-48 overflow-y-auto
      bg-white dark:bg-[#020617]
      border border-gray-200 dark:border-gray-700
      rounded-xl shadow-2xl z-[9999]"
                    style={{
                      top: dropdownPosition.top,
                      left: dropdownPosition.left,
                      width: dropdownPosition.width,
                    }}
                  >
                    {UNIT_OPTIONS.map((unit) => (
                      <div
                        key={unit.value}
                        onClick={() => {
                          setForm({ ...form, unit: unit.value });
                          setOpenMainUnit(false);
                        }}
                        className={`px-3 py-2 text-gray-800 dark:text-gray-200 cursor-pointer
            ${
              form.unit === unit.value
                ? "bg-orange-500 text-white"
                : "hover:bg-gray-100 dark:hover:bg-gray-800"
            }`}
                      >
                        {unit.label} ({unit.value})
                      </div>
                    ))}
                  </div>,
                  document.body,
                )}
            </div>
          </div>

          {/* INGREDIENTS */}
          <div>
            <h3 className="font-medium mb-2 text-gray-900 dark:text-gray-200">
              Ingredients
            </h3>
            <div
              ref={ingredientsContainerRef}
              className="max-h-[250px] overflow-y-auto pr-2"
            >
              {form.ingredients.map((ing, index) => {
                // console.log("ROW STATE", ing);
                return (
                  <div
                    key={index}
                    className="grid grid-cols-12 gap-3 mb-3 items-center"
                  >
                    <div className="col-span-3 relative ingredient-search">
                      <input
                        type="text"
                        placeholder="Search ingredient..."
                        value={ing.search || ""}
                        onFocus={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();

                          setDropdownPosition({
                            top: rect.bottom + window.scrollY,
                            left: rect.left + window.scrollX,
                            width: rect.width,
                          });

                          setOpenUnitIndex(null);
                          setOpenMainUnit(false);
                          setActiveDropdown(index);
                        }}
                        onChange={(e) =>
                          handleIngredientChange(
                            index,
                            "search",
                            e.target.value,
                          )
                        }
                        className="w-full px-3 py-2.5 rounded-xl border border-gray-300 
dark:border-gray-700 
bg-white dark:bg-[#020617]
text-gray-800 dark:text-gray-200
focus:ring-2 focus:ring-orange-400 outline-none"
                      />
                      {activeDropdown === index &&
                        createPortal(
                          <div
                            className="portal-dropdown fixed max-h-65 overflow-y-auto
      bg-white dark:bg-[#020617]
      border border-gray-200 dark:border-gray-700
      rounded-xl shadow-2xl z-[9999]"
                            style={{
                              top: dropdownPosition.top,
                              left: dropdownPosition.left,
                              width: dropdownPosition.width,
                            }}
                          >
                            <>
                              {/* INVENTORY ITEMS */}
                              <div className="px-3 py-1 text-xs text-gray-400">
                                Inventory Items
                              </div>

                              {inventory.map((item) => (
                                <div
                                  key={`inv-${item.id}`}
                                  onClick={() => {
                                    handleIngredientChange(
                                      index,
                                      "ingredient_id",
                                      `inv-${item.id}`,
                                    );

                                    handleIngredientChange(
                                      index,
                                      "ingredient_name",
                                      item.name,
                                    );

                                    handleIngredientChange(
                                      index,
                                      "isCustomItem",
                                      false,
                                    );

                                    handleIngredientChange(
                                      index,
                                      "search",
                                      `${item.name} (${item.unit})`,
                                      true,
                                    );

                                    setActiveDropdown(null);
                                  }}
                                  className="px-3 py-2 text-gray-800 dark:text-gray-200 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                                >
                                  {item.name} ({item.unit})
                                </div>
                              ))}

                              {/* PREPARED ITEMS */}
                              <div className="px-3 py-1 text-xs text-gray-400 border-t dark:border-gray-700">
                                Prepared Items
                              </div>

                              {preparedItems.map((item) => (
                                <div
                                  key={`prep-${item.semi_finished_id}`}
                                  onClick={() => {
                                    handleIngredientChange(
                                      index,
                                      "ingredient_id",
                                      `prep-${item.semi_finished_id}`,
                                    );

                                    handleIngredientChange(
                                      index,
                                      "ingredient_name",
                                      item.name,
                                    );

                                    handleIngredientChange(
                                      index,
                                      "isCustomItem",
                                      false,
                                    );

                                    handleIngredientChange(
                                      index,
                                      "search",
                                      `${item.name} (${item.yield_unit})`,
                                      true,
                                    );

                                    setActiveDropdown(null);
                                  }}
                                  className="px-3 py-2 text-gray-800 dark:text-gray-200 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800"
                                >
                                  {item.name} ({item.yield_unit})
                                </div>
                              ))}

                              {inventory.length === 0 &&
                                preparedItems.length === 0 && (
                                  <div className="p-2 text-gray-400 text-sm">
                                    No results
                                  </div>
                                )}
                            </>
                          </div>,
                          document.body,
                        )}
                    </div>

                    {/* QTY */}
                    <input
                      type="number"
                      placeholder="Qty"
                      value={ing.isFixedCostItem ? 0 : ing.quantity_required}
                      disabled={ing.isFixedCostItem}
                      min="0.001"
                      onKeyDown={(e) => {
                        // 🚫 block negative + scientific notation
                        if (e.key === "-" || e.key === "e") e.preventDefault();
                      }}
                      onChange={(e) => {
                        const value = e.target.value;

                        // 🚫 skip change if fixed cost item
                        if (ing.isFixedCostItem) return;

                        // 🚫 block negative (paste + typing)
                        if (value !== "" && Number(value) < 0) {
                          toast.error("Negative values not allowed ❌");
                          return;
                        }

                        handleIngredientChange(
                          index,
                          "quantity_required",
                          value,
                        );
                      }}
                      className={`col-span-2 px-3 py-2.5 rounded-xl border 
    ${
      ing.isFixedCostItem
        ? "bg-gray-100 dark:bg-[#020617] cursor-not-allowed text-gray-500"
        : "bg-white dark:bg-[#0b1220] text-gray-800 dark:text-gray-200"
    } 
    border-gray-300 dark:border-gray-700
    focus:ring-2 focus:ring-orange-400 outline-none`}
                    />

                    {/* UNIT */}
                    <div className="col-span-3 relative custom-dropdown">
                      <div
                        onClick={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect();

                          setDropdownPosition({
                            top: rect.bottom + window.scrollY,
                            left: rect.left + window.scrollX,
                            width: rect.width,
                          });

                          setActiveDropdown(null);
                          setOpenMainUnit(false);
                          setOpenUnitIndex(
                            openUnitIndex === index ? null : index,
                          );
                        }}
                        className="px-3 py-2.5 rounded-xl border border-gray-300 
dark:border-gray-700 
bg-white dark:bg-[#020617]
text-gray-800 dark:text-gray-200
cursor-pointer flex justify-between items-center"
                      >
                        <span>
                          {(() => {
                            const selected = UNIT_OPTIONS.find(
                              (u) => u.value === ing.unit,
                            );
                            return selected
                              ? `${selected.label} (${selected.value})`
                              : "Unit";
                          })()}
                        </span>

                        <span
                          className={`transition ${openUnitIndex === index ? "rotate-180" : ""}`}
                        >
                          ▼
                        </span>
                      </div>
                      {openUnitIndex === index &&
                        createPortal(
                          <div
                            className="portal-dropdown fixed max-h-48 overflow-y-auto
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
                              //  Get selected inventory item for this row
                              let selectedItem = null;
                              let baseUnit = null;

                              // INVENTORY ITEM
                              if (
                                String(ing.ingredient_id).startsWith("inv-")
                              ) {
                                const id = ing.ingredient_id.replace(
                                  "inv-",
                                  "",
                                );

                                selectedItem = inventory.find(
                                  (inv) => String(inv.id) === String(id),
                                );

                                baseUnit = selectedItem?.unit;
                              }

                              // PREPARED ITEM
                              else if (
                                String(ing.ingredient_id).startsWith("prep-")
                              ) {
                                const id = ing.ingredient_id.replace(
                                  "prep-",
                                  "",
                                );

                                selectedItem = preparedItems.find(
                                  (item) =>
                                    String(item.semi_finished_id) ===
                                    String(id),
                                );

                                // IMPORTANT
                                baseUnit =
                                  selectedItem?.yield_unit ||
                                  selectedItem?.unit;
                              }

                              // NEW ITEM → show all units
                              if (ing.isCustomItem) {
                                return UNIT_OPTIONS.map((unit) => (
                                  <div
                                    key={unit.value}
                                    onClick={() => {
                                      handleIngredientChange(
                                        index,
                                        "unit",
                                        unit.value,
                                      );
                                      setOpenUnitIndex(null);
                                    }}
                                    className={`px-3 py-2 text-gray-800 dark:text-gray-200 cursor-pointer
        ${
          ing.unit === unit.value
            ? "bg-orange-500 text-white"
            : "hover:bg-gray-100 dark:hover:bg-gray-800"
        }`}
                                  >
                                    {unit.label} ({unit.value})
                                  </div>
                                ));
                              }

                              // EXISTING LOGIC FOR INVENTORY / PREPARED ITEMS
                              const allowedCategory = getUnitCategory(
                                baseUnit || ing.unit,
                              );

                              const filteredUnits = allowedCategory
                                ? UNIT_OPTIONS.filter(
                                    (u) =>
                                      getUnitCategory(u.value) ===
                                      allowedCategory,
                                  )
                                : [];

                              return filteredUnits.map((unit) => (
                                <div
                                  key={unit.value}
                                  onClick={() => {
                                    handleIngredientChange(
                                      index,
                                      "unit",
                                      unit.value,
                                    );
                                    setOpenUnitIndex(null);
                                  }}
                                  className={`px-3 py-2 text-gray-800 dark:text-gray-200 cursor-pointer
      ${
        ing.unit === unit.value
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
                    {ing.isFixedCostItem ? (
                      <input
                        type="number"
                        placeholder="Fixed Cost"
                        value={ing.fixedCost}
                        min="0.001"
                        onKeyDown={(e) => {
                          // 🚫 block negative + scientific notation
                          if (e.key === "-" || e.key === "e")
                            e.preventDefault();
                        }}
                        onChange={(e) => {
                          const value = e.target.value;

                          // 🚫 block negative values from typing/paste
                          if (value !== "" && Number(value) < 0) {
                            toast.error("Negative values not allowed ❌");
                            return;
                          }

                          handleIngredientChange(index, "fixedCost", value);
                        }}
                        className="col-span-3 px-3 py-2.5 rounded-xl border border-gray-300
dark:border-gray-700 bg-white dark:bg-[#0b1220]
text-gray-800 dark:text-gray-200
focus:ring-2 focus:ring-orange-400 outline-none"
                      />
                    ) : (
                      <input
                        type="text"
                        placeholder="Cost/unit"
                        value={
                          ing.cost !== "" &&
                          ing.cost !== null &&
                          ing.cost !== undefined
                            ? Number(ing.cost).toFixed(2)
                            : ""
                        }
                        readOnly
                        className="col-span-3 px-3 py-2.5 rounded-xl border border-gray-300
dark:border-gray-700 bg-gray-100 dark:bg-[#020617]
text-gray-500 cursor-not-allowed outline-none"
                      />
                    )}

                    {/* REMOVE */}
                    <button
                      onClick={() => removeIngredient(index)}
                      className="col-span-1 flex justify-center items-center text-red-500 hover:scale-110 transition"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>

            <button
              onClick={addIngredient}
              className="text-orange-500 text-sm mt-2"
            >
              + Add Ingredient
            </button>
          </div>

          {/* SUBMIT */}
          <button
            onClick={handleSubmit}
            className="w-full bg-orange-500 text-white py-2 rounded-lg hover:bg-orange-600"
          >
            {editData ? "Update Prepared Item" : "Save Prepared Item"}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AddPreparedItemModal;
