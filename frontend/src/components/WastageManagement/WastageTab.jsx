import React, { useState, useEffect } from "react";
import PageHeader from "../PageHeader";
import {
  FiPlus,
  FiFileText,
  FiEye,
  FiChevronLeft,
  FiChevronRight,
  FiAlertTriangle,
  FiTrash2,
  FiBox,
  FiSearch,
  FiArrowUp,
  FiArrowDown,
  FiMinus,
  FiEdit2,
} from "react-icons/fi";

import api from "../../api/axios";
import { toast } from "react-toastify";
import AddDishWastageModal from "./AddDishWastageModal";
import AddExcelModal from "../Inventory Management/AddExcelModal";
import PerishableWasteTab from "./PerishableWasteTab";
import NonPerishableWasteTab from "./NonPerishableWasteTab";
import { capitalizeWords } from "../../utils/text";

export default function WastageTab() {
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [searchText, setSearchText] = useState("");

  const [filterType, setFilterType] = useState("daily");
  const getTodayDate = () => {
    const today = new Date();
    return today.toISOString().split("T")[0]; // YYYY-MM-DD
  };

  const [selectedDate, setSelectedDate] = useState(getTodayDate());
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  const [activeTab, setActiveTab] = useState("all");

  const [showAddModal, setShowAddModal] = useState(false);

  const [wastageRecords, setWastageRecords] = useState([]);
  const [showExcelModal, setShowExcelModal] = useState(false);
  const [editData, setEditData] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedWastage, setSelectedWastage] = useState(null);
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: null,
  });
  const [expandedRows, setExpandedRows] = useState({});
  const [stats, setStats] = useState({
    totalCost: 0,
    totalRecords: 0,

    mostDish: "-",
    mostDishCost: 0,

    topItem: "-",
    topItemCost: 0,

    leastItem: "-",
    leastItemCost: 0,

    topReason: "-",

    inventoryCount: 0,
    dishCount: 0,
  });

  /* ================= FETCH WASTAGE ================= */
  const fetchWastageRecords = async () => {
    try {
      let params = {
        page: currentPage,
        page_size: rowsPerPage,
      };

      if (searchText.trim()) {
        params.search = searchText;
      }

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

      const res = await api.get("/wastage/records", { params });

      console.log("WASTAGE RESPONSE:", res.data);

      const summary = res.data?.summary || {};

      // backend records
      const records = res.data?.records || res.data?.data || [];

      // Hide reversed / invalid wastage records
      const filteredRecords = records.filter((item) => {
        const qty = item.quantity_wasted ?? item.quantity_unsold ?? 0;

        return qty > 0;
      });

      setWastageRecords(filteredRecords);
      setTotalPages(
        res.data.meta?.total_pages || res.data.pagination?.total_pages || 1,
      );
      /* ================= NEW STATS (BACKEND + DERIVED) ================= */

      // -------- BASIC --------
      const totalCost = summary.total_wastage_cost || 0;
      const totalRecords = summary.total_wastage_records || records.length;

      // -------- MOST WASTED DISH --------
      const mostDish = summary.most_wasted_dish?.name || "No dish wastage";
      const mostDishCost = summary.most_wasted_dish?.total_cost || 0;

      // -------- INVENTORY ITEMS --------
      const topItem = summary.most_wasted_inventory_item?.name || "-";
      const topItemCost = summary.most_wasted_inventory_item?.total_cost || 0;

      const leastItem = summary.least_wasted_inventory_item?.name || "-";
      const leastItemCost =
        summary.least_wasted_inventory_item?.total_cost || 0;

      // -------- DERIVED STATS --------
      let reasonCount = {};
      let inventoryCount = 0;
      let dishCount = 0;

      records.forEach((row) => {
        // count reasons
        if (row.wastage_reason) {
          reasonCount[row.wastage_reason] =
            (reasonCount[row.wastage_reason] || 0) + 1;
        }

        // type split
        if (row.wastage_type === "inventory") inventoryCount++;
        if (row.wastage_type === "dish") dishCount++;
      });

      const topReason =
        Object.keys(reasonCount).length > 0
          ? Object.keys(reasonCount).reduce((a, b) =>
              reasonCount[a] > reasonCount[b] ? a : b,
            )
          : "-";

      /* ================= SET FINAL STATS ================= */

      setStats({
        totalCost,
        totalRecords,

        mostDish,
        mostDishCost,

        topItem,
        topItemCost,

        leastItem,
        leastItemCost,

        topReason,

        inventoryCount,
        dishCount,
      });
    } catch (err) {
      console.error(err);
      toast.error("Failed to fetch wastage records");
    }
  };

  useEffect(() => {
    fetchWastageRecords();
  }, [
    filterType,
    selectedDate,
    customFrom,
    customTo,
    currentPage,
    rowsPerPage,
    searchText,
  ]);

  /* ================= PAGINATION ================= */

  const sortedData = [...wastageRecords].sort((a, b) => {
    if (!sortConfig.key) return 0;

    let aValue = 0;
    let bValue = 0;

    switch (sortConfig.key) {
      case "quantity":
        aValue = a.quantity_wasted || a.quantity_unsold || 0;
        bValue = b.quantity_wasted || b.quantity_unsold || 0;
        break;

      case "cost":
        aValue = a.cost_value || 0;
        bValue = b.cost_value || 0;
        break;

      case "date":
        aValue = new Date(a.wastage_date || 0).getTime();
        bValue = new Date(b.wastage_date || 0).getTime();
        break;

      default:
        return 0;
    }

    if (sortConfig.direction === "asc") return aValue - bValue;
    if (sortConfig.direction === "desc") return bValue - aValue;

    return 0;
  });

  const toggleBreakdown = (id) => {
    setExpandedRows((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
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
      <PageHeader title="Wastage Management" tabs={[]} />

      {/* ================= FILTER BUTTONS ================= */}
      <div className="flex flex-col gap-3 px-6 py-4">
        {/* ROW 1 → Filters + Download */}
        <div className="flex justify-between items-center">
          {/* LEFT → Filters */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setActiveTab("all")}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition
        ${
          activeTab === "all"
            ? "bg-[#9AF288] text-gray-900 shadow-sm"
            : "bg-gray-100 dark:bg-[#020617] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-800"
        }`}
            >
              All
            </button>

            <button
              onClick={() => setActiveTab("perishable")}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition
        ${
          activeTab === "perishable"
            ? "bg-[#9AF288] text-gray-900 shadow-sm"
            : "bg-gray-100 dark:bg-[#020617] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-800"
        }`}
            >
              Perishable Waste
            </button>

            <button
              onClick={() => setActiveTab("non-perishable")}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition
        ${
          activeTab === "non-perishable"
            ? "bg-[#9AF288] text-gray-900 shadow-sm"
            : "bg-gray-100 dark:bg-[#020617] text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-800"
        }`}
            >
              Non-Perishable Waste
            </button>
          </div>

          {/* RIGHT → Download */}
          <a
            href="/wastage_excel_format.xlsx"
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

        {/* ROW 2 → Buttons RIGHT */}
        <div className="flex justify-end items-center gap-3">
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
      bg-orange-500 text-white hover:bg-orange-600 transition"
          >
            <FiPlus />
            Add wastage
          </button>

          <button
            onClick={() => setShowExcelModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 
      bg-white dark:bg-[#020617] text-sm hover:bg-gray-50 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300"
          >
            <FiFileText />
            Add via excel
          </button>
        </div>
      </div>

      {activeTab === "all" && (
        <>
          {/* ================= STATS ================= */}
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4 px-6 pb-4">
            <StatCard
              title="Total Cost"
              value={`₹${stats.totalCost}`}
              icon={<FiTrash2 />}
            />

            <StatCard
              title="Total Records"
              value={stats.totalRecords}
              icon={<FiAlertTriangle />}
            />

            <StatCard
              title="Most Wasted Dish"
              value={capitalizeWords(stats.mostDish)}
              price={stats.mostDishCost}
              icon={<FiBox />}
            />

            <StatCard
              title="Top Inventory Waste"
              value={capitalizeWords(stats.topItem)}
              price={stats.topItemCost}
              icon={<FiBox />}
            />

            <StatCard
              title="Least Wasted Item"
              value={capitalizeWords(stats.leastItem)}
              price={stats.leastItemCost}
              icon={<FiBox />}
            />

            <StatCard
              title="Top Reason"
              value={capitalizeWords(stats.topReason)}
              icon={<FiAlertTriangle />}
            />

            <StatCard
              title="Inventory vs Dish"
              value={`${stats.inventoryCount} / ${stats.dishCount}`}
              icon={<FiBox />}
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 px-6 pb-4">
            {/* LEFT → Filters */}
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex bg-gray-100 dark:bg-[#020617] p-1 rounded-full">
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
                    className={`px-4 py-1.5 text-sm rounded-full font-medium transition ${
                      filterType === type
                        ? "bg-orange-500 text-white"
                        : "text-gray-700 dark:text-gray-300"
                    }`}
                  >
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </button>
                ))}
              </div>

              {/* DATE RANGE */}
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                  disabled={filterType !== "custom"}
                  className={`px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200
  ${filterType !== "custom" ? "cursor-not-allowed opacity-60" : ""}`}
                />

                <span>-</span>

                <input
                  type="date"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                  disabled={filterType !== "custom"}
                  className={`px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200
  ${filterType !== "custom" ? "cursor-not-allowed opacity-60" : ""}`}
                />
              </div>
            </div>

            {/* RIGHT → SEARCH */}
            <div className="relative w-72">
              <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg" />

              <input
                type="text"
                placeholder="Search wastage..."
                value={searchText}
                onChange={(e) => {
                  setSearchText(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full pl-10 pr-4 py-2 rounded-xl
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
                <table className="w-full min-w-[900px]">
                  <thead className="sticky top-0 bg-gray-100 dark:bg-[#020617] border-b border-gray-200 dark:border-gray-700 z-10">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Batch
                      </th>

                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Wastage Item
                      </th>

                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Type
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
                          Cost
                          <span
                            onClick={() => handleSort("cost")}
                            className="cursor-pointer"
                          >
                            {sortConfig.key === "cost" ? (
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
                        Reason
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
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Edit
                      </th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                        Proof
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedData.length === 0 ? (
                      <tr>
                        <td
                          colSpan="9"
                          className="text-center py-10 text-gray-500 dark:text-gray-400"
                        >
                          🚫 No wastage records found for selected date
                        </td>
                      </tr>
                    ) : (
                      sortedData.map((row) => (
                        <React.Fragment key={row.id}>
                          {/* MAIN ROW */}
                          <tr className="border-t border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#020617] transition">
                            {/* BATCH */}
                            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                              <div className="flex items-center gap-2">
                                {(row.wastage_type === "dish" ||
                                  row.wastage_type === "combo") &&
                                  row.breakdown?.length > 0 && (
                                    <button
                                      onClick={() => toggleBreakdown(row.id)}
                                      className="text-gray-500 hover:text-orange-500 transition"
                                    >
                                      <FiChevronRight
                                        className={`transition-transform duration-200 ${
                                          expandedRows[row.id]
                                            ? "rotate-90"
                                            : ""
                                        }`}
                                      />
                                    </button>
                                  )}

                                {row.batch_number || "-"}
                              </div>
                            </td>

                            {/* ITEM */}
                            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                              {capitalizeWords(
                                row.item_name ||
                                  row.dish_name ||
                                  row.combo_name ||
                                  "-",
                              )}
                            </td>

                            {/* TYPE */}
                            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                              {capitalizeWords(row.wastage_type || "-")}
                            </td>

                            {/* QUANTITY */}
                            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                              {row.quantity_wasted || row.quantity_unsold}{" "}
                              {row.unit ||
                                (row.wastage_type === "dish" ? "portion" : "")}
                            </td>
                            {/* COST */}
                            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                              ₹{row.cost_value ?? row.unit_cost ?? 0}
                            </td>

                            {/* REASON */}
                            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                              <span className="px-2 py-1 text-xs rounded-full bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400">
                                {capitalizeWords(
                                  row.wastage_reason || "unsold",
                                )}
                              </span>
                            </td>

                            {/* DATE */}
                            <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                              {row.wastage_date
                                ? new Date(row.wastage_date)
                                    .toLocaleDateString("en-GB")
                                    .replace(/\//g, "-")
                                : "-"}
                            </td>

                            {/* EDIT */}
                            <td className="px-4 py-3">
                              <button
                                onClick={() => {
                                  setEditData(row);
                                  setShowAddModal(true);
                                }}
                                className="p-1 rounded text-orange-500 hover:bg-orange-100 dark:hover:bg-orange-500/20 transition"
                              >
                                <FiEdit2 />
                              </button>
                            </td>

                            {/* PROOF */}
                            <td className="px-4 py-3">
                              <button
                                disabled={!row.photo_url}
                                onClick={() =>
                                  window.open(row.photo_url, "_blank")
                                }
                                className={`p-1 rounded
            ${
              row.photo_url
                ? "text-blue-500 hover:bg-gray-200 dark:hover:bg-gray-700"
                : "text-gray-400 cursor-not-allowed"
            }`}
                              >
                                <FiEye />
                              </button>
                            </td>
                          </tr>

                          {/* BREAKDOWN ROW */}
                          {expandedRows[row.id] &&
                            row.breakdown?.length > 0 && (
                              <tr className="bg-gray-50 dark:bg-[#0f172a]">
                                <td colSpan="9" className="px-6 py-4">
                                  <div>
                                    <h3 className="text-sm font-semibold text-green-600 mb-3">
                                      Ingredient Breakdown
                                    </h3>

                                    <div className="flex flex-wrap gap-3">
                                      {row.breakdown.map(
                                        (ingredient, index) => (
                                          <div
                                            key={index}
                                            className={`min-w-[150px] rounded-xl border px-4 py-3 shadow-sm
                    ${
                      ingredient.source === "raw"
                        ? "bg-green-50 border-green-200"
                        : "bg-orange-50 border-orange-200"
                    }`}
                                          >
                                            {/* NAME */}
                                            <p
                                              className={`text-sm font-semibold
                      ${
                        ingredient.source === "raw"
                          ? "text-green-700"
                          : "text-orange-700"
                      }`}
                                            >
                                              {capitalizeWords(
                                                ingredient.ingredient_name ||
                                                  ingredient.semi_finished_name ||
                                                  ingredient.dish_name ||
                                                  "-",
                                              )}
                                            </p>

                                            {/* QTY */}
                                            <p className="text-xs text-gray-500 mt-1">
                                              {ingredient.qty_deducted ??
                                                ingredient.semi_finished_qty ??
                                                ingredient.sub_ingredients?.[0]
                                                  ?.qty_deducted ??
                                                "-"}{" "}
                                              {ingredient.unit ||
                                                ingredient.semi_finished_unit ||
                                                ingredient.sub_ingredients?.[0]
                                                  ?.unit ||
                                                ""}
                                            </p>

                                            {/* COST */}
                                            <p
                                              className={`text-sm font-bold mt-1
                      ${
                        ingredient.source === "raw"
                          ? "text-green-600"
                          : "text-orange-600"
                      }`}
                                            >
                                              ₹
                                              {ingredient.ingredient_cost ??
                                                ingredient.semi_finished_cost ??
                                                ingredient.dish_cost ??
                                                ingredient.sub_ingredients?.[0]
                                                  ?.ingredient_cost ??
                                                0}
                                            </p>
                                          </div>
                                        ),
                                      )}
                                    </div>
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

              {/* PAGINATION */}

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

                  {/* Dynamic Pages */}
                  {(() => {
                    let pages = [];

                    // 1,2,3 → SHOW ALL
                    if (totalPages <= 3) {
                      pages = Array.from(
                        { length: totalPages },
                        (_, i) => i + 1,
                      );
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
        </>
      )}

      {activeTab === "perishable" && <PerishableWasteTab />}

      {activeTab === "non-perishable" && <NonPerishableWasteTab />}

      {/* ================= MODAL ================= */}

      {showAddModal && (
        <AddDishWastageModal
          isOpen={showAddModal}
          editData={editData}
          onClose={() => {
            setShowAddModal(false);
            setEditData(null);
          }}
          onSuccess={() => {
            fetchWastageRecords();
            setShowAddModal(false);
          }}
        />
      )}
      {showExcelModal && (
        <AddExcelModal
          isOpen={showExcelModal}
          onClose={() => setShowExcelModal(false)}
          uploadUrl="/wastage/bulk-upload-via-excel"
          onSuccess={() => {
            fetchWastageRecords();
            setShowExcelModal(false);
          }}
        />
      )}
    </div>
  );
}

/* ================= STAT CARD ================= */
function StatCard({ title, value, icon, price }) {
  return (
    <div
      className="bg-white dark:bg-[#020617]
border border-gray-200 dark:border-gray-700
rounded-xl px-5 py-4 shadow-sm"
    >
      {/* TOP ROW → TITLE + ICON */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>

        <div className="text-red-500 text-xl">{icon}</div>
      </div>

      {/* BOTTOM ROW → VALUE + PRICE */}
      <div className="flex items-center justify-between mt-2">
        <span className="text-base font-semibold text-gray-900 dark:text-white">
          {value}
        </span>

        {price !== undefined && (
          <span className="text-m font-semibold text-gray-700 dark:text-gray-300">
            ₹{price}
          </span>
        )}
      </div>
    </div>
  );
}
