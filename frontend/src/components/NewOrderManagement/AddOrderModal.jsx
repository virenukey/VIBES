import React, { useState, useEffect, useRef } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function AddOrderModal({ isOpen, onClose, onSuccess }) {
  const [orderType, setOrderType] = useState("dish");

  const [items, setItems] = useState([]);

  const [searchText, setSearchText] = useState("");

  const [selectedItemId, setSelectedItemId] = useState("");

  const [qty, setQty] = useState("");
  const [date, setDate] = useState("");

  const [showDropdown, setShowDropdown] = useState(false);

  const dropdownRef = useRef(null);

  if (!isOpen) return null;

  /* ================= FETCH DISHES ================= */

  /* ================= FETCH ITEMS ================= */

  useEffect(() => {
  const fetchItems = async () => {
    try {
      if (orderType === "dish") {
        const res = await api.get(
          `/dish/get-dishes-with-ingredients?search=${searchText}`
        );

        setItems(res.data.dishes || []);
      } else {
        const res = await api.get(
          `/dish/?search=${searchText}`
        );

        setItems(res.data.combos || []);
      }
    } catch (err) {
      console.error(`Failed to fetch ${orderType}s`, err);
    }
  };

  const debounce = setTimeout(() => {
    fetchItems();
  }, 300);

  return () => clearTimeout(debounce);
}, [orderType, searchText]);

  /* ================= CLOSE DROPDOWN ON OUTSIDE CLICK ================= */

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  /* ================= FILTER DISHES ================= */

 
  /* ================= SELECT DISH ================= */

  const selectItem = (item) => {
    setSearchText(item.name);

    setSelectedItemId(item.id);

    setShowDropdown(false);
  };

  /* ================= RESET WHEN CLEARED ================= */

  useEffect(() => {
    if (searchText === "") {
      setSelectedItemId("");
    }
  }, [searchText]);

  /* ================= SUBMIT ================= */
  const submitOrder = async () => {
    if (Number(qty || 0) < 0) {
      toast.error("Quantity cannot be negative ❌");
      return;
    }

    if (!qty || Number(qty) === 0) {
      toast.error("Quantity must be greater than 0 ❌");
      return;
    }
    try {
      const formattedDate = `${
        date || new Date().toISOString().split("T")[0]
      }T00:00:00`;

      await api.post("/oders/add-ordered-dish", {
        sales:
          orderType === "dish"
            ? [
                {
                  dish_id: Number(selectedItemId),

                  qty_sold: Number(qty),

                  date: formattedDate,
                },
              ]
            : [],

        combo_sales:
          orderType === "combo"
            ? [
                {
                  combo_id: Number(selectedItemId),

                  qty_sold: Number(qty),

                  date: formattedDate,
                },
              ]
            : [],

        sale_date: formattedDate,
      });

      toast.success("Order added successfully 🍽️");

      onSuccess();

      onClose();
    } catch (err) {
      console.error("FULL ERROR 👉", err.response?.data);

      let errorMessage = "Failed to add order ❌";

      const data = err?.response?.data;

      if (data?.detail?.errors && Array.isArray(data.detail.errors)) {
        errorMessage = data.detail.errors.join(", ");
      }

      toast.error(errorMessage);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div
        className="bg-white dark:bg-[#0f172a] rounded-xl w-[420px] p-6 shadow-xl border border-gray-200 dark:border-gray-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}

        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            Add Order
          </h2>

          <button
            onClick={onClose}
            className="text-gray-500 hover:text-black dark:hover:text-white"
          >
            ✕
          </button>
        </div>

        {/* Form */}

        <div className="space-y-4">
          {/* ORDER TYPE */}

          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Order Type
            </label>

            <select
              value={orderType}
              onChange={(e) => {
                setOrderType(e.target.value);

                setSearchText("");

                setSelectedItemId("");

                setShowDropdown(false);
              }}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700
    bg-white dark:bg-[#020617]
    text-gray-800 dark:text-gray-200
    outline-none focus:ring-2 focus:ring-orange-400"
            >
              <option value="dish">Dish</option>

              <option value="combo">Combo</option>
            </select>
          </div>

          {/* Dish Search Dropdown */}

          <div className="relative" ref={dropdownRef}>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              {orderType === "dish" ? "Dish Name" : "Combo Name"}
            </label>

            <input
              type="text"
              value={searchText}
              onChange={(e) => {
                setSearchText(e.target.value);

                setShowDropdown(true);
              }}
              onFocus={() => setShowDropdown(true)}
              placeholder={`Search ${orderType}...`}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700
              bg-white dark:bg-[#020617]
              text-gray-800 dark:text-gray-200
              outline-none focus:ring-2 focus:ring-orange-400"
            />

            {/* Dropdown */}

            {showDropdown && (
              <div className="absolute z-50 w-full mt-1 max-h-52 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#020617] shadow-lg">
               {items.length > 0 ? (
  items.map((item) => (
                    <div
                      key={item.id}
                      onClick={() => selectItem(item)}
                      className="px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 text-sm text-gray-800 dark:text-gray-200"
                    >
                      {item.name}
                    </div>
                  ))
                ) : (
                  <div className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
                    No {orderType}s found
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Quantity */}
          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Quantity
            </label>

            <input
              type="number"
              value={qty}
              min="0"
              onKeyDown={(e) => {
                if (e.key === "-" || e.key === "e") e.preventDefault();
              }}
              onChange={(e) => {
                const value = e.target.value;

                if (value !== "" && Number(value) < 0) {
                  toast.error("Negative quantity not allowed ❌");
                  return;
                }

                setQty(value);
              }}
              placeholder="Enter quantity"
              className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700
  bg-white dark:bg-[#020617]
  text-gray-800 dark:text-gray-200
  outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {/* Date */}

          <div>
            <label className="text-sm text-gray-600 dark:text-gray-300">
              Date
            </label>

            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-700
              bg-white dark:bg-[#020617]
              text-gray-800 dark:text-gray-200
              outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>
        </div>

        {/* Submit */}

        <button
          onClick={submitOrder}
          disabled={!selectedItemId || !qty}
          className="w-full mt-6 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white font-semibold py-2 rounded-lg transition"
        >
          Add Order
        </button>
      </div>
    </div>
  );
}
