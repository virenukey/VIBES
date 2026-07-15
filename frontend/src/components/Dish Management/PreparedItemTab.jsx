import React, { useEffect, useState } from "react";
import AddPreparedItemModal from "./AddPreparedItemModal";
import { Plus } from "lucide-react";
import { FiChevronRight, FiChevronDown, FiChevronLeft } from "react-icons/fi";
import api from "../../api/axios";
import AddExcelModal from "../Inventory Management/AddExcelModal";
import { capitalizeWords } from "../../utils/text";
import { toast } from "react-toastify";
import {
  FiEdit,
  FiTrash2,
  FiFileText,
  FiArrowUp,
  FiArrowDown,
  FiMinus,
  FiPlus,
} from "react-icons/fi";

const formatCost = (num) => {
  const value = Number(num || 0);

  // For normal numbers → truncate to 2 decimals
  if (value >= 0.01) {
    return (Math.floor(value * 100) / 100).toFixed(2);
  }

  // For very small numbers → show meaningful precision
  return Number(value.toPrecision(2)).toString();
};

const PreparedItemTab = () => {
  const [openModal, setOpenModal] = useState(false);
  const [items, setItems] = useState([]);
  const [expandedRow, setExpandedRow] = useState(null);
  const [editItem, setEditItem] = useState(null);
  const [deleteId, setDeleteId] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [showExcelModal, setShowExcelModal] = useState(false);
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);

  const [totalPages, setTotalPages] = useState(1);
  const [searchText, setSearchText] = useState("");

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: null,
  });

  const fetchPreparedItems = async () => {
    try {
      const res = await api.get(
        `/dish/semi-finished-ingredients?page=${currentPage}&page_size=${rowsPerPage}&search=${searchText}`,
      );

      console.log("Prepared Items API:", res.data);

      setItems(res.data.data || res.data.items || []);

      setTotalPages(res.data.meta?.total_pages || 1);
    } catch (err) {
      console.error("Failed to fetch prepared items", err);
    }
  };

  useEffect(() => {
    fetchPreparedItems();
  }, [currentPage, rowsPerPage, searchText]);

  const handleDelete = async () => {
    if (!deleteId) return;

    const id = deleteId;
    setDeleteId(null);
    setItems((prev) => prev.filter((item) => item.semi_finished_id !== id));

    try {
      setDeleting(true);

      await api.delete(`/dish/semi-finished-ingredients/${id}`);
      toast.success("Deleted successfully 🗑️");
    } catch (err) {
      console.error(err);

      toast.error("Delete failed ❌");

      fetchPreparedItems();
    } finally {
      setDeleting(false);
    }
  };

  const getTotalCost = (item) => {
    return (
      item.ingredients?.reduce(
        (sum, ing) =>
          sum +
          (ing.fixed_cost_amount && ing.fixed_cost_amount > 0
            ? ing.fixed_cost_amount
            : (ing.quantity_required || 0) * (ing.cost_per_unit || 0)),
        0,
      ) || 0
    );
  };

  const sortedItems = [...items].sort((a, b) => {
    if (!sortConfig.key) return 0;

    let aValue = 0;
    let bValue = 0;

    switch (sortConfig.key) {
      case "yield":
        aValue = a.yield_quantity || 0;
        bValue = b.yield_quantity || 0;
        break;

      case "cost":
        aValue = a.unit_cost || 0;
        bValue = b.unit_cost || 0;
        break;

      case "totalCost":
        aValue = getTotalCost(a);
        bValue = getTotalCost(b);
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
    <div className="w-full bg-white dark:bg-[#0f172a] rounded-xl border border-gray-200 dark:border-gray-800">
      <div className="flex flex-col gap-3 px-4 sm:px-6 py-4">
        {/* ROW 1 → Heading + Download */}
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            Prepared Items
          </h2>

          <a
            href="prepared_items_excel_format.xlsx"
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
        <div className="flex flex-wrap justify-end items-center gap-3">
          <input
            type="text"
            placeholder="Search prepared items..."
            value={searchText}
            onChange={(e) => {
              setSearchText(e.target.value);
              setCurrentPage(1);
            }}
            className="w-72 px-4 py-2 rounded-xl
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-800 dark:text-gray-200
  outline-none"
          />
          <button
            onClick={() => {
              setEditItem(null);
              setOpenModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium
    bg-white dark:bg-[#0f172a] text-gray-800 dark:text-gray-200
    border-gray-200 dark:border-gray-700
    hover:bg-gray-50 dark:hover:bg-gray-800 transition"
          >
            <FiPlus />
            Add Prepared Item
          </button>

          <button
            onClick={() => setShowExcelModal(true)}
            className="px-4 py-2 border border-gray-300 dark:border-gray-700 
      text-gray-800 dark:text-gray-200 rounded-lg 
      hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            Add via Excel
          </button>
        </div>
      </div>

      {/* TABLE */}
      <div className="px-4 sm:px-6 pb-4">
        <div className="border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto overflow-y-auto max-h-[400px]">
            <table className="w-full">
              {/* HEADER */}
              <thead className="bg-gray-100 dark:bg-gray-900">
                <tr>
                  <th className="px-4 py-3 text-left text-sm text-gray-700 dark:text-gray-300">
                    Name
                  </th>
                  <th className="px-4 py-3 text-left text-sm text-gray-700 dark:text-gray-300">
                    <div className="flex items-center gap-1">
                      Yield
                      <span
                        onClick={() => handleSort("yield")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "yield" ? (
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
                  <th className="px-4 py-3 text-left text-sm text-gray-700 dark:text-gray-300">
                    <div className="flex items-center gap-1">
                      Cost/Unit
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
                  <th className="px-4 py-3 text-left text-sm text-gray-700 dark:text-gray-300">
                    <div className="flex items-center gap-1">
                      Total Production Cost
                      <span
                        onClick={() => handleSort("totalCost")}
                        className="cursor-pointer"
                      >
                        {sortConfig.key === "totalCost" ? (
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
                  </th>{" "}
                  <th className="px-4 py-3 text-left text-sm text-gray-700 dark:text-gray-300">
                    Ingredients
                  </th>
                  <th className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">
                    Edit
                  </th>
                  <th className="px-4 py-3 text-center text-sm text-gray-700 dark:text-gray-300">
                    Delete
                  </th>
                </tr>
              </thead>

              <tbody>
                {sortedItems.map((item) => (
                  <React.Fragment key={item.semi_finished_id}>
                    <tr className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-[#020617]/80">
                      <td className="px-4 py-3 flex items-center gap-2">
                        <button
                          onClick={() =>
                            setExpandedRow(
                              expandedRow === item.semi_finished_id
                                ? null
                                : item.semi_finished_id,
                            )
                          }
                          className="p-1 rounded hover:bg-gray-200 dark:text-white dark:hover:bg-gray-700"
                        >
                          {expandedRow === item.semi_finished_id ? (
                            <FiChevronDown />
                          ) : (
                            <FiChevronRight />
                          )}
                        </button>

                        <span className="font-medium text-gray-900 dark:text-gray-100">
                          {capitalizeWords(item.name)}
                        </span>
                      </td>

                      {/* YIELD */}
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                        {item.yield_quantity} {item.yield_unit}
                      </td>

                      {/* COST PER UNIT */}
                      <td className="px-4 py-3 text-sm font-semibold text-green-600">
                        ₹{formatCost(item.unit_cost)}
                      </td>

                      {/* TOTAL COST */}
                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100">
                        ₹
                        {formatCost(
                          item.ingredients?.reduce(
                            (sum, ing) =>
                              sum +
                              (ing.fixed_cost_amount &&
                              ing.fixed_cost_amount > 0
                                ? ing.fixed_cost_amount
                                : (ing.quantity_required || 0) *
                                  (ing.cost_per_unit || 0)),
                            0,
                          ),
                        )}
                      </td>

                      {/* INGREDIENT COUNT */}
                      <td className="px-4 py-3 text-sm">
                        <span className="px-3 py-1 text-xs rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
                          {item.ingredient_count} items
                        </span>
                      </td>

                      {/* EDIT */}
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => {
                            setEditItem(item);
                            setOpenModal(true);
                          }}
                          className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800 dark:text-white"
                        >
                          <FiEdit />
                        </button>
                      </td>

                      {/* DELETE */}
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={() => setDeleteId(item.semi_finished_id)}
                          className="p-2 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                          <FiTrash2 className="text-red-600" />
                        </button>
                      </td>
                    </tr>

                    {expandedRow === item.semi_finished_id && (
                      <tr>
                        <td colSpan={5} className="px-6 py-4">
                          <p className="text-orange-600 dark:text-orange-400 font-semibold mb-3">
                            Ingredient Breakdown
                          </p>

                          <div className="flex flex-wrap gap-3">
                            {item.ingredients?.map((ing) => {
                              const isPrepared = ing.is_semi_finished === true;

                              return (
                                <div
                                  key={ing.id}
                                  className={`border rounded-lg px-4 py-3
        ${
          isPrepared
            ? "border-orange-200 dark:border-orange-300 bg-orange-50 dark:bg-orange-900/30"
            : "border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0b1220]"
        }`}
                                >
                                  {/* NAME */}
                                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                                    {capitalizeWords(ing.ingredient_name)}
                                  </p>

                                  {/* QUANTITY */}
                                  <p className="text-xs text-gray-500 dark:text-gray-400">
                                    {ing.quantity_required} {ing.unit}
                                  </p>

                                  {/* COST */}
                                  <p className="text-xs text-orange-500 font-semibold">
                                    ₹
                                    {formatCost(
                                      ing.fixed_cost_amount &&
                                        ing.fixed_cost_amount > 0
                                        ? ing.fixed_cost_amount
                                        : (ing.quantity_required || 0) *
                                            (ing.cost_per_unit || 0),
                                    )}
                                  </p>

                                  {/* COST PER UNIT */}
                                  <p className="text-xs text-gray-400">
                                    {ing.fixed_cost_amount &&
                                    ing.fixed_cost_amount > 0 ? (
                                      <span className="text-xs text-gray-400">
                                        Fixed Cost
                                      </span>
                                    ) : (
                                      <span className="text-xs text-gray-400">
                                        ₹{formatCost(ing.cost_per_unit)}
                                        /unit
                                      </span>
                                    )}
                                  </p>
                                </div>
                              );
                            })}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {/* Pagination */}
          <div
            className="flex items-center justify-end gap-6 flex-wrap
  px-4 sm:px-6 py-5 border-t border-gray-200 dark:border-gray-800"
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
                  // DOTS
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
                      key={`page-${page}-${index}`}
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
      {/* MODAL */}
      {openModal && (
        <AddPreparedItemModal
          onClose={() => {
            setOpenModal(false);
            setEditItem(null);
          }}
          onSuccess={fetchPreparedItems}
          editData={editItem}
        />
      )}

      <AddExcelModal
        isOpen={showExcelModal}
        onClose={() => setShowExcelModal(false)}
        onSuccess={fetchPreparedItems}
        uploadUrl="/dish/add-semi-finished-ingredients-via-excel"
      />

      {deleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Overlay */}
          <div className="absolute inset-0 bg-black/40" />

          {/* Modal */}
          <div
            className="relative w-full max-w-md sm:max-w-lg 
    bg-white dark:bg-[#020617] 
    p-6 sm:p-8 rounded-2xl shadow-2xl
    border border-gray-200 dark:border-gray-800"
          >
            <h2 className="text-lg font-semibold mb-3 text-gray-900 dark:text-white">
              Delete Item
            </h2>

            <p className="text-sm mb-6 text-gray-600 dark:text-gray-400">
              Are you sure you want to delete this prepared item?
            </p>

            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteId(null)}
                className="px-4 py-2 rounded-lg 
          text-gray-700 dark:text-gray-300 
          hover:bg-gray-100 dark:hover:bg-gray-800 transition"
              >
                Cancel
              </button>

              <button
                onClick={handleDelete}
                disabled={deleting}
                className={`px-4 py-2 rounded-lg text-white transition
                                   ${
                                     deleting
                                       ? "bg-gray-400 cursor-not-allowed"
                                       : "bg-red-500 hover:bg-red-600"
                                   }`}
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PreparedItemTab;
