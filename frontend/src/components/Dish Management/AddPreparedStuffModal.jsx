import { useEffect, useState } from "react";
import {
  FiX,
  FiPlus,
  FiCheck,
  FiEdit,
  FiTrash2,
} from "react-icons/fi";
import api from "../../api/axios";

export default function AddPreparedStuffModal({
  isOpen,
  onClose,
  onSave,
  editData,
}) {
  /* ===== EXISTING STATE (UNCHANGED) ===== */
  const [stuffName, setStuffName] = useState("");
  const [ingredients, setIngredients] = useState([]);
  const [adding, setAdding] = useState(false);

  const [tempIngredient, setTempIngredient] = useState({
    ingredient_id: "",
    name: "",
    quantity: "",
    unit: "",
    available_quantity: 0,
    preferred_batch_id: null,
  });


  const [editIndex, setEditIndex] = useState(null);

  /* ===== NEW STATES (ADDED ONLY) ===== */
  const [productType, setProductType] = useState("BATTER");
  const [unit, setUnit] = useState("gm");
  const [storageLocationId, setStorageLocationId] = useState("");
  const [description, setDescription] = useState("");
  const [shelfLifeHours, setShelfLifeHours] = useState("");
  const [prepTimeMinutes, setPrepTimeMinutes] = useState("");
  const [yieldQuantity, setYieldQuantity] = useState("");
  const [storages, setStorages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [quantityError, setQuantityError] = useState("");

  const fetchItems = async () => {
    try {
      const res = await api.get("/inventory/");
      setItems(res.data.data || []);
    } catch (err) {
      console.error("Failed to fetch items", err);
    }
  };

  const fetchStorages = async () => {
    try {
      setLoading(true);
      const res = await api.get("/inventory/get-all-storage/all");
      setStorages(res.data.data || []);
    } catch (err) {
      console.error("Failed to fetch storages", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
  if (isOpen) {
    fetchStorages();
    fetchItems();
  }
  }, [isOpen]);
  
  useEffect(() => {
    console.log("EDIT DATA RECEIVED:", editData);
  }, [editData]);

  useEffect(() => {
    if (isOpen && !editData) {
      // Reset form when opening Add mode
      setStuffName("");
      setIngredients([]);
      setProductType("BATTER");
      setUnit("gm");
      setStorageLocationId("");
      setDescription("");
      setShelfLifeHours("");
      setPrepTimeMinutes("");
      setYieldQuantity("");
      setAdding(false);
      setEditIndex(null);
    }
  }, [isOpen, editData]);


  useEffect(() => {
    if (editData) {
      setStuffName(editData.name || "");
      setIngredients(
        (editData.ingredients || []).map((ing) => ({
          ingredient_id: ing.ingredient_id,
          name: ing.ingredient_name,
          quantity: ing.quantity_required,
          unit: ing.unit,
          preferred_batch_id: ing.preferred_batch_id || null,
        }))
      );

      /* NEW */
      setProductType(editData.product_type || "BATTER");
      setUnit(editData.unit || "gm");
      setStorageLocationId(editData.storage_location_id || "");
      setDescription(editData.description || "");
      setShelfLifeHours(editData.shelf_life_hours || "");
      setPrepTimeMinutes(editData.preparation_time_minutes || "");
      setYieldQuantity(editData.yield_quantity || "");
    } else {
      setStuffName("");
      setIngredients([]);
      setProductType("BATTER");
      setUnit("gm");
      setStorageLocationId("");
      setDescription("");
      setShelfLifeHours("");
      setPrepTimeMinutes("");
      setYieldQuantity("");
    }
  }, [editData]);

  if (!isOpen) return null;

  const resetTemp = () => {
    setTempIngredient({ name: "", quantity: "" });
    setAdding(false);
    setEditIndex(null);
  };

  
  const handleAddIngredient = () => {
    setAdding(true);
    setTempIngredient({ name: "", quantity: "" });
  };

const handleSaveIngredient = () => {
  if (
    !tempIngredient.ingredient_id ||
    !tempIngredient.quantity ||
    quantityError
  )
    return;

  if (editIndex !== null) {
    const updated = [...ingredients];
    updated[editIndex] = tempIngredient;
    setIngredients(updated);
  } else {
    setIngredients([...ingredients, tempIngredient]);
  }

  resetTemp();
};


  const handleEditIngredient = (idx) => {
    setEditIndex(idx);
    setTempIngredient(ingredients[idx]);
    setAdding(true);
  };

  const handleDeleteIngredient = (idx) =>
  {
    setIngredients(ingredients.filter((_, i) => i !== idx));
  };

  const handleSubmit = async () => {
    if (!stuffName.trim()) {
      alert("Stuff name is required");
      return;
    }

    if (ingredients.length === 0) {
      alert("Please add at least one ingredient");
      return;
    }

    const payload = {
      name: stuffName.trim(),
      product_type: productType,
      description: description || "",
      unit,
      shelf_life_hours: shelfLifeHours
        ? Number(shelfLifeHours)
        : 0,
      preparation_time_minutes: prepTimeMinutes
        ? Number(prepTimeMinutes)
        : 0,
      storage_location_id: storageLocationId
        ? Number(storageLocationId)
        : null,
      yield_quantity: yieldQuantity
        ? Number(yieldQuantity)
        : 0,
      ingredients: ingredients.map((ing) => ({
        ingredient_id: Number(ing.ingredient_id),
        quantity_required: Number(ing.quantity),
        unit: ing.unit,
        preferred_batch_id: ing.preferred_batch_id
          ? Number(ing.preferred_batch_id)
          : 0,
      })),
    };

    try {
      console.log("editData:", editData);

      // ✅ UPDATE only if real product_id exists
      if (editData?.product_id) {

        console.log("Updating product:", editData.product_id);
        console.log("PATCH PAYLOAD:", JSON.stringify(payload, null, 2));


        await api.patch(
          `/dish/update-semi-finished/${editData.product_id}`,
          payload
        );

      } else {

        console.log("Creating new product");

        await api.post(
          "/dish/semi-finished/create",
          payload
        );
      }

      onSave();
      onClose();

    } catch (err) {
      console.error("Failed to save prepared stuff", err);
      alert("Failed to save prepared stuff");
    }

  };



  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-3 sm:px-6">
      <div className="absolute inset-0 bg-black/40" onClick={onClose}></div>

      <div className="relative w-full max-w-3xl my-6 bg-white dark:bg-[#0f172a] rounded-xl shadow-lg border border-gray-200 dark:border-gray-800">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {editData ? "Edit Prepared Stuff" : "Add Prepared Stuff"}
          </h2>
          <button onClick={onClose} className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800">
            <FiX className="text-xl text-gray-700 dark:text-gray-200" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-6 space-y-6 max-h-[70vh] overflow-y-auto">
          {/* Stuff Name */}
          <div>
            <label className="text-sm font-medium text-gray-800 dark:text-gray-200">
              Stuff Name
            </label>
            <input
              placeholder="Enter Stuff Name"
              type="text"
              value={stuffName}
              onChange={(e) => setStuffName(e.target.value)}
              className="mt-2 w-full border border-gray-300 dark:border-gray-700
              rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
              text-gray-800 dark:text-gray-200 outline-none"

            />
          </div>

          {/* NEW GRID (same styling) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="text-sm font-medium text-gray-800 dark:text-gray-200">Product Type</label>
              <select
                value={productType}
                onChange={(e) => setProductType(e.target.value)}
               className="mt-2 w-full border border-gray-300 dark:border-gray-700
              rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
              text-gray-800 dark:text-gray-200 outline-none"

              >
                <option value="BATTER">BATTER</option>
                <option value="SAUCE">SAUCE</option>
                <option value="PASTE">PASTE</option>
                <option value="STOCK">STOCK</option>
                <option value="SPICES">SPICES</option>
                <option value="DOUGH">DOUGH</option>
                <option value="FILLING">FILLING</option>
                <option value="GRAVY">GRAVY</option>
                <option value="OTHER">OTHER</option>
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-800 dark:text-gray-200">Unit</label>
              <select
                name="unit"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                className="mt-2 w-full border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-white dark:bg-[#0b1220] text-gray-800 dark:text-gray-200 outline-none"

              >
                <option value="kg">kg</option>
                <option value="gm">gm</option>
                <option value="mg">mg</option>
                <option value="liter">liter</option>
                <option value="ml">ml</option>
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-800 dark:text-gray-200">Shelf Life (hours)</label>
              <input
                placeholder="Enter Shelf Life"
                type="number"
                value={shelfLifeHours}
                onChange={(e) => setShelfLifeHours(e.target.value)}
                className="mt-2 w-full border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-white dark:bg-[#0b1220] text-gray-800 dark:text-gray-200 outline-none"

              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray-800 dark:text-gray-200">Preparation Time (minutes)</label>
              <input
                placeholder="Enter Preparation Time"
                type="number"
                value={prepTimeMinutes}
                onChange={(e) => setPrepTimeMinutes(e.target.value)}
                className="mt-2 w-full border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-white dark:bg-[#0b1220] text-gray-800 dark:text-gray-200 outline-none"

              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray-800 dark:text-gray-200">Yield Quantity</label>
              <input
                placeholder="Enter Yield Quantity"
                type="number"
                value={yieldQuantity}
                onChange={(e) => setYieldQuantity(e.target.value)}
                className="mt-2 w-full border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-white dark:bg-[#0b1220] text-gray-800 dark:text-gray-200 outline-none"

              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray-800 dark:text-gray-200">Storage Location</label>
              <select
                value={storageLocationId}
                onChange={(e) => setStorageLocationId(e.target.value)}
                className="mt-2 w-full border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-white dark:bg-[#0b1220] text-gray-800 dark:text-gray-200 outline-none"

              >
                <option value="">Select Storage</option>

                {storages.map((store) => (
                  <option key={store.id} value={store.id}>
                    {store.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-800 dark:text-gray-200">Description</label>
            <textarea
              placeholder="Description..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-2 w-full border border-gray-300 dark:border-gray-700 rounded-md px-3 py-2 bg-white dark:bg-[#0b1220] text-gray-800 dark:text-gray-200 outline-none"

            />
          </div>

          {/* INGREDIENT SECTION (UNCHANGED) */}
          {/* Ingredients Section */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Ingredients
              </h3>

              {!adding && (
                <button
                  onClick={handleAddIngredient}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-md
                             bg-yellow-400 hover:bg-yellow-500 text-sm font-medium"
                >
                  <FiPlus />
                  Add Ingredient
                </button>
              )}
            </div>

            {/* Add / Edit Ingredient Row */}
            {adding && (
              <div className="mb-3 flex items-center gap-3">
                <select
                  value={tempIngredient.ingredient_id}
                  onChange={(e) => {
                    const selected = items.find(
                      (it) => it.id === Number(e.target.value)
                    );

                    setTempIngredient({
                      ingredient_id: selected.id,
                      name: selected.name,
                      quantity: "",
                      unit: selected.unit,
                      available_quantity: selected.quantity,
                      preferred_batch_id: selected.batch_id || null,
                    });

                    setQuantityError("");
                  }}
                  className="mt-2 w-sm border border-gray-300 dark:border-gray-700
                            rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
                            text-gray-800 dark:text-gray-200 outline-none"
                >
                  <option value="">Select Item</option>
                  {items.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                {tempIngredient.ingredient_id && (
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    {/* Available:{" "} */}
                    <span className="font-medium text-gray-700 dark:text-gray-300">
                      {tempIngredient.available_quantity} {tempIngredient.unit}
                    </span>
                  </div>
                )}


                <div className="flex flex-col">
                  <input
                    type="number"
                    placeholder="Quantity"
                    value={tempIngredient.quantity}
                    onChange={(e) => {
                      const value = Number(e.target.value);

                      if (value > tempIngredient.available_quantity) {
                        setQuantityError(
                          `Available: ${tempIngredient.available_quantity} ${tempIngredient.unit}`
                        );
                      } else {
                        setQuantityError("");
                      }

                      setTempIngredient((p) => ({
                        ...p,
                        quantity: value,
                      }));
                    }}
                    className="mt-2 w-40 border border-gray-300 dark:border-gray-700
                              rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
                              text-gray-800 dark:text-gray-200 outline-none"
                  />

                  {quantityError && (
                    <span className="text-xs text-red-500 mt-1">
                      {quantityError}
                    </span>
                  )}
                </div>

                <button
                  onClick={handleSaveIngredient}
                  className="p-2 rounded bg-green-500 hover:bg-green-600 text-white"
                >
                  <FiCheck />
                </button>

                <button
                  onClick={resetTemp}
                  className="p-2 rounded bg-red-400 hover:bg-red-500 text-white"
                >
                  <FiX />
                </button>
              </div>
            )}

            {/* Ingredient List */}
            <div className="max-h-[200px] overflow-y-auto space-y-2 pr-1">
              {ingredients.map((ing, idx) => (
                <div
                  key={idx}
                  className="flex items-center gap-3 border border-gray-200 dark:border-gray-700
                             rounded-md px-3 py-2"
                >
                  <div className="flex-1 text-sm text-gray-800 dark:text-gray-200">
                    {ing.name}
                  </div>
                  <div className="w-32 text-sm text-gray-800 dark:text-gray-200">
                    {ing.quantity}
                  </div>

                  <button
                    onClick={() => handleEditIngredient(idx)}
                    className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    <FiEdit className="text"/>
                  </button>
{/* 
                  <button
                    onClick={() => handleDeleteIngredient(idx)}
                    className="p-2 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                  >
                    <FiTrash2 className="text-red-600" />
                  </button> */}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center gap-4 px-6 py-4 border-t border-gray-200 dark:border-gray-800">
          <button onClick={handleSubmit} className="px-8 py-2 bg-green-400 hover:bg-green-500 text-white rounded-md">
            Save
          </button>
          <button onClick={onClose} className="px-8 py-2 bg-yellow-400 hover:bg-yellow-500 rounded-md">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
