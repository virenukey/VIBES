import React, { useState, useEffect } from "react";
import api from "../../api/axios";
import PageHeader from "../PageHeader";
import {
  FiPlus,
  FiSearch,
  FiFileText,
  FiChevronLeft,
  FiChevronRight,
  FiChevronRight as RowClosed,
  FiChevronDown as RowOpen,
  FiShoppingCart,
  FiTrendingUp,
  FiDollarSign,
  FiPackage,
  FiCalendar,
  FiArrowUp,
  FiArrowDown,
  FiMinus,
} from "react-icons/fi";
import { FaRupeeSign } from "react-icons/fa";
import { capitalizeWords } from "../../utils/text";

import AddOrderModal from "./AddOrderModal";
import AddExcelModal from "../Inventory Management/AddExcelModal";

export default function OrderTab() {
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [searchText, setSearchText] = useState("");

  const [expandedOrder, setExpandedOrder] = useState(null);

  const [showAddModal, setShowAddModal] = useState(false);
  const [showExcelModal, setShowExcelModal] = useState(false);

  const [orders, setOrders] = useState([]);
  const [dashboard, setDashboard] = useState(null);

  const [filterType, setFilterType] = useState("daily");
  const getTodayDate = () => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  };
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: null,
  });

  const [selectedDate, setSelectedDate] = useState(getTodayDate());

  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  /* ================= FETCH SALES ================= */
  const fetchSalesHistory = async () => {
    try {
      let params = {
        page: currentPage,
        page_size: rowsPerPage,
      };

      if (searchText.trim()) {
        params.search = searchText;
      }
      // DAILY
      if (filterType === "daily" && selectedDate) {
        params.date_from = selectedDate;
        params.date_to = selectedDate;
      }

      // WEEKLY
      if (filterType === "weekly" && selectedDate) {
        const week = getWeekRange(selectedDate);

        params.date_from = week.start;
        params.date_to = week.end;
      }

      // MONTHLY
      if (filterType === "monthly" && selectedDate) {
        const month = getMonthRange(selectedDate);

        params.date_from = month.start;
        params.date_to = month.end;
      }

      // CUSTOM
      if (filterType === "custom") {
        if (!customFrom || !customTo) return;

        params.date_from = customFrom;
        params.date_to = customTo;
      }

      const res = await api.get("/oders/sales-history", { params });
      const transformed = (res.data.sales || []).map((sale, index) => {
        const ingredients = (sale.ingredients_used || [])
          .map((item) => {
            if (item.type === "raw") {
              return {
                ingredient_name: item.ingredient_name,
                quantity_consumed: item.quantity_consumed ?? 0,
                unit: item.unit ?? "",
              };
            }

            if (item.type === "semi_finished") {
              return {
                ingredient_name:
                  item.semi_finished_name || item.ingredient_name,
                quantity_consumed: item.qty_used ?? 0,
                unit: item.unit ?? "",
              };
            }

            return null;
          })
          .filter(Boolean);

        return {
          ...sale,
          sale_id: sale.sale_id || index,
          ingredients_used: ingredients,
        };
      });

      setOrders(transformed);
      setTotalPages(res.data.meta?.total_pages || 1);
    } catch (err) {
      console.error("Failed to fetch sales history", err);
    }
  };

  /* ================= FETCH DASHBOARD ================= */
  const fetchDashboard = async () => {
    try {
      let params = {};

      if (filterType === "daily") {
        params.filter_type = "daily";
        params.date = selectedDate;
      }

      if (filterType === "weekly") {
        params.filter_type = "weekly";
        params.date = selectedDate;
      }

      if (filterType === "monthly") {
        params.filter_type = "monthly";
        params.date = selectedDate;
      }

      if (filterType === "custom") {
        if (!customFrom || !customTo) return;

        params.filter_type = "custom";
        params.start_date = customFrom;
        params.end_date = customTo;
      }
      const res = await api.get("/oders/sales-dashboard", { params });

      setDashboard(res.data);
    } catch (err) {
      console.error("Failed to fetch dashboard", err);
    }
  };

  useEffect(() => {
    fetchSalesHistory();
    fetchDashboard();
  }, [
    filterType,
    selectedDate,
    customFrom,
    customTo,
    currentPage,
    rowsPerPage,
    searchText,
  ]);
  /* ================= FILTER ================= */

  const sortedData = [...orders].sort((a, b) => {
    if (!sortConfig.key) return 0;

    let aValue = 0;
    let bValue = 0;

    switch (sortConfig.key) {
      case "price":
        aValue = a.price || 0;
        bValue = b.price || 0;
        break;

      case "quantity":
        aValue = a.quantity || 0;
        bValue = b.quantity || 0;
        break;

      case "date":
        const [aDay, aMonth, aYear] = (a.date || "").split("-");
        const [bDay, bMonth, bYear] = (b.date || "").split("-");

        aValue = new Date(aYear, aMonth - 1, aDay).getTime();
        bValue = new Date(bYear, bMonth - 1, bDay).getTime();
        break;

      default:
        return 0;
    }

    if (sortConfig.direction === "asc") return aValue - bValue;
    if (sortConfig.direction === "desc") return bValue - aValue;

    return 0;
  });

  // ================= DATE HELPERS =================

  // get monday to sunday of selected date
  const getWeekRange = (date) => {
    const d = new Date(date);

    const first = new Date(d);
    first.setDate(d.getDate() - d.getDay() + 1);

    const last = new Date(first);
    last.setDate(first.getDate() + 6);

    return {
      start: first.toISOString().split("T")[0],
      end: last.toISOString().split("T")[0],
    };
  };

  // get first and last day of month
  const getMonthRange = (date) => {
    const d = new Date(date);

    const first = new Date(d.getFullYear(), d.getMonth(), 1);
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);

    return {
      start: first.toISOString().split("T")[0],
      end: last.toISOString().split("T")[0],
    };
  };

  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key !== key) return { key, direction: "asc" };
      if (prev.direction === "asc") return { key, direction: "desc" };
      return { key: null, direction: null };
    });
  };
  return (
    <div className="w-full bg-white dark:bg-[#0f172a] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm">
      <PageHeader title="Order Management" tabs={[]} />

      {/* ================= TOOLBAR ================= */}

      <div className="flex flex-col gap-3 px-6 py-4">
        {/* ROW 1 → Search + Download */}
        <div className="flex justify-end items-center">
          {/* LEFT → Search */}

          <a
            href="/order_excel_format.xlsx"
            download
            className="flex items-center gap-2 px-4 py-2 rounded-lg 
      bg-gradient-to-r from-orange-500 to-orange-600 
      text-white text-sm font-semibold 
      shadow-md hover:shadow-lg hover:scale-[1.02] 
      transition-all duration-200"
          >
            <FiFileText className="text-lg" />
            Download Excel Format
          </a>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 px-6 pb-4">
        {/* LEFT → Filters + Dates */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Filter buttons */}
          <div className="flex items-center gap-1 bg-gray-100 dark:bg-[#020617] p-1 rounded-full">
            {["daily", "weekly", "monthly", "custom"].map((type) => (
              <button
                key={type}
                onClick={() => {
                  setFilterType(type);

                  if (type !== "custom") {
                    setCustomFrom("");
                    setCustomTo("");
                  }
                }}
                className={`px-4 py-1.5 text-sm rounded-full font-medium transition
          ${
            filterType === type
              ? "bg-orange-500 text-white"
              : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800"
          }`}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>

          {/* Date Inputs */}
          {filterType !== "custom" && (
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={customFrom}
                disabled
                className="px-3 py-1.5 rounded-lg
border-2 border-orange-400
bg-white dark:bg-[#020617]
text-sm cursor-not-allowed opacity-70"
              />
              <span>-</span>
              <input
                type="date"
                value={customTo}
                disabled
                className="px-3 py-1.5 rounded-lg
border-2 border-orange-400
bg-white dark:bg-[#020617]
text-sm cursor-not-allowed opacity-70"
              />
            </div>
          )}

          {filterType === "custom" && (
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                className="px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200"
              />

              <span>-</span>

              <input
                type="date"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                className="px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200"
              />
            </div>
          )}
        </div>

        {/* RIGHT → Buttons */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
      bg-orange-500 text-white hover:bg-orange-600 transition"
          >
            <FiPlus />
            Add Order
          </button>

          <button
            onClick={() => setShowExcelModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border
      border-gray-200 dark:border-gray-700
      bg-white dark:bg-[#020617]
      text-sm text-gray-800 dark:text-gray-200
      hover:bg-gray-50 dark:hover:bg-gray-800 transition"
          >
            <FiFileText />
            Add via excel
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 px-6 pb-4">
        {/* Total Orders */}

        <div
          className="flex items-center justify-between bg-white dark:bg-[#020617]
  border border-gray-200 dark:border-gray-700 rounded-xl px-5 py-4"
        >
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Total Ordered Dish
            </p>

            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              {dashboard?.total_orders || 0}
            </h2>
          </div>

          <FiShoppingCart className="text-red-500 text-2xl" />
        </div>

        {/* Revenue */}

        <div
          className="flex items-center justify-between bg-white dark:bg-[#020617]
  border border-gray-200 dark:border-gray-700 rounded-xl px-5 py-4"
        >
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Total Revenue
            </p>

            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              ₹{dashboard?.total_revenue || 0}
            </h2>
          </div>

          <FaRupeeSign className="text-green-500 text-2xl" />
        </div>

        {/* Profit */}

        <div
          className="flex items-center justify-between bg-white dark:bg-[#020617]
  border border-gray-200 dark:border-gray-700 rounded-xl px-5 py-4"
        >
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">Profit</p>

            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              ₹{dashboard?.profit || 0}
            </h2>
          </div>

          <FiTrendingUp className="text-green-400 text-2xl" />
        </div>

        {/* COGS */}

        <div
          className="flex items-center justify-between bg-white dark:bg-[#020617]
  border border-gray-200 dark:border-gray-700 rounded-xl px-5 py-4"
        >
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Total Cost (COGS)
            </p>

            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              ₹{dashboard?.total_cogs || 0}
            </h2>
          </div>

          <FiPackage className="text-red-500 text-2xl" />
        </div>
      </div>
      <div className="px-6 mb-4 flex justify-end">
        <div className="relative w-72">
          <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg" />

          <input
            type="text"
            placeholder="Search orders..."
            value={searchText}
            onChange={(e) => {
              setSearchText(e.target.value);
              setCurrentPage(1);
            }}
            className="w-64 sm:w-72 pl-10 pr-4 py-2 rounded-xl 
      border-2 border-orange-400
      bg-white dark:bg-[#020617]
      text-sm text-gray-800 dark:text-gray-200
      outline-none
      transition-all duration-200"
          />
        </div>
      </div>
      {/* ================= TABLE ================= */}

      <div className="px-6 pb-4">
        <div className="border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto overflow-y-auto max-h-[400px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-gray-100 dark:bg-[#020617] border-b border-gray-200 dark:border-gray-800 z-10">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Dish
                  </th>

                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                    Category
                  </th>

                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                    <div className="flex items-center gap-1">
                      Price
                      <span
                        onClick={() => handleSort("price")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "price" ? (
                          sortConfig.direction === "asc" ? (
                            <FiArrowUp className="text-orange-500" />
                          ) : sortConfig.direction === "desc" ? (
                            <FiArrowDown className="text-orange-500" />
                          ) : (
                            <FiMinus className="text-gray-400" />
                          )
                        ) : (
                          <FiMinus className="text-gray-400" />
                        )}
                      </span>
                    </div>
                  </th>

                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                    <div className="flex items-center gap-1">
                      Quantity
                      <span
                        onClick={() => handleSort("quantity")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "quantity" ? (
                          sortConfig.direction === "asc" ? (
                            <FiArrowUp className="text-orange-500" />
                          ) : sortConfig.direction === "desc" ? (
                            <FiArrowDown className="text-orange-500" />
                          ) : (
                            <FiMinus className="text-gray-400" />
                          )
                        ) : (
                          <FiMinus className="text-gray-400" />
                        )}
                      </span>
                    </div>
                  </th>

                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                    <div className="flex items-center gap-1">
                      Date
                      <span
                        onClick={() => handleSort("date")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "date" ? (
                          sortConfig.direction === "asc" ? (
                            <FiArrowUp className="text-orange-500" />
                          ) : sortConfig.direction === "desc" ? (
                            <FiArrowDown className="text-orange-500" />
                          ) : (
                            <FiMinus className="text-gray-400" />
                          )
                        ) : (
                          <FiMinus className="text-gray-400" />
                        )}
                      </span>
                    </div>
                  </th>
                  {/* 
                                <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                                    Time
                                </th> */}
                </tr>
              </thead>
              <tbody>
                {sortedData.length === 0 ? (
                  <tr>
                    <td
                      colSpan="5"
                      className="text-center py-10 text-gray-500 dark:text-gray-400"
                    >
                      <div className="flex flex-col items-center gap-2">
                        <span className="text-2xl">📦</span>
                        <span>No orders found for selected date</span>
                      </div>
                    </td>
                  </tr>
                ) : (
                  sortedData.map((order) => (
                    <React.Fragment key={order.sale_id}>
                      <tr className="border-t border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#020617] transition">
                        <td className="px-4 py-3 text-sm font-medium flex items-center gap-2 text-gray-800 dark:text-gray-200">
                          <button
                            onClick={() =>
                              setExpandedOrder(
                                expandedOrder === order.sale_id
                                  ? null
                                  : order.sale_id,
                              )
                            }
                            className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition"
                          >
                            {expandedOrder === order.sale_id ? (
                              <RowOpen />
                            ) : (
                              <RowClosed />
                            )}
                          </button>

                          {capitalizeWords(
                            order.type === "combo"
                              ? order.combo_name
                              : order.dish_name,
                          )}
                        </td>

                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                          {capitalizeWords(order.category)}
                        </td>

                        <td className="px-4 py-3 text-sm font-medium text-gray-700 dark:text-gray-300">
                          ₹
                          {order.type === "combo"
                            ? order.selling_price
                            : order.price}{" "}
                        </td>

                        <td className="px-4 py-3 text-sm font-semibold text-gray-700 dark:text-gray-300">
                          x
                          {order.type === "combo"
                            ? order.quantity
                            : order.quantity}
                        </td>

                        <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                          {order.date}
                        </td>
                      </tr>

                      {/* EXPANDED */}
                      {expandedOrder === order.sale_id && (
                        <tr className="bg-gray-50 dark:bg-[#020617]">
                          <td colSpan={6} className="px-6 py-5">
                            <p className="text-green-600 dark:text-green-400 text-sm font-semibold mb-4">
                              {order.type === "combo"
                                ? "Combo Items"
                                : "Ingredients Used"}
                            </p>

                            <div className="flex flex-wrap gap-3">
                              {order.type === "combo" ? (
                                <>
                                  {(order.combo_items || []).map(
                                    (item, index) => (
                                      <div
                                        key={index}
                                        className="border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-3 bg-white dark:bg-[#0b1220] shadow-sm"
                                      >
                                        <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                                          {capitalizeWords(item.item_name)}
                                        </p>

                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                          <p className="text-xs text-gray-500 dark:text-gray-400">
                                            {item.quantity}{" "}
                                            {item.unit === "piece"
                                              ? "plate"
                                              : item.unit}
                                          </p>
                                        </p>
                                      </div>
                                    ),
                                  )}

                                  {(order.combo_items || []).length === 0 && (
                                    <p className="text-sm text-gray-400 italic">
                                      No combo items available
                                    </p>
                                  )}
                                </>
                              ) : (
                                <>
                                  {(order.ingredients_used || []).map(
                                    (ing, index) => (
                                      <div
                                        key={index}
                                        className="border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-3 bg-white dark:bg-[#0b1220] shadow-sm"
                                      >
                                        <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                                          {capitalizeWords(ing.ingredient_name)}
                                        </p>

                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                          {ing.quantity_consumed} {ing.unit}
                                        </p>
                                      </div>
                                    ),
                                  )}

                                  {(order.ingredients_used || []).length ===
                                    0 && (
                                    <p className="text-sm text-gray-400 italic">
                                      No ingredients data available
                                    </p>
                                  )}
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* ================= PAGINATION ================= */}

          <div
            className="flex items-center justify-end gap-6 flex-wrap
  px-6 py-5 border-t border-gray-200 dark:border-gray-800"
          >
            {/* Rows Per Page */}
            <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
              <span className="font-medium">Rows per page</span>

              <select
                value={rowsPerPage}
                onChange={(e) => {
                  setRowsPerPage(Number(e.target.value));
                  setCurrentPage(1);
                }}
                className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700
      bg-white dark:bg-[#020617]
      text-sm outline-none"
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
              </select>
            </div>

            {/* Pagination */}
            <div className="flex items-center gap-1 flex-wrap">
              {/* First */}
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(1)}
                className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                «
              </button>

              {/* Previous */}
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <FiChevronLeft />
              </button>

              {(() => {
                let pages = [];

                // 1,2,3 → SHOW ALL
                if (totalPages <= 3) {
                  pages = Array.from({ length: totalPages }, (_, i) => i + 1);
                }

                // EXACTLY 4 PAGES
                else if (totalPages === 4) {
                  pages = [1, 2, 3, 4];
                }

                // EXACTLY 5 PAGES
                else if (totalPages === 5) {
                  if (currentPage <= 2) {
                    pages = [1, 2, 3, "...", 5];
                  } else if (currentPage >= 4) {
                    pages = [1, "...", 3, 4, 5];
                  } else {
                    pages = [1, 2, 3, 4, 5];
                  }
                }

                // MORE THAN 5 PAGES
                else {
                  // START
                  if (currentPage <= 2) {
                    pages = [1, 2, 3, "...", totalPages];
                  }

                  // END
                  else if (currentPage >= totalPages - 1) {
                    pages = [
                      1,
                      "...",
                      totalPages - 2,
                      totalPages - 1,
                      totalPages,
                    ];
                  }

                  // MIDDLE
                  else {
                    pages = [
                      1,
                      "...",
                      currentPage - 1,
                      currentPage,
                      currentPage + 1,
                      "...",
                      totalPages,
                    ];
                  }
                }

                return pages.map((page, index) => {
                  if (page === "...") {
                    return (
                      <span
                        key={`dots-${index}`}
                        className="w-9 h-9 flex items-center justify-center text-gray-500"
                      >
                        ...
                      </span>
                    );
                  }

                  return (
                    <button
                      key={page}
                      onClick={() => setCurrentPage(page)}
                      className={`w-9 h-9 rounded-md text-sm transition
              ${
                currentPage === page
                  ? "font-semibold text-black dark:text-white"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              }`}
                    >
                      {page}
                    </button>
                  );
                });
              })()}

              {/* Next */}
              <button
                disabled={currentPage === totalPages}
                onClick={() =>
                  setCurrentPage((p) => Math.min(totalPages, p + 1))
                }
                className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                <FiChevronRight />
              </button>

              {/* Last */}
              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(totalPages)}
                className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
              >
                »
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ================= MODALS ================= */}

      {showAddModal && (
        <AddOrderModal
          isOpen={showAddModal}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            fetchSalesHistory();
            fetchDashboard();
          }}
        />
      )}

      <AddExcelModal
        isOpen={showExcelModal}
        onClose={() => setShowExcelModal(false)}
        uploadUrl="/oders/upload-sales-excel"
        downloadReport={true}
        onSuccess={() => {
          fetchSalesHistory();
          fetchDashboard();
        }}
      />
    </div>
  );
}
