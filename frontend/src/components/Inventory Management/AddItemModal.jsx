import { useEffect, useState } from "react";
import { FiX, FiCalendar } from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";
import { useRef } from "react";
import { FiChevronDown } from "react-icons/fi";

const getInitialFormData = () => ({
  itemName: "",
  category: "",
  totalPrice: "",
  totalQuantity: "",
  pricePerUnit: "",
  storage: "",
  unitSelection: "kg",
  minStockAlert: "",
  currentQuantity: "",
  dateOption: "expiry",
  expiryDate: "",
  activationDateTime: "",
  shelfLifeDays: "",
  date_added: new Date().toISOString().slice(0, 16),
  is_fixed_cost: false,
});

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
export default function AddItemModal({ isOpen, onClose, editData, onSuccess }) {
  const [storages, setStorages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showUnitDropdown, setShowUnitDropdown] = useState(false);
  const dropdownRef = useRef(null);

  const [formData, setFormData] = useState(getInitialFormData());
  useEffect(() => {
    if (editData) {
      setFormData({
        itemName: editData.name || "",
        category: editData.category_type || "",
        totalPrice: editData.total_cost || "",
        totalQuantity: editData.quantity || "",
        pricePerUnit: editData.price_per_unit || "",
        storage: editData.storage_location_id || "",
        unitSelection: editData.unit || "kg",
        minStockAlert: editData.reorder_point || "",
        currentQuantity: editData.current_quantity ?? editData.quantity ?? "",
        dateOption: editData.expiry_date ? "expiry" : "shelfLife",
        expiryDate: editData.expiry_date || "",
        activationDateTime: "",
        shelfLifeDays: editData.shelf_life_in_days || "",
        date_added: editData.date_added
          ? editData.date_added.slice(0, 16)
          : new Date().toISOString().slice(0, 16),
        is_fixed_cost: editData.is_fixed_cost ?? false,
      });
    }
  }, [editData]);
  useEffect(() => {
    if (!isOpen) {
      setFormData(getInitialFormData());
    }
  }, [isOpen]);

  useEffect(() => {
    fetchStorages();
  }, [isOpen]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowUnitDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

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

  const handleChange = (e) => {
    const { name, value } = e.target;

    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };
  const handleSubmit = async (e) => {
    e.preventDefault();

    //  Capitalize item name
    const formattedName =
      formData.itemName.charAt(0).toUpperCase() +
      formData.itemName.slice(1).toLowerCase();

    const payload = {
      sku: formattedName,
      name: formattedName,
      quantity: Number(formData.totalQuantity),
      unit: formData.unitSelection,
      category_type: formData.category,
      storage_location_id: formData.storage ? Number(formData.storage) : null,
      price_per_unit: Number(formData.pricePerUnit),
      total_cost: Number(formData.totalPrice),
      current_quantity: Number(formData.currentQuantity),
      purchase_unit: formData.unitSelection,
      purchase_unit_size: 0,
      type: "",
      expiry_date: null,
      shelf_life_in_days: null,
      date_added: new Date(formData.date_added).toISOString(),
      reorder_point: Number(formData.minStockAlert),
      is_fixed_cost: formData.is_fixed_cost,
    };

    try {
      if (editData) {
        const updatePayload = {
          name: payload.name,
          unit: payload.unit,
          price_per_unit: payload.price_per_unit,
          total_cost: payload.total_cost,
          storage_location_id: formData.storage
            ? Number(formData.storage)
            : null,
          type: "",
          date_added: payload.date_added,
          category_type: formData.category,
          is_fixed_cost: formData.is_fixed_cost,
        };

        await api.put(`/inventory/${editData.id}`, updatePayload);

        toast.success("Item updated successfully ✅");
      } else {
        console.log("Payload:", payload);
        await api.post("/inventory/add_item", payload);
        toast.success("Item added successfully ✅");
      }

      onSuccess();
      onClose();
    } catch (err) {
      console.error("Save item failed", err);

      let errorMessage = "Failed to save item ❌";

      if (err?.response?.data) {
        const data = err.response.data;

        // Case 1: FastAPI validation errors (array)
        if (Array.isArray(data.detail)) {
          errorMessage = data.detail[0]?.msg || "Invalid input ❌";
        }

        //Case 2: string detail
        else if (typeof data.detail === "string") {
          errorMessage = data.detail;
        }

        // Case 3: message field
        else if (data.message) {
          errorMessage = data.message;
        } else {
          errorMessage = JSON.stringify(data);
        }
      }

      toast.error(errorMessage);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

      {/* Modal */}
      <div
        className="relative w-full max-w-lg bg-white dark:bg-[#0f172a] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-black dark:text-white">
            {editData
              ? `Edit ${editData.name || "Inventory Item"}`
              : "Add Inventory Item"}
          </h2>

          <button
            onClick={onClose}
            className="text-2xl text-gray-700 dark:text-gray-300 hover:text-black dark:hover:text-white"
          >
            <FiX />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Item Name + Category */}
          <div className="grid grid-cols-2 gap-4">
            {/* Item Name */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Item Name
              </label>

              <input
                type="text"
                name="itemName"
                placeholder="eg. Rice"
                value={formData.itemName}
                onChange={handleChange}
                className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:ring-2 focus:ring-orange-400 outline-none"
                required
              />
            </div>

            {/* Category */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Category
              </label>

              <select
                name="category"
                value={formData.category}
                onChange={handleChange}
                required
                className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200"
              >
                <option value="">Select Category Type</option>
                <option value="perishable">Perishable</option>
                <option value="non_perishable">Non-Perishable</option>
              </select>
            </div>
          </div>

          {/* Unit + Storage */}
          <div className="grid grid-cols-2 gap-4">
            {/* Unit */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Unit
              </label>

              <div className="relative" ref={dropdownRef}>
                {/* Input */}
                <div
                  onClick={() => setShowUnitDropdown((prev) => !prev)}
                  className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 
      bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 
      cursor-pointer flex items-center justify-between"
                >
                  <span>
                    {(() => {
                      const selected = UNIT_OPTIONS.find(
                        (u) => u.value === formData.unitSelection,
                      );
                      return selected
                        ? `${selected.label} (${selected.value})`
                        : "Select Unit";
                    })()}{" "}
                  </span>

                  <FiChevronDown
                    className={`text-gray-500 transition-transform duration-200 ${
                      showUnitDropdown ? "rotate-180" : ""
                    }`}
                  />
                </div>

                {/* Dropdown */}
                {showUnitDropdown && (
                  <div
                    className="absolute z-50 mt-2 w-full max-h-48 overflow-y-auto 
      bg-white dark:bg-[#020617] border border-gray-200 dark:border-gray-700 
      rounded-xl shadow-lg"
                  >
                    {UNIT_OPTIONS.map((unit) => (
                      <div
                        key={unit.value}
                        onClick={() => {
                          setFormData((prev) => ({
                            ...prev,
                            unitSelection: unit.value,
                          }));
                          setShowUnitDropdown(false);
                        }}
                        className={`px-3 py-2 text-sm cursor-pointer transition
              ${
                formData.unitSelection === unit.value
                  ? "bg-orange-500 text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
                      >
                        {unit.label} ({unit.value})
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Storage */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Storage (Optional)
              </label>

              <select
                name="storage"
                value={formData.storage}
                onChange={handleChange}
                className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200"
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

          {/* Fixed Cost Checkbox */}
          <div className="flex items-center gap-2 mt-2">
            <input
              type="checkbox"
              id="is_fixed_cost"
              checked={formData.is_fixed_cost}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  is_fixed_cost: e.target.checked,
                }))
              }
              className="w-4 h-4 accent-orange-500 cursor-pointer"
            />

            <label
              htmlFor="is_fixed_cost"
              className="text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
            >
              Allow manual price entry (Fixed Cost)
            </label>
          </div>

          {/* Date Added */}
          {/* Date Added */}
<div>
  <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
    Date Added
  </label>

  <div
    className="
      mt-1 flex items-center gap-2
      px-3 py-2.5
      rounded-xl
      border border-gray-300 dark:border-gray-700
      bg-white dark:bg-[#020617]
    "
  >
    <FiCalendar
      className="text-gray-500 cursor-pointer"
      onClick={() =>
        document
          .getElementById("inventory-date-added")
          ?.showPicker()
      }
    />

    <input
      id="inventory-date-added"
      type="datetime-local"
      name="date_added"
      value={formData.date_added}
      onChange={handleChange}
      required
      className="
        w-full
        outline-none
        bg-transparent
        text-gray-800 dark:text-gray-200
        custom-date-input
      "
    />
  </div>
</div>

          {/* Button */}
          <div className="pt-3">
            <button
              type="submit"
              className="w-full py-2.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-lg font-semibold transition"
            >
              {editData ? "Update Item" : "Add Item"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
