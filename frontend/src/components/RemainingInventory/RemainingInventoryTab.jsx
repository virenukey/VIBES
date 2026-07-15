import React, { useEffect, useState } from "react";
import api from "../../api/axios";
import PageHeader from "../PageHeader";
import {
  FiTrendingUp,
  FiTrendingDown,
  FiDollarSign,
  FiPackage,
  FiCalendar,
  FiChevronLeft,
  FiChevronRight,
  FiSearch,
  FiArrowUp,
  FiArrowDown,
  FiMinus,
  FiDownload,
} from "react-icons/fi";
import { FaRupeeSign } from "react-icons/fa";
import { capitalizeWords } from "../../utils/text";
export default function RemainingInventoryTab() {
  const [period, setPeriod] = useState("daily");

  const [loading, setLoading] = useState(false);
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [summary, setSummary] = useState({});
  const [items, setItems] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");

  const getTodayDate = () => {
    return new Date().toISOString().split("T")[0];
  };

  const [referenceDate, setReferenceDate] = useState(getTodayDate());
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: null,
  });

  // ================= API =================
  const fetchDashboard = async () => {
    try {
      setLoading(true);

      let params = {
        page: currentPage,
        page_size: rowsPerPage,
      };

      if (searchTerm.trim()) {
        params.search = searchTerm;
      }

      if (period === "daily") {
        params.period = "daily";
        params.reference_date = referenceDate;
      }

      if (period === "weekly") {
        params.period = "weekly";
        params.reference_date = referenceDate;
      }

      if (period === "monthly") {
        params.period = "monthly";
        params.reference_date = referenceDate;
      }

      if (period === "custom") {
        if (!customFrom || !customTo) return;

        params.period = "custom";
        params.start_date = customFrom;
        params.end_date = customTo;
      }
      const res = await api.get("/reconciliation/dashboard", { params });

      setSummary(res.data.summary || {});
      setItems(res.data.itemwise?.data || []);

      setTotalPages(
        res.data.itemwise?.meta?.total_pages || res.data.meta?.total_pages || 1,
      );
    } catch (err) {
      console.error("Error fetching remaining inventory", err);
    } finally {
      setLoading(false);
    }
  };

  // ================= DOWNLOAD REPORT =================
  const handleDownloadReport = async () => {
    try {
      let params = {};

      // Same params logic as dashboard API
      if (period === "daily") {
        params.period = "daily";
        params.reference_date = referenceDate;
      }

      if (period === "weekly") {
        params.period = "weekly";
        params.reference_date = referenceDate;
      }

      if (period === "monthly") {
        params.period = "monthly";
        params.reference_date = referenceDate;
      }

      if (period === "custom") {
        if (!customFrom || !customTo) {
          alert("Please select start and end date");
          return;
        }

        params.period = "custom";
        params.start_date = customFrom;
        params.end_date = customTo;
      }

      // Include search if available
      if (searchTerm.trim()) {
        params.search = searchTerm;
      }

      const response = await api.get("/reconciliation/download/excel", {
        params,
        responseType: "blob", // Important for file download
      });

      // Create file download
      const blob = new Blob([response.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });

      const url = window.URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = url;

      // Dynamic filename
      link.setAttribute("download", `remaining_inventory_${period}.xlsx`);

      document.body.appendChild(link);
      link.click();

      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Error downloading report:", error);
    }
  };

  useEffect(() => {
    fetchDashboard();
  }, [
    period,
    referenceDate,
    customFrom,
    customTo,
    currentPage,
    rowsPerPage,
    searchTerm,
  ]);

  // ================= SEARCH FILTER =================

  const parseQuantity = (value) => {
    if (!value) return 0;

    const num = parseFloat(value);
    return isNaN(num) ? 0 : num;
  };
  const sortedItems = [...items].sort((a, b) => {
    if (!sortConfig.key) return 0;

    let aValue = 0;
    let bValue = 0;

    switch (sortConfig.key) {
      case "openingQty":
        aValue = parseQuantity(a.opening?.quantity_display);
        bValue = parseQuantity(b.opening?.quantity_display);
        break;

      case "wastageQty":
        aValue = parseQuantity(a.wastage?.quantity_display);
        bValue = parseQuantity(b.wastage?.quantity_display);
        break;

      case "closingQty":
        aValue = parseQuantity(a.closing?.quantity_display);
        bValue = parseQuantity(b.closing?.quantity_display);
        break;

      case "openingValue":
        aValue = a.opening?.value || 0;
        bValue = b.opening?.value || 0;
        break;

      case "closingValue":
        aValue = a.closing?.value || 0;
        bValue = b.closing?.value || 0;
        break;

      case "remainingValue":
        aValue = a.remaining_value || 0;
        bValue = b.remaining_value || 0;
        break;

      default:
        return 0;
    }

    if (sortConfig.direction === "asc") return aValue - bValue;
    if (sortConfig.direction === "desc") return bValue - aValue;

    return 0;
  });

  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key !== key) return { key, direction: "asc" };
      if (prev.direction === "asc") return { key, direction: "desc" };
      return { key: null, direction: null };
    });
  };

  return (
    <div className="w-full bg-white dark:bg-[#0f172a] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm">
      <PageHeader title="Remaining Inventory" />

      {/* ================= FILTER ================= */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 px-6 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 bg-gray-100 dark:bg-[#020617] p-1 rounded-full">
            {["daily", "weekly", "monthly", "custom"].map((type) => (
              <button
                key={type}
                onClick={() => {
                  setPeriod(type);

                  if (type !== "custom") {
                    setCustomFrom("");
                    setCustomTo("");
                  }
                }}
                className={`px-4 py-1.5 text-sm rounded-full font-medium transition
                            ${
                              period === type
                                ? "bg-orange-500 text-white"
                                : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800"
                            }`}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <input
              type="date"
              value={customFrom}
              onChange={(e) => setCustomFrom(e.target.value)}
              disabled={period !== "custom"}
              className={`px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200
  ${period !== "custom" ? "opacity-60 cursor-not-allowed" : ""}`}
            />

            <span>-</span>

            <input
              type="date"
              value={customTo}
              onChange={(e) => setCustomTo(e.target.value)}
              disabled={period !== "custom"}
              className={`px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200
  ${period !== "custom" ? "opacity-60 cursor-not-allowed" : ""}`}
            />
          </div>
        </div>

        <button
          onClick={handleDownloadReport}
          className="flex items-center gap-2 px-5 py-2 rounded-lg 
  bg-gradient-to-r from-orange-500 to-orange-600 
  text-white text-sm font-semibold 
  shadow-md hover:shadow-lg hover:scale-[1.02] 
  transition-all duration-200"
        >
          Download Report
          <FiDownload className="text-lg" />
        </button>
      </div>

      {/* ================= CARDS ================= */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 px-6 pb-4">
        <Card
          title="Opening Stock"
          value={`₹${summary.opening_stock || 0}`}
          icon={<FiPackage className="text-blue-500" />}
        />
        <Card
          title="Highest Expense"
          value={capitalizeWords(summary.highest_expense_item || "-")}
          price={summary.highest_expense_value}
          icon={<FiTrendingUp className="text-orange-500" />}
        />
        <Card
          title="Lowest Expense"
          value={capitalizeWords(summary.lowest_expense_item || "-")}
          price={summary.lowest_expense_value}
          icon={<FiTrendingDown className="text-red-500" />}
        />
        <Card
          title="Wastage"
          value={`₹${summary.wastage || 0}`}
          icon={<FiTrendingDown className="text-red-500" />}
        />
        <Card
          title="Closing Stock"
          value={`₹${Number(summary.closing_stock || 0).toFixed(2)}`}
          icon={<FiPackage className="text-indigo-500" />}
        />{" "}
        {/* <Card
          title="Revenue"
          value={`₹${summary.revenue || 0}`}
          icon={<FiTrendingUp className="text-green-500" />}
        /> */}
        {/* <Card
          title="COGS"
          value={`₹${summary.cogs || 0}`}
          icon={<FaRupeeSign className="text-orange-500" />}
        /> */}
        <Card
          title="Most Frequent"
          value={capitalizeWords(
            summary.most_frequent_purchased_inventory || "-",
          )}
          price={summary.most_frequent_purchased_value}
          icon={<FiPackage className="text-purple-500" />}
        />
      </div>

      {/* ================= TABLE ================= */}
      <div className="px-6 pb-4">
        <div className="mb-4 flex justify-end">
          <div className="relative w-72">
            {/* Search Icon */}
            <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg" />

            <input
              type="text"
              placeholder="Search items..."
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
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
        <div className="border border-gray-300 dark:border-gray-700 rounded-xl overflow-hidden bg-white dark:bg-[#0f172a]">
          <div className="overflow-x-auto overflow-y-auto max-h-[400px]">
            <table className="w-full">
              <thead className="sticky top-0 bg-gray-200 dark:bg-[#1e293b] border-b border-gray-300 dark:border-gray-600 z-10">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-100">
                    Item
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-semibold">
                    <div className="flex items-center gap-1  text-gray-800 dark:text-gray-100">
                      Opening
                      <span
                        onClick={() => handleSort("openingQty")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "openingQty" ? (
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
                  <th className="px-4 py-3 text-left text-sm font-semibold">
                    <div className="flex items-center gap-1  text-gray-800 dark:text-gray-100">
                      Wastage
                      <span
                        onClick={() => handleSort("wastageQty")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "wastageQty" ? (
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
                  <th className="px-4 py-3 text-left text-sm font-semibold">
                    <div className="flex items-center gap-1  text-gray-800 dark:text-gray-100">
                      Closing
                      <span
                        onClick={() => handleSort("closingQty")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "closingQty" ? (
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
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-100">
                    <div className="flex items-center gap-1">
                      Opening Value
                      <span
                        onClick={() => handleSort("openingValue")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "openingValue" ? (
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
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-100">
                    <div className="flex items-center gap-1">
                      Closing Value
                      <span
                        onClick={() => handleSort("closingValue")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "closingValue" ? (
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
                  <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-100">
                    <div className="flex items-center gap-1">
                      Remaining Value
                      <span
                        onClick={() => handleSort("remainingValue")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "remainingValue" ? (
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
                </tr>
              </thead>

              <tbody>
                {loading ? (
                  <tr>
                    <td
                      colSpan="7"
                      className="text-center py-10 text-gray-600 dark:text-gray-300"
                    >
                      Loading...
                    </td>
                  </tr>
                ) : sortedItems.length === 0 ? (
                  <tr>
                    <td
                      colSpan="7"
                      className="text-center py-10 text-gray-500 dark:text-gray-400"
                    >
                      📦 No data available
                    </td>
                  </tr>
                ) : (
                  sortedItems.map((item) => (
                    <tr
                      key={item.item_id}
                      className="border-t border-gray-300 dark:border-gray-700 
                                        bg-white dark:bg-[#0f172a] 
                                        hover:bg-gray-100 dark:hover:bg-[#1e293b] transition"
                    >
                      <td className="px-4 py-3 text-gray-800 dark:text-gray-200 font-medium">
                        {capitalizeWords(item.item_name)}
                      </td>
                      <td className="px-4 py-3 text-gray-800 dark:text-gray-200">
                        {item.opening.quantity_display}
                      </td>
                      <td className="px-4 py-3 text-red-600 dark:text-red-400 font-medium">
                        {item.wastage.quantity_display}
                      </td>
                      <td className="px-4 py-3 text-gray-800 dark:text-gray-200">
                        {item.closing.quantity_display}
                      </td>
                      <td className="px-4 py-3 text-gray-800 dark:text-gray-200">
                        ₹{item.opening.value}
                      </td>
                      <td className="px-4 py-3 text-gray-800 dark:text-gray-200">
                        ₹{item.closing.value}
                      </td>
                      <td className="px-4 py-3 font-semibold text-gray-900 dark:text-white">
                        ₹{item.remaining_value}
                      </td>
                    </tr>
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
    </div>
  );
}

/* ================= CARD ================= */
function Card({ title, value, icon, price }) {
  return (
    <div
      className="bg-white dark:bg-[#020617]
        border border-gray-200 dark:border-gray-700
        rounded-xl px-5 py-4"
    >
      {/* TOP ROW → TITLE + ICON */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>

        <div className="text-2xl">{icon}</div>
      </div>

      {/* BOTTOM ROW → VALUE + PRICE (like wastage tab) */}
      <div className="flex items-center justify-between mt-2">
        <span className="text-xl font-semibold text-gray-900 dark:text-white">
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
