import { useEffect, useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";
import { FiUpload, FiX } from "react-icons/fi";
import { downloadWastageCSV } from "../../utils/ExcelFormatDownloadFunction";

export default function AddDishWastageModal({
  isOpen,
  onClose,
  onSuccess,
  editData = null,
}) {
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
    single: ["unit"],
  };

  const getUnitCategory = (unit) => {
    for (const key in UNIT_CATEGORIES) {
      if (UNIT_CATEGORIES[key].includes(unit)) return key;
    }
    return null;
  };

  const convertToBase = (value, fromUnit, baseUnit) => {
    let val = Number(value);

    // weight
    if (fromUnit === "gm" && baseUnit === "kg") val /= 1000;
    if (fromUnit === "mg" && baseUnit === "kg") val /= 1000000;

    // volume
    if (fromUnit === "ml" && baseUnit === "liter") val /= 1000;

    // length
    if (fromUnit === "cm" && baseUnit === "m") val /= 100;
    if (fromUnit === "mm" && baseUnit === "m") val /= 1000;

    return val;
  };

  const [type, setType] = useState("");

  const [items, setItems] = useState([]);
  const [filteredItems, setFilteredItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);

  const [itemSearch, setItemSearch] = useState("");
  const [selectedItem, setSelectedItem] = useState(null);

  const [batches, setBatches] = useState([]);
  const [selectedBatch, setSelectedBatch] = useState(null);

  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [wastageDate, setWastageDate] = useState(
    new Date().toISOString().split("T")[0],
  );

  const [proof, setProof] = useState(null);

  const [remainingQty, setRemainingQty] = useState(0);

  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const [unit, setUnit] = useState("");

  useEffect(() => {
    if (!editData) return;

    const loadEditData = async () => {
      setType(editData.wastage_type || "");

      setQuantity(editData.quantity_wasted || editData.quantity_unsold || "");

      setReason(editData.wastage_reason || "");

      setWastageDate(
        editData.wastage_date
          ? editData.wastage_date.split("T")[0]
          : new Date().toISOString().split("T")[0],
      );

      setUnit(editData.unit || "");

      const itemName = editData.item_name || editData.dish_name || "";

      setItemSearch(itemName);

      // FETCH ITEMS
      await handleTypeChange(editData.wastage_type, true);
      // SELECT ITEM
      console.log("EDIT DATA FULL", editData);

      const selected = {
        id:
          editData.inventory_item_id ||
          editData.dish_id ||
          editData.semi_finished_id ||
          editData.combo_id ||
          editData.item_id,

        name:
          editData.item_name ||
          editData.dish_name ||
          editData.combo_name ||
          editData.semi_finished_name ||
          editData.name ||
          "",

        unit: editData.unit || editData.yield_unit,
      };

      setSelectedItem(selected);

      setItemSearch(selected.name);
      // INVENTORY BATCH
      if (editData.wastage_type === "inventory" && editData.inventory_item_id) {
        const batchData = await fetchBatches(editData.inventory_item_id, true);

        console.log("EDIT DATA", editData);
        console.log("BATCH DATA", batchData);

        const matchedBatch = batchData.find(
          (b) => b.batch_number === editData.batch_number,
        );

        if (matchedBatch) {
          setSelectedBatch(matchedBatch);

          setRemainingQty(matchedBatch.quantity_remaining || 0);
        }
      }
    };

    loadEditData();
  }, [editData]);

  /* ================= FETCH ITEMS ================= */

  const fetchItems = async (selectedType, search = "") => {
    try {
      setLoadingItems(true);

      // ================= INVENTORY =================
      if (selectedType === "inventory") {
        const res = await api.get("/inventory/", {
          params: {
            page: 1,
            page_size: 20,
            search: search || undefined,
          },
        });

        const data = res.data?.data || [];

        const formatted = data.map((item) => ({
          id: item.id,
          name: item.name,
          unit: item.unit,
        }));

        setItems(formatted);
        setFilteredItems(formatted);
      }

      // ================= DISH =================
      if (selectedType === "dish") {
        const res = await api.get("/dish/get-dishes-with-ingredients", {
          params: {
            page: 1,
            page_size: 20,
            search: search || undefined,
          },
        });

        const raw = res.data?.data || res.data?.dishes || res.data || [];

        const formatted = raw.map((dish) => ({
          id: dish.id,
          name: dish.dish_name || dish.name,
        }));

        setItems(formatted);
        setFilteredItems(formatted);
      }

      // ================= PREPARED ITEM =================
      if (selectedType === "semi_finished") {
        const res = await api.get("/dish/semi-finished-ingredients", {
          params: {
            page: 1,
            page_size: 20,
            is_active: true,
            search: search || undefined,
          },
        });

        const raw = res.data?.data || res.data || [];

        const formatted = raw.map((item) => ({
          id: item.id || item.semi_finished_id || item.item_id,

          name: item.name || item.item_name || item.semi_finished_name,

          unit: item.unit || item.base_unit || item.yield_unit,
        }));

        setItems(formatted);
        setFilteredItems(formatted);
      }

      // ================= COMBO =================
      if (selectedType === "combo") {
        const res = await api.get("/dish/", {
          params: {
            page: 1,
            page_size: 20,
            search: search || undefined,
          },
        });

        const raw = res.data?.combos || [];

        const formatted = raw.map((combo) => ({
          id: combo.id,
          name: combo.name,
        }));

        setItems(formatted);
        setFilteredItems(formatted);
      }
    } catch (err) {
      console.error("Failed to fetch items", err);
    } finally {
      setLoadingItems(false);
    }
  };
  /* ================= TYPE CHANGE ================= */
  const handleTypeChange = async (value, isEdit = false) => {
    setType(value);
    if (!isEdit) {
      setItemSearch("");
      setSelectedItem(null);

      setBatches([]);
      setSelectedBatch(null);

      setQuantity("");
      setRemainingQty(0);
    }

    try {
      await fetchItems(value);

      if (!isEdit) {
        setShowDropdown(true);
      }
    } catch (err) {
      console.error("Failed to fetch items", err);
    }
  };
  /* ================= SEARCH FILTER ================= */

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (!e.target.closest(".relative")) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("click", handleClickOutside);

    return () => document.removeEventListener("click", handleClickOutside);
  }, []);

  useEffect(() => {
    if (!type) return;

    const delayDebounce = setTimeout(() => {
      fetchItems(type, itemSearch);
    }, 400);

    return () => clearTimeout(delayDebounce);
  }, [itemSearch, type]);

  /* ================= FETCH BATCHES ================= */
  const fetchBatches = async (itemId, isEdit = false) => {
    try {
      let data = [];

      // EDIT MODE → FETCH ALL BATCHES
      if (isEdit) {
        const res = await api.get("/inventory/filter/get-all-batches");

        const allBatches = res.data?.data || [];

        data = allBatches.filter(
          (batch) => Number(batch.inventory_item_id) === Number(itemId),
          
        );
      }

      // ADD MODE → FETCH ONLY ACTIVE BATCHES
      else {
        const res = await api.get(`/inventory/items/${itemId}/batches`);

        const allBatches = res.data?.data || [];

        data = allBatches.filter((batch) => batch.is_active === true);
      }

      setBatches(data);

      return data;
    } catch (err) {
      console.error("Failed to fetch batches", err);

      return [];
    }
  };

  /* ================= ITEM SELECT ================= */

  const handleItemSelect = (item) => {
    setSelectedItem(item);

    setItemSearch(item.name);

    setShowDropdown(false);

    if (type === "inventory") {
      fetchBatches(item.id, !!editData);
    }
  };

  /* ================= BATCH SELECT ================= */

  const handleBatchSelect = (batch) => {
    setSelectedBatch(batch);

    setRemainingQty(batch.quantity_remaining);
  };

  /* ================= QUANTITY VALIDATION ================= */
  const handleQuantityChange = (val) => {
    const num = Number(val);

    if (val !== "" && num < 0) {
      toast.error("Negative quantity not allowed ❌");
      return;
    }

    if (type === "inventory" && !selectedBatch) {
      toast.error("Please select batch first ❌");
      return;
    }

    setQuantity(val);
  };
  /* ================= SUBMIT ================= */
  const handleSubmit = async () => {
    if (!type || !selectedItem || !quantity) {
      toast.error("Please fill all required fields");
      return;
    }

    try {
      const formData = new FormData();

      formData.append("wastage_type", type);
      formData.append("quantity_wasted", Number(quantity));

      let finalReason = reason;

      if (type === "inventory" && !reason) {
        finalReason = "other";
      }

      if (type === "dish" && !reason) {
        finalReason = "unsold_dish";
      }

      if (type === "semi_finished" && !reason) {
        finalReason = "preparation_error";
      }
      if (type === "combo" && !reason) {
        finalReason = "other";
      }

      formData.append("wastage_reason", finalReason);
      formData.append("wastage_date", `${wastageDate}T00:00:00`);

      if (proof) {
        formData.append("photo", proof);
      }

      // INVENTORY
      if (type === "inventory") {
        if (!selectedBatch) {
          toast.error("Please select batch");
          return;
        }

        if (!unit) {
          toast.error("Please select unit");
          return;
        }

        formData.append("inventory_item_id", Number(selectedItem.id));
        formData.append("inventory_batch_id", Number(selectedBatch.id));
        formData.append("unit", unit);
      }

      // DISH
      if (type === "dish") {
        formData.append("dish_id", Number(selectedItem.id));
      }

      // PREPARED ITEM
      if (type === "semi_finished") {
        formData.append("semi_finished_id", Number(selectedItem.id));

        // SEND UNIT ALSO
        formData.append("unit", unit);
      }

      // COMBO
      if (type === "combo") {
        formData.append("combo_id", Number(selectedItem.id));
      }

      for (let pair of formData.entries()) {
        console.log(pair[0], pair[1]);
      }

      if (type === "inventory" || type === "semi_finished") {
        if (type === "inventory" && !selectedBatch) {
          toast.error("Please select batch ❌");
          return;
        }

        if (!unit) {
          toast.error("Please select unit ❌");
          return;
        }

        if (!selectedItem?.unit) {
          toast.error("Item unit missing ❌");
          return;
        }

        const baseUnit = selectedItem.unit;

        let convertedQty = Number(quantity);

        const selectedUnit = unit;

        if (
          ["pcs", "piece", "pieces"].includes(selectedUnit) &&
          ["packet", "packets", "pkt"].includes(baseUnit)
        ) {
          if (!selectedBatch.pieces) {
            toast.error("Pieces per packet not defined ❌");
            return;
          }

          convertedQty = Number(quantity) / Number(selectedBatch.pieces);
        } else if (selectedUnit === baseUnit) {
          convertedQty = Number(quantity);
        } else {
          convertedQty = convertToBase(
            Number(quantity),
            selectedUnit,
            baseUnit,
          );
        }

        if (type === "inventory" && !editData) {
          const remaining = Number(selectedBatch.quantity_remaining);

          console.log("EDIT DATA", editData);
          console.log("SELECTED BATCH", selectedBatch);
          console.log("QUANTITY", quantity);
          console.log("CONVERTED QTY", convertedQty);
          console.log("REMAINING", remaining);
          console.log("BASE UNIT", baseUnit);
          console.log("SELECTED UNIT", selectedUnit);

          if (!["pcs", "piece", "pieces", "unit"].includes(selectedUnit)) {
            if (convertedQty > remaining) {
              toast.error(`Cannot waste more than ${remaining} ${baseUnit} ❌`);

              return;
            }
          }
        }
      }

      // EDIT
      if (editData) {
        await api.put(`/wastage/edit-wastage/${editData.id}`, formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        });

        toast.success("Wastage updated successfully");
      }

      // ADD
      else {
        const res = await api.post("/wastage/add-wastage", formData);
        console.log(res.data,"DATAAAAAAAA");
        toast.success("Wastage recorded successfully");

        downloadWastageCSV(
          res.data.data,
          res.data.wastage_type
      );
      }

      onSuccess();
      onClose();
    } catch (err) {
  console.error(err);

  const data = err?.response?.data;

  let message = "Failed to record wastage";

  // FastAPI validation/custom errors
  if (data?.detail?.errors && Array.isArray(data.detail.errors)) {
    message = data.detail.errors.join("\n");
  }

  // FastAPI HTTPException(detail="...")
  else if (typeof data?.detail === "string") {
    message = data.detail;
  }

  // Validation errors
  else if (Array.isArray(data?.detail)) {
    message = data.detail
      .map((e) => e.msg || e.message)
      .join("\n");
  }

  // Generic backend message
  else if (data?.message) {
    message = data.message;
  }

  toast.error(message);
}
  };
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div
        className="w-full max-w-md rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0f172a] shadow-xl
  max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* HEADER */}

        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-white">
            {editData ? "Edit Wastage" : "Add Wastage"}
          </h2>

          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <FiX />
          </button>
        </div>

        {/* BODY */}

        <div className="p-5 space-y-4 overflow-y-auto flex-1">
          {/* SELECT TYPE */}

          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Select Type
            </label>

            <select
              value={type}
              disabled={!!editData}
              onChange={(e) => handleTypeChange(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600
              bg-white dark:bg-[#020617]
              px-3 py-2 text-sm text-gray-800 dark:text-gray-200
              focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              <option value="">Select type</option>
              <option value="inventory">Inventory</option>
              <option value="dish">Dish</option>
              <option value="semi_finished">Prepared Item</option>
              <option value="combo">Combo</option>
            </select>
          </div>

          {/* ITEM SEARCH */}

          <div className="relative">
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Item
            </label>

            <input
              type="text"
              readOnly={!!editData}
              disabled={!type}
              value={itemSearch}
              placeholder="Search item..."
              onFocus={() => {
                if (!editData) {
                  setShowDropdown(true);
                }
              }}
              onChange={(e) => {
                const value = e.target.value;

                setItemSearch(value);

                setShowDropdown(true);

                setHighlightIndex(-1);
              }}
              onKeyDown={(e) => {
                if (!showDropdown) return;

                if (e.key === "ArrowDown") {
                  setHighlightIndex((prev) =>
                    prev < filteredItems.length - 1 ? prev + 1 : prev,
                  );
                }
                if (e.key === "ArrowUp") {
                  setHighlightIndex((prev) => (prev > 0 ? prev - 1 : prev));
                }
                if (e.key === "Enter" && highlightIndex >= 0) {
                  handleItemSelect(filteredItems[highlightIndex]);
                }
              }}
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600
    bg-white dark:bg-[#020617]
    px-3 py-2 text-sm text-gray-800 dark:text-gray-200
    focus:outline-none focus:ring-2 focus:ring-orange-400"
            />

            {showDropdown && !editData && (
              <div
                className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 dark:border-gray-700
bg-white dark:bg-[#0b1220] shadow-lg max-h-48 overflow-y-auto"
              >
                {loadingItems ? (
                  <p className="px-3 py-2 text-sm text-gray-400">Loading...</p>
                ) : filteredItems.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-gray-400">
                    No such items
                  </p>
                ) : (
                  filteredItems.map((item, index) => (
                    <div
                      key={item.id}
                      onMouseEnter={() => setHighlightIndex(index)}
                      onClick={() => handleItemSelect(item)}
                      className={`px-3 py-2 text-sm cursor-pointer
text-gray-800 dark:text-gray-200
${
  highlightIndex === index
    ? "bg-orange-500 text-white"
    : "hover:bg-gray-100 dark:hover:bg-gray-700"
}`}
                    >
                      {item.name}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
          {/* BATCH */}
          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Batch
            </label>

            <select
              value={selectedBatch?.id ? Number(selectedBatch.id) : ""}
              disabled={type !== "inventory"}
              onChange={(e) =>
                handleBatchSelect(
                  batches.find((b) => b.id === Number(e.target.value)),
                )
              }
              className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm
    focus:outline-none focus:ring-2 focus:ring-orange-400
    ${
      type !== "inventory"
        ? "bg-gray-200 text-gray-400 cursor-not-allowed border-gray-300"
        : "bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 border-gray-300 dark:border-gray-600"
    }`}
            >
              <option value="">Select Batch</option>

              {batches.map((batch) => (
                <option key={batch.id} value={batch.id}>
                  {batch.batch_number || batch.batch_no || batch.id}
                </option>
              ))}
            </select>
          </div>

          {/* QUANTITY */}

          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Quantity
            </label>

            <input
              type="number"
              value={quantity}
              min="0"
              onKeyDown={(e) => {
                if (e.key === "-" || e.key === "e") e.preventDefault();
              }}
              onChange={(e) => handleQuantityChange(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600
  bg-white dark:bg-[#020617]
  px-3 py-2 text-sm text-gray-800 dark:text-gray-200
  focus:outline-none focus:ring-2 focus:ring-orange-400"
            />

            {type === "inventory" && remainingQty > 0 && (
              <p className="text-xs text-gray-400 mt-1">
                Available: {remainingQty}
              </p>
            )}
          </div>
          {(type === "inventory" || type === "semi_finished") && (
            <div>
              <label className="text-sm text-gray-600 dark:text-gray-300">
                Unit
              </label>

              <select
                value={unit}
                onChange={(e) => {
                  const selectedUnit = e.target.value;

                  setUnit(selectedUnit);

                  if (quantity) {
                    handleQuantityChange(quantity);
                  }
                }}
                className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600
  bg-white dark:bg-[#020617]
  px-3 py-2 text-sm text-gray-800 dark:text-gray-200
  focus:outline-none focus:ring-2 focus:ring-orange-400"
              >
                <option value="">Select unit</option>

                {(() => {
                  const baseUnit = selectedItem?.unit;

                  const allowedCategory = getUnitCategory(baseUnit);

                  const allUnits = [
                    "kg",
                    "gm",
                    "mg",
                    "liter",
                    "ml",
                    "m",
                    "cm",
                    "mm",
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
                    "unit",
                  ];

                  const filteredUnits = allowedCategory
                    ? allUnits.filter(
                        (u) => getUnitCategory(u) === allowedCategory,
                      )
                    : allUnits;

                  return filteredUnits.map((u) => (
                    <option key={u} value={u}>
                      {u}
                    </option>
                  ));
                })()}
              </select>
            </div>
          )}

          {/* WASTAGE DATE */}

          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Wastage Date
            </label>

            <input
              type="date"
              value={wastageDate}
              onChange={(e) => setWastageDate(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600
bg-white dark:bg-[#020617]
px-3 py-2 text-sm text-gray-800 dark:text-gray-200
focus:outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {/* REASON */}

          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Reason
            </label>

            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-300 dark:border-gray-600
              bg-white dark:bg-[#020617]
              px-3 py-2 text-sm text-gray-800 dark:text-gray-200
              focus:outline-none focus:ring-2 focus:ring-orange-400"
            >
              <option value="">Select reason</option>
              <option value="damage">Damage</option>
              <option value="contamination">Contamination</option>
              <option value="spillage">Spillage</option>
              <option value="dish_not_ordered">Dish Not Ordered</option>
              <option value="preparation_error">Preparation Error</option>
              <option value="staff_meal">Staff Meal</option>
              <option value="sampling">Sampling</option>
              <option value="other">Other</option>
            </select>
          </div>

          {/* UPLOAD PROOF */}
          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Upload Proof
            </label>

            <label className="mt-1 flex items-center justify-between gap-2 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700">
              <div className="flex items-center gap-2">
                <FiUpload />

                <span className="text-sm">
                  {proof ? proof.name : "Upload Proof"}
                </span>
              </div>

              {proof && (
                <span className="text-xs text-green-500">Uploaded</span>
              )}

              <input
                type="file"
                hidden
                onChange={(e) => setProof(e.target.files[0])}
              />
            </label>
          </div>
        </div>

        <div className="px-5 pb-5">
          <button
            onClick={handleSubmit}
            className="w-full rounded-lg bg-orange-500 hover:bg-orange-600 text-white py-2.5 font-medium transition"
          >
            {editData ? "Update Wastage" : "Add Wastage"}
          </button>
        </div>
      </div>
    </div>
  );
}
