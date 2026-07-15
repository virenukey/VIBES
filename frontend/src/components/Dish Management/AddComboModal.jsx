import React, { useState, useEffect } from "react";
import { FiSearch, FiX } from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function AddComboModal({
  isOpen,
  onClose,
  editData,
  fetchCombos,
}) {
  const [search, setSearch] = useState("");
  const [comboName, setComboName] = useState("");
  const [category, setCategory] = useState("Meal Combo");
  const [categories, setCategories] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sellingPrice, setSellingPrice] = useState("");
  const [dishes, setDishes] = useState([]);

  const [preparedItems, setPreparedItems] = useState([]);

  const [inventoryItems, setInventoryItems] = useState([]);

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

  const getUnitCategory = (unit) => {
    for (const category in UNIT_CATEGORIES) {
      if (UNIT_CATEGORIES[category].includes(unit)) {
        return category;
      }
    }

    return null;
  };

  const handleSelectItem = (item) => {
    const exists = selectedItems.find(
      (selected) => selected.uniqueId === item.uniqueId,
    );

    if (exists) {
      setSelectedItems((prev) =>
        prev.filter((selected) => selected.uniqueId !== item.uniqueId),
      );
    } else {
      setSelectedItems((prev) => [
        ...prev,
        {
          ...item,

          uniqueId: item.uniqueId,

          quantity: "",

          unit: item.baseUnit || "pcs",
        },
      ]);
    }
  };

  const updateItemQuantity = (uniqueId, quantity) => {
    setSelectedItems((prev) =>
      prev.map((item) =>
        item.uniqueId === uniqueId
          ? {
              ...item,
              quantity,
            }
          : item,
      ),
    );
  };

  const updateItemUnit = (uniqueId, unit) => {
    setSelectedItems((prev) =>
      prev.map((item) =>
        item.uniqueId === uniqueId
          ? {
              ...item,
              unit,
            }
          : item,
      ),
    );
  };

  const handleSubmit = async () => {
    if (!comboName.trim()) {
      toast.error("Combo name is required ❌");
      return;
    }

    if (!category || category === "Meal Combo") {
      toast.error("Please select combo category ❌");
      return;
    }

    if (sellingPrice === "" || Number(sellingPrice) <= 0) {
      toast.error("Please enter valid selling price ❌");
      return;
    }

    if (selectedItems.length === 0) {
      toast.error("Please select at least one item ❌");
      return;
    }

    const invalidItem = selectedItems.find(
      (item) => item.quantity === "" || Number(item.quantity) <= 0,
    );

    if (invalidItem) {
      toast.error(`Please enter valid quantity for ${invalidItem.name}`);

      return;
    }
    try {
      setLoading(true);

      const payload = {
        name: comboName,

        type_id: Number(category),

        selling_price: Number(sellingPrice),

        is_active: true,

        items: selectedItems.map((item) => ({
          dish_id: item.type === "dish" ? item.id : null,

          semi_finished_id: item.type === "prepared_item" ? item.id : null,

          ingredient_id: item.type === "inventory" ? item.id : null,

          quantity: Number(item.quantity),

          unit: item.unit || "piece",
        })),
      };

      if (editData) {
        await api.patch(`/dish/${editData.id}`, payload);
      } else {
        await api.post("/dish/", payload);
      }

      fetchCombos();

      toast.success(
        editData ? "Combo updated successfully" : "Combo created successfully",
      );

      onClose();
    } catch (err) {
      console.error(
        editData ? "Failed to update combo" : "Failed to create combo",
        err,
      );

      toast.error(
        err?.response?.data?.detail?.message || "Something went wrong",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (editData) {
      setSelectedItems(
        editData.items.map((item) => {
          const itemId =
            item.dish_id || item.semi_finished_id || item.ingredient_id;
          return {
            id: itemId,

            uniqueId:
              item.item_type === "dish"
                ? `dish-${itemId}`
                : item.item_type === "semi_finished"
                  ? `prepared-${itemId}`
                  : `inventory-${itemId}`,

            name: item.item_name,

            type:
              item.item_type === "semi_finished"
                ? "prepared_item"
                : item.item_type === "ingredient"
                  ? "inventory"
                  : item.item_type,

            quantity: item.quantity,

            unit: item.unit,

            price: item.cost_per_unit,
          };
        }),
      );
      setComboName(editData.name || "");
      setCategory(editData.type_id || "");
      setSellingPrice(editData.selling_price || "");
    } else {
      setSelectedItems([]);
      setComboName("");
      setSellingPrice("");
      setCategory("Meal Combo");
    }
  }, [editData]);

  useEffect(() => {
    if (!isOpen) {
      // Reset all form fields
      setSearch("");
      setComboName("");
      setCategory("Meal Combo");
      setSelectedItems([]);
      setSellingPrice("");
    }
  }, [isOpen]);

  useEffect(() => {
    fetchDishTypes();
  }, []);

  useEffect(() => {
    fetchDishes();

    fetchPreparedItems();

    fetchInventoryItems();
  }, [search]);

  const fetchDishTypes = async () => {
    try {
      const res = await api.get("/dish/get_dish_types");

      setCategories(res.data.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const fetchDishes = async () => {
    try {
      const res = await api.get("/dish/get-dishes-with-ingredients", {
        params: {
          page: 1,
          page_size: 100,
          search,
        },
      });

      const formattedDishes = (res.data.dishes || []).map((item) => ({
        id: item.id,

        uniqueId: `dish-${item.id}`,

        name: item.name,

        category: item.category_name,

        price: item.selling_price,
        baseUnit: "pcs",

        type: "dish",
      }));

      setDishes(formattedDishes);
    } catch (err) {
      console.error("Failed to fetch dishes", err);
    }
  };

  const fetchPreparedItems = async () => {
    try {
      const res = await api.get("/dish/semi-finished-ingredients", {
        params: {
          page: 1,
          page_size: 100,
          search,
          is_active: true,
        },
      });

      const formattedPrepared = (res.data.data || []).map((item) => ({
        id: item.semi_finished_id,

        uniqueId: `prepared-${item.semi_finished_id}`,

        name: item.name,

        category: "Prepared Item",

        price: item.unit_cost || 0,
        baseUnit: item.yield_unit || item.unit,

        type: "prepared_item",
      }));

      setPreparedItems(formattedPrepared);
    } catch (err) {
      console.error("Failed to fetch prepared items", err);
    }
  };

  const fetchInventoryItems = async () => {
    try {
      const res = await api.get("/inventory/", {
        params: {
          page: 1,
          page_size: 100,
          search,
        },
      });

      const formattedInventory = (res.data.data || []).map((item) => ({
        id: item.id,

        uniqueId: `inventory-${item.id}`,

        name: item.name,

        category: item.item_category || "Inventory",

        price: item.price_per_unit || 0,
        baseUnit: item.unit,

        type: "inventory",
      }));

      setInventoryItems(formattedInventory);
    } catch (err) {
      console.error("Failed to fetch inventory items", err);
    }
  };

  const renderSection = (title, items, emptyText) => {
    return (
      <div>
        {/* TITLE */}

        <div className="flex items-center gap-2 mb-3">
          <h3 className="text-sm sm:text-base font-semibold text-gray-800 dark:text-gray-200">
            {title}
          </h3>

          <span className="text-xs text-gray-400">({items.length})</span>
        </div>

        {/* EMPTY */}

        {items.length === 0 ? (
          <div
            className="
          rounded-2xl border border-dashed
          border-gray-300 dark:border-gray-700
          p-6 text-center
          text-sm text-gray-500 dark:text-gray-400
          bg-gray-50 dark:bg-[#020617]
        "
          >
            {emptyText}
          </div>
        ) : (
          <div
            className="
          rounded-2xl
          border border-gray-200 dark:border-gray-700
          overflow-hidden
        "
          >
            <div
              className="
            max-h-[220px]
            overflow-y-auto

            divide-y divide-gray-200
            dark:divide-gray-800
          "
            >
              {items.map((item) => {
                const selectedItem = selectedItems.find(
                  (selected) => selected.uniqueId === item.uniqueId,
                );

                const isSelected = !!selectedItem;

                return (
                  <label
                    key={`${item.type}-${item.id}`}
                    className="
                flex items-center justify-between
                gap-4

                px-4 py-4

                cursor-pointer

                bg-white dark:bg-[#0f172a]

                hover:bg-orange-50
                dark:hover:bg-orange-900/10

                transition
              "
                  >
                    {/* LEFT */}

                    <div className="flex items-start gap-4">
                      <input
                        type="checkbox"
                        checked={selectedItems.some(
                          (selected) => selected.uniqueId === item.uniqueId,
                        )}
                        onChange={() => handleSelectItem(item)}
                        className="
    mt-1 h-5 w-5 rounded
    border-gray-300
    accent-orange-500
    focus:ring-orange-400
  "
                      />

                      <div>
                        <p className="font-semibold text-gray-900 dark:text-white">
                          {item.name}
                        </p>

                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {item.category}
                        </p>
                      </div>
                    </div>

                    {/* RIGHT */}

                    <div className="flex flex-col items-end gap-3">
                      {/* PRICE */}

                      <p className="whitespace-nowrap text-sm ">
                        <span className="text-gray-500 dark:text-gray-400 font-medium">
                          Selling Price:
                        </span>{" "}
                        <span className="font-semibold text-orange-500">
                          ₹{item.price}
                        </span>
                      </p>

                      {/* QTY CONTROLS */}

                      {isSelected && (
                        <div className="flex flex-col gap-2">
                          {/* QUANTITY */}
                          <input
                            type="number"
                            min="0"
                            placeholder="Enter qty"
                            value={selectedItem.quantity}
                            onClick={(e) => e.preventDefault()}
                            onKeyDown={(e) => {
                              if (
                                e.key === "-" ||
                                e.key === "+" ||
                                e.key === "e"
                              ) {
                                e.preventDefault();
                              }
                            }}
                            onPaste={(e) => {
                              const pasteData = e.clipboardData.getData("text");

                              if (
                                pasteData.includes("-") ||
                                pasteData.includes("+") ||
                                pasteData.includes("e")
                              ) {
                                e.preventDefault();
                              }
                            }}
                            onChange={(e) => {
                              const value = e.target.value;

                              if (value === "") {
                                updateItemQuantity(item.uniqueId, "");

                                return;
                              }

                              const numericValue = Number(value);

                              if (numericValue >= 0) {
                                updateItemQuantity(item.uniqueId, numericValue);
                              }
                            }}
                            className={`
    w-28 h-10 px-3 rounded-lg

    border

    ${
      selectedItem.quantity === "" || Number(selectedItem.quantity) <= 0
        ? "border-red-500"
        : "border-gray-200 dark:border-gray-700"
    }

    bg-white dark:bg-[#020617]

    text-gray-900 dark:text-white

    placeholder:text-gray-400
    dark:placeholder:text-gray-500

    outline-none

    focus:ring-2 focus:ring-orange-400
  `}
                          />

                          {/* UNIT */}

                          <select
                            value={selectedItem.unit}
                            onClick={(e) => e.preventDefault()}
                            onChange={(e) =>
                              updateItemUnit(item.uniqueId, e.target.value)
                            }
                            className="
        h-9 px-3 rounded-lg

        border border-gray-200
        dark:border-gray-700

        bg-white dark:bg-[#020617]

        text-sm

        text-gray-900 dark:text-white

        outline-none

        focus:ring-2 focus:ring-orange-400
      "
                          >
                            {(() => {
                              const baseUnit = item.baseUnit;

                              const allowedCategory = getUnitCategory(baseUnit);

                              const filteredUnits = allowedCategory
                                ? UNIT_OPTIONS.filter(
                                    (u) =>
                                      getUnitCategory(u.value) ===
                                      allowedCategory,
                                  )
                                : UNIT_OPTIONS;

                              return filteredUnits.map((unit) => {
                                const displayLabel =
                                  item.type === "dish" && unit.value === "pcs"
                                    ? "Plate"
                                    : unit.label;

                                return (
                                  <option key={unit.value} value={unit.value}>
                                    {displayLabel}
                                  </option>
                                );
                              });
                            })()}
                          </select>
                        </div>
                      )}
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  };

  if (!isOpen) return null;

  return (
    <div
      className="
  fixed inset-0 z-50
  flex items-center justify-center
  p-2 sm:p-4
"
    >
      {/* BACKDROP */}

      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* MODAL */}

      <div
        className="
  relative
  w-full
  max-w-[95vw]
  sm:max-w-2xl
  lg:max-w-3xl
  xl:max-w-4xl

  max-h-[95vh]

  rounded-2xl sm:rounded-3xl

  bg-white dark:bg-[#0f172a]

  border border-gray-200 dark:border-gray-800

  shadow-2xl

  overflow-hidden

  flex flex-col
"
      >
        {/* HEADER */}

        <div
          className="flex items-start justify-between
          px-4 sm:px-6 py-4 sm:py-5 border-b border-gray-200 dark:border-gray-800"
        >
          <div>
            <h2 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white">
              {editData ? `Edit: ${editData.name}` : "Add New Combo"}
            </h2>

            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Select 2+ dishes to bundle
            </p>
          </div>

          {/* CLOSE BUTTON */}

          <button
            onClick={onClose}
            className="h-10 w-10 flex items-center justify-center rounded-xl
            bg-gray-100 dark:bg-gray-800
            hover:bg-red-50 dark:hover:bg-red-900/20
            transition"
          >
            <FiX className="text-gray-600 dark:text-gray-300 text-lg" />
          </button>
        </div>

        {/* BODY */}

        <div
          className="
  flex-1 overflow-y-auto

  p-4 sm:p-6

  space-y-5 sm:space-y-6
"
        >
          {/* COMBO NAME */}

          <div>
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Combo Name <span className="text-red-500">*</span>
            </label>

            <input
              type="text"
              value={comboName}
              onChange={(e) => setComboName(e.target.value)}
              placeholder="e.g. Thali + Roll Combo"
              className="w-full px-4 py-3 rounded-xl
  border border-gray-200 dark:border-gray-700
  bg-white dark:bg-[#020617]
  text-gray-900 dark:text-white
  placeholder:text-gray-400 dark:placeholder:text-gray-500
  outline-none
  focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {/* CATEGORY */}

          <div>
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Combo Category
            </label>

            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full px-4 py-3 rounded-xl
  border border-gray-200 dark:border-gray-700
  bg-white dark:bg-[#020617]
  text-gray-900 dark:text-white
  outline-none
  focus:ring-2 focus:ring-orange-400"
            >
              <option value="">Select Category</option>

              {categories.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>

          {/* SELLING PRICE */}

          <div>
            <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
              Combo Selling Price <span className="text-red-500">*</span>
            </label>

            <input
              type="number"
              value={sellingPrice}
              onChange={(e) => setSellingPrice(e.target.value)}
              placeholder="Enter combo selling price"
              className="w-full px-4 py-3 rounded-xl
    border border-gray-200 dark:border-gray-700
    bg-white dark:bg-[#020617]
    text-gray-900 dark:text-white
    placeholder:text-gray-400 dark:placeholder:text-gray-500
    outline-none
    focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {/* SELECTED ITEMS */}

          {selectedItems.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="block text-sm font-semibold text-gray-700 dark:text-gray-300">
                  Selected Items
                </label>

                <span className="text-xs text-gray-400">
                  {selectedItems.length} selected
                </span>
              </div>

              <div
                className="
        rounded-2xl
        border border-gray-200 dark:border-gray-700
        bg-white dark:bg-[#020617]
        overflow-hidden
      "
              >
                <div className="max-h-[280px] overflow-y-auto divide-y divide-gray-200 dark:divide-gray-800">
                  {selectedItems.map((item) => {
                    let selectedBaseUnit = item.baseUnit;

                    // DISH
                    if (item.type === "dish") {
                      selectedBaseUnit = "pcs";
                    }

                    // PREPARED ITEM
                    else if (item.type === "prepared_item") {
                      const preparedMatch = preparedItems.find(
                        (p) => p.id === item.id,
                      );

                      selectedBaseUnit =
                        preparedMatch?.baseUnit ||
                        preparedMatch?.yield_unit ||
                        preparedMatch?.unit;
                    }

                    // INVENTORY
                    else if (item.type === "inventory") {
                      const inventoryMatch = inventoryItems.find(
                        (inv) => inv.id === item.id,
                      );

                      selectedBaseUnit =
                        inventoryMatch?.baseUnit || inventoryMatch?.unit;
                    }

                    const allowedCategory = getUnitCategory(selectedBaseUnit);

                    const filteredUnits = allowedCategory
                      ? UNIT_OPTIONS.filter(
                          (u) => getUnitCategory(u.value) === allowedCategory,
                        )
                      : [];

                    return (
                      <div
                        key={item.uniqueId}
                        className="
    grid
    grid-cols-1
    lg:grid-cols-[minmax(220px,1fr)_110px_140px_40px]
    items-center
    gap-3
    px-4 py-4
  "
                      >
                        {/* LEFT */}
                        <div className="min-w-0">
                          <p className="font-semibold text-gray-900 dark:text-white">
                            {item.name}
                          </p>

                          <p className="text-xs text-gray-500 dark:text-gray-400 capitalize">
                            {item.type.replace("_", " ")}
                          </p>
                        </div>

                        {/* RIGHT */}
                        <div className="contents">
                          {/* QUANTITY */}
                          <input
                            type="number"
                            min="0"
                            placeholder="Qty"
                            value={item.quantity}
                            onKeyDown={(e) => {
                              if (
                                e.key === "-" ||
                                e.key === "+" ||
                                e.key === "e"
                              ) {
                                e.preventDefault();
                              }
                            }}
                            onChange={(e) => {
                              const value = e.target.value;

                              if (value === "") {
                                updateItemQuantity(item.uniqueId, "");
                                return;
                              }

                              const numericValue = Number(value);

                              if (numericValue >= 0) {
                                updateItemQuantity(item.uniqueId, numericValue);
                              }
                            }}
                            className={`
                    w-28 h-10 px-3 rounded-xl border
                    ${
                      item.quantity === "" || Number(item.quantity) <= 0
                        ? "border-red-500"
                        : "border-gray-200 dark:border-gray-700"
                    }
                    bg-white dark:bg-[#0f172a]
                    text-gray-900 dark:text-white
                    outline-none
                    focus:ring-2 focus:ring-orange-400
                  `}
                          />

                          {/* UNIT */}
                          <select
                            value={item.unit}
                            onChange={(e) =>
                              updateItemUnit(item.uniqueId, e.target.value)
                            }
                            className="
                    h-10 px-3 rounded-xl
                    border border-gray-200 dark:border-gray-700
                    bg-white dark:bg-[#0f172a]
                    text-sm text-gray-900 dark:text-white
                    outline-none
                    focus:ring-2 focus:ring-orange-400
                  "
                          >
                            {filteredUnits.map((unit) => {
                              const displayLabel =
                                item.type === "dish" && unit.value === "pcs"
                                  ? "Plate"
                                  : unit.label;

                              return (
                                <option key={unit.value} value={unit.value}>
                                  {displayLabel}
                                </option>
                              );
                            })}
                          </select>

                          {/* REMOVE */}
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedItems((prev) =>
                                prev.filter(
                                  (selected) =>
                                    selected.uniqueId !== item.uniqueId,
                                ),
                              )
                            }
                            className="
                    h-10 w-10
                    flex items-center justify-center
                    rounded-xl
                    hover:bg-red-50
                    dark:hover:bg-red-900/20
                    transition
                  "
                          >
                            <FiX className="text-red-500 text-lg" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* DISHES */}

          {/* SEARCH */}

          <div className="relative">
            <FiSearch
              className="
    absolute left-3 top-1/2
    -translate-y-1/2
    text-gray-400
  "
            />

            <input
              type="text"
              placeholder="Search dishes, prepared items, inventory..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="
    w-full

    pl-10 pr-4 py-3

    rounded-xl

    border border-gray-200
    dark:border-gray-700

    bg-white dark:bg-[#020617]

    text-gray-900 dark:text-white

    placeholder:text-gray-400
    dark:placeholder:text-gray-500

    outline-none

    focus:ring-2 focus:ring-orange-400
  "
            />
          </div>

          {/* DISHES */}

          {/* SEARCH MODE */}
          {search.trim() ? (
            <>
              {inventoryItems.length > 0 &&
                renderSection(
                  "Select Inventory Items",
                  inventoryItems,
                  "No inventory items found",
                )}

              {dishes.length > 0 &&
                renderSection("Select Dishes", dishes, "No dishes found")}

              {preparedItems.length > 0 &&
                renderSection(
                  "Select Prepared Items",
                  preparedItems,
                  "No prepared items found",
                )}

              {/* NOTHING FOUND */}
              {inventoryItems.length === 0 &&
                dishes.length === 0 &&
                preparedItems.length === 0 && (
                  <div
                    className="
            rounded-2xl border border-dashed
            border-gray-300 dark:border-gray-700
            p-8 text-center
            text-sm text-gray-500 dark:text-gray-400
            bg-gray-50 dark:bg-[#020617]
          "
                  >
                    No matching items found
                  </div>
                )}
            </>
          ) : (
            <>
              {renderSection("Select Dishes", dishes, "No dishes found")}

              {renderSection(
                "Select Prepared Items",
                preparedItems,
                "No prepared items found",
              )}

              {renderSection(
                "Select Inventory Items",
                inventoryItems,
                "No inventory items found",
              )}
            </>
          )}
        </div>

        {/* FOOTER */}

        <div
          className="
  flex flex-col-reverse sm:flex-row
  items-stretch sm:items-center
  justify-end
  gap-3

  px-4 sm:px-6
  py-4 sm:py-5

  border-t border-gray-200 dark:border-gray-800
"
        >
          {/* CANCEL */}

          <button
            onClick={onClose}
            className="w-full sm:w-auto
px-5 py-2.5 rounded-xl
            border border-gray-300 dark:border-gray-700
            bg-white dark:bg-[#0f172a]
            text-gray-700 dark:text-gray-300
            hover:bg-gray-100 dark:hover:bg-gray-800
            transition"
          >
            Cancel
          </button>

          {/* SAVE */}

          <button
            onClick={handleSubmit}
            disabled={loading}
            className="w-full sm:w-auto
px-5 py-2.5 rounded-xl
  bg-orange-500 hover:bg-orange-600
  disabled:opacity-50
  text-white font-semibold
  shadow-md hover:shadow-lg
  transition"
          >
            {loading ? "Saving..." : editData ? "Update Combo" : "Save Combo"}
          </button>
        </div>
      </div>
    </div>
  );
}
