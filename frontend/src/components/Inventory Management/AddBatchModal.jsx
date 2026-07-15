import { useState, useEffect, useRef } from "react";
import { FiX, FiCalendar } from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";
import { FiChevronDown } from "react-icons/fi";

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

const getInitialBatchData = (unit = "kg") => ({
  quantity_received: "",
  unit_cost: "",
  total_cost: "",
  packets: "",
  pieces: "",
  expiry_date: "",
  date_added: "",
  quantity_remaining: "",
  unit,
});

export default function AddBatchModal({
  isOpen,
  onClose,
  item,
  onSuccess,
  editData,
}) {
  const [formData, setFormData] = useState(getInitialBatchData());
  const dateInputRef = useRef(null);
  const dateAddedRef = useRef(null);
  const [showUnitDropdown, setShowUnitDropdown] = useState(false);
  const dropdownRef = useRef(null);
  const [activeField, setActiveField] = useState(null);
  const [costSource, setCostSource] = useState(null);

  useEffect(() => {
    if (isOpen) {
      setActiveField(null);
      if (editData) {
        setFormData({
          quantity_received: editData.quantity_received || "",
          unit_cost: editData.unit_cost || "",
          total_cost: editData.total_cost || "",
          packets: editData.packets || "",
          pieces: editData.pieces || "",
          expiry_date: editData.expiry_date?.split("T")[0] || "",
          date_added: editData.date_added
            ? new Date(editData.date_added).toISOString().slice(0, 16)
            : "",
          unit: editData.unit || item?.unit || "kg",
          quantity_remaining: editData.quantity_remaining || "",
        });

        if (editData.unit_cost && !editData.total_cost) {
          setCostSource("unit");
        } else if (!editData.unit_cost && editData.total_cost) {
          setCostSource("total");
        } else {
          setCostSource("total");
        }
      } else {
        setCostSource(null);
        setFormData(getInitialBatchData(item?.unit || "kg"));
      }
    }
  }, [isOpen, item, editData]);

  const handleChange = (e) => {
    const { name, value } = e.target;

    // block negative
    if (value !== "" && Number(value) < 0) {
      toast.error("Negative values not allowed ❌");
      return;
    }

    //track active field
    if (name === "total_cost" || name === "unit_cost") {
      setActiveField(name);
    }

    setFormData((prev) => {
      let updated = { ...prev, [name]: value };

      const qty = Number(updated.quantity_received || 0);

      //  auto calculation
      if (name === "total_cost" && value !== "") {
        updated.unit_cost = qty ? (Number(value) / qty).toFixed(2) : "";
      }

      if (name === "unit_cost" && value !== "") {
        updated.total_cost = qty ? (Number(value) * qty).toFixed(2) : "";
      }

      return updated;
    });
  };
  const handleSubmit = async (e) => {
    e.preventDefault();

    const qty = Number(formData.quantity_received || 0);
    const unitCost = Number(formData.unit_cost || 0);
    const totalCost = Number(formData.total_cost || 0);

    //  NEGATIVE VALUE VALIDATION
    if (
      qty < 0 ||
      unitCost < 0 ||
      totalCost < 0 ||
      Number(formData.packets || 0) < 0 ||
      Number(formData.pieces || 0) < 0
    ) {
      toast.error("Negative values are not allowed ❌");
      return;
    }
    if (!formData.unit_cost && !formData.total_cost) {
      toast.error("Enter Cost/Unit or Total Cost ❌");
      return;
    }

    if (!qty) {
      toast.error("Quantity is required");
      return;
    }

    // DATE VALIDATION
    const expiry = new Date(formData.expiry_date);
    const added = new Date(formData.date_added);
    const today = new Date();

    //  Invalid date check
    if (isNaN(expiry.getTime()) || isNaN(added.getTime())) {
      toast.error("Invalid date format ❌");
      return;
    }

    // Year validation
    const expiryYear = expiry.getFullYear();
    const addedYear = added.getFullYear();

    if (expiryYear < 2000 || expiryYear > 2100) {
      toast.error("Expiry year must be between 2000 and 2100 ❌");
      return;
    }

    if (addedYear < 2000 || addedYear > 2100) {
      toast.error("Date added year must be valid ❌");
      return;
    }

    if (added > today) {
      toast.error("Date added cannot be in the future ❌");
      return;
    }

    //  Normalize both to only DATE (ignore time)
    const addedDateOnly = new Date(
      added.getFullYear(),
      added.getMonth(),
      added.getDate(),
    );

    const expiryDateOnly = new Date(
      expiry.getFullYear(),
      expiry.getMonth(),
      expiry.getDate(),
    );

    if (addedDateOnly > expiryDateOnly) {
      toast.error("Date added cannot be after expiry date ❌");
      return;
    }

    if (formData.unit === "packet") {
      if (!formData.packets) {
        toast.error("Packets is required when unit is Packet ❌");
        return;
      }

      if (!formData.pieces) {
        toast.error("Pieces is required when unit is Packet ❌");
        return;
      }
    }
    const packets = Number(formData.packets || 0);
    const pieces = Number(formData.pieces || 0);
    const totalCostValue = Number(formData.total_cost || 0);

    const totalPieces = packets && pieces ? packets * pieces : pieces;

    // calculate price per piece
    const pricePerPiece =
      totalPieces > 0 ? (totalCostValue / totalPieces).toFixed(2) : null;
    const payload = {
      batch_number: editData?.batch_number || `B-${Date.now()}`,

      expiry_date: new Date(formData.expiry_date).toISOString(),

      quantity_received: Number(formData.quantity_received),

      packets,
      pieces,
      total_pieces: totalPieces,

      unit_cost: formData.unit_cost ? Number(formData.unit_cost) : null,
      total_cost: totalCostValue,

      price_per_packet:
        packets > 0 ? Number((totalCostValue / packets).toFixed(2)) : null,
      price_per_piece: pricePerPiece ? Number(pricePerPiece) : null,

      unit: formData.unit,
      date_added: new Date(formData.date_added).toISOString(),
    };
    try {
      if (editData) {
        await api.put(
          `/inventory/items/${item.id}/update-batch/${editData.id}`,
          payload,
        );

        toast.success("Stock updated successfully ✏️");
      } else {
        await api.post(`/inventory/items/${item.id}/batches`, payload);

        toast.success("Stock added successfully");
      }

      onSuccess?.();
      onClose();
    } catch (err) {
      console.error(err);

      let errorMessage = "Failed to save batch ❌";

      if (err?.response?.data) {
        const data = err.response.data;

        if (Array.isArray(data.detail)) {
          errorMessage = data.detail[0]?.msg || errorMessage;
        } else if (typeof data.detail === "string") {
          errorMessage = data.detail;
        } else if (data.message) {
          errorMessage = data.message;
        }
      }

      toast.error(errorMessage);
    }
  };

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowUnitDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      {/* Modal */}
      <div className="relative w-full max-w-md bg-white dark:bg-[#0f172a] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800 p-5">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-black dark:text-white">
            {editData ? "Edit Stock" : "Add Stock"}{" "}
            {item?.name ? `for ${item.name}` : ""}
          </h2>

          <button onClick={onClose}>
            <FiX className="text-xl text-gray-800 dark:text-gray-200" />
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          {/* 🔹 Row 1: Quantity + Unit */}
          <div className="grid grid-cols-2 gap-4">
            {/* Quantity */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Quantity
              </label>
              <input
                type="number"
                name="quantity_received"
                placeholder="eg. 10"
                value={formData.quantity_received}
                onChange={handleChange}
                min="0"
                onKeyDown={(e) => {
                  if (e.key === "-" || e.key === "e") {
                    e.preventDefault();
                  }
                }}
                required
                className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200"
              />
            </div>

            {/* Unit */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Unit
              </label>

              <div className="relative" ref={dropdownRef}>
                <div
                  onClick={() => setShowUnitDropdown((prev) => !prev)}
                  className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] flex justify-between cursor-pointer"
                >
                  <span className="text-gray-800 dark:text-gray-200">
                    {(() => {
                      const selected = UNIT_OPTIONS.find(
                        (u) => u.value === formData.unit,
                      );
                      return selected
                        ? `${selected.label} (${selected.value})`
                        : "Select Unit";
                    })()}
                  </span>

                  <FiChevronDown
                    className={`transition ${showUnitDropdown ? "rotate-180" : ""}`}
                  />
                </div>

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
                            unit: unit.value,
                          }));
                          setShowUnitDropdown(false);
                        }}
                        className={`px-3 py-2 text-sm cursor-pointer transition
          ${
            formData.unit === unit.value
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
          </div>

          {/* 🔹 Row 2: Total Cost + Cost/Unit */}
          <div className="grid grid-cols-2 gap-4">
            {/* Total Cost */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Total Cost
              </label>
              <input
                type="number"
                name="total_cost"
                placeholder="Enter total cost"
                value={formData.total_cost}
                onChange={handleChange}
                disabled={
                  editData
                    ? costSource !== "total"
                    : activeField === "unit_cost"
                }
                min="0"
                onKeyDown={(e) => {
                  if (e.key === "-" || e.key === "e") {
                    e.preventDefault();
                  }
                }}
                className={`mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 
  bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 
  ${
    editData
      ? costSource !== "total"
        ? "opacity-50 cursor-not-allowed"
        : ""
      : activeField === "unit_cost"
        ? "opacity-50 cursor-not-allowed"
        : ""
  }`}
              />
            </div>

            {/* Cost / Unit */}
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Cost / Unit
              </label>
              <input
                type="number"
                name="unit_cost"
                placeholder="eg. 50"
                value={formData.unit_cost}
                onChange={handleChange}
                disabled={
                  editData
                    ? costSource !== "unit"
                    : activeField === "total_cost"
                }
                min="0"
                onKeyDown={(e) => {
                  if (e.key === "-" || e.key === "e") {
                    e.preventDefault();
                  }
                }}
                className={`mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 
  bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 
  ${
    editData
      ? costSource !== "unit"
        ? "opacity-50 cursor-not-allowed"
        : ""
      : activeField === "total_cost"
        ? "opacity-50 cursor-not-allowed"
        : ""
  }`}
              />
            </div>
          </div>

          {/* 🔹 Row 3: Packets + Pieces */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Packets
              </label>
              <input
                type="number"
                name="packets"
                required={formData.unit === "packet"}
                placeholder="eg. 5"
                value={formData.packets}
                onChange={handleChange}
                min="0"
                onKeyDown={(e) => {
                  if (e.key === "-" || e.key === "e") {
                    e.preventDefault();
                  }
                }}
                className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-gray -700 dark:text-gray-300">
                Pieces
              </label>
              <input
                type="number"
                name="pieces"
                placeholder="eg. 10"
                required={formData.unit === "packet"}
                value={formData.pieces}
                onChange={handleChange}
                min="0"
                onKeyDown={(e) => {
                  if (e.key === "-" || e.key === "e") {
                    e.preventDefault();
                  }
                }}
                className="mt-1 w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none"
              />
            </div>
          </div>

          {/* 🔹 Date Added */}
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Date Added
            </label>

            <div className="mt-1 flex items-center gap-2 px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617]">
              <FiCalendar
                className="text-gray-500 cursor-pointer"
                onClick={() => dateAddedRef.current?.showPicker()}
              />
              <input
                ref={dateAddedRef}
                type="datetime-local"
                name="date_added"
                value={formData.date_added}
                onChange={handleChange}
                required
                className="w-full outline-none bg-transparent text-gray-800 dark:text-gray-200 custom-date-input"
              />
            </div>
          </div>

          {/* 🔹 Expiry Date */}
          <div>
            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Expiry Date
            </label>

            <div className="mt-1 flex items-center gap-2 px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617]">
              <FiCalendar
                className="text-gray-500 cursor-pointer"
                onClick={() => dateInputRef.current?.showPicker()}
              />
              <input
                ref={dateInputRef}
                type="date"
                name="expiry_date"
                value={formData.expiry_date}
                onChange={handleChange}
                required
                className="w-full outline-none bg-transparent text-gray-800 dark:text-gray-200 custom-date-input"
              />
            </div>
          </div>
          {/* 🔹 Button */}
          <button
            type="submit"
            className="w-full py-2.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-lg font-semibold"
          >
            {editData ? "Update Stock" : "Add Stock"}
          </button>
        </form>
      </div>
    </div>
  );
}
