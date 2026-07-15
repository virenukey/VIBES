import React, { useState, useEffect } from "react";
import {
  FiPlus,
  FiSearch,
  FiEdit,
  FiChevronLeft,
  FiChevronRight,
  FiChevronRight as RowClosed,
  FiChevronDown as RowOpen,
  FiTrash2,
} from "react-icons/fi";

import { MdDeleteOutline } from "react-icons/md";

import AddComboModal from "./AddComboModal";
import api from "../../api/axios";
export default function ComboTab() {
  const [expandedCombo, setExpandedCombo] = useState(null);

  const [showComboModal, setShowComboModal] = useState(false);
  const [editCombo, setEditCombo] = useState(null);

  const [rowsPerPage, setRowsPerPage] = useState(5);

  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [searchText, setSearchText] = useState("");
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [combos, setCombos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  const [selectedCombo, setSelectedCombo] = useState(null);

  const [deleteLoading, setDeleteLoading] = useState(false);

  useEffect(() => {
    fetchDishTypes();
  }, []);

  useEffect(() => {
    fetchCombos();
  }, [currentPage, rowsPerPage, searchText, selectedCategory]);

  const fetchDishTypes = async () => {
    try {
      const res = await api.get("/dish/get_dish_types");

      setCategories(res.data.data || []);
    } catch (err) {
      console.error("Failed to fetch dish types", err);
    }
  };

  const fetchCombos = async () => {
    try {
      setLoading(true);

      const params = {
        page: currentPage,
        page_size: rowsPerPage,
      };

      if (searchText) {
        params.search = searchText;
      }

      if (selectedCategory) {
        params.type_id = selectedCategory;
      }

      const res = await api.get("/dish/", {
        params,
      });

      setCombos(res.data.combos || []);
      setTotalPages(
        res.data.record?.total_pages ||
          res.data.meta?.total_pages ||
          res.data.pagination?.total_pages ||
          1,
      );
    } catch (err) {
      console.error("Failed to fetch combos", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCombo = async () => {
    try {
      setDeleteLoading(true);

      await api.delete(`/dish/${selectedCombo.id}`);

      fetchCombos();

      setShowDeleteModal(false);

      setSelectedCombo(null);
    } catch (err) {
      console.error("Failed to delete combo", err);
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div className="w-full">
      {/* TOOLBAR */}

      <div className="flex flex-col gap-3 px-4 sm:px-6 py-4">
        {/* TOP ROW */}

        <div className="flex justify-between items-center">
          {/* CATEGORY */}

          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="w-xs px-3 py-2 rounded-lg
  border border-gray-200 dark:border-gray-700
  bg-white dark:bg-[#0f172a]
  text-sm text-gray-800 dark:text-gray-200
  outline-none
  focus:ring-2 focus:ring-orange-400"
          >
            <option value="">All Categories</option>

            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>

          {/* RIGHT */}

          <div className="flex items-center gap-3">
            {/* SEARCH */}

            <div className="relative">
              <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg" />

              <input
                type="text"
                placeholder="Search combo..."
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                className="w-64 sm:w-72 pl-10 pr-4 py-2 rounded-xl 
    border-2 border-orange-400
    bg-white dark:bg-[#0f172a]
    text-sm text-gray-800 dark:text-gray-200
    outline-none
    transition-all duration-200"
              />
            </div>

            {/* ADD BUTTON */}

            <button
              onClick={() => {
                setEditCombo(null);
                setShowComboModal(true);
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium
    bg-white dark:bg-[#0f172a] text-gray-800 dark:text-gray-200
    border-gray-200 dark:border-gray-700
    hover:bg-gray-50 dark:hover:bg-gray-800 transition"
            >
              <FiPlus />
              Add Combo
            </button>

            {/* DOWNLOAD */}
          </div>
        </div>
      </div>

      {/* TABLE */}

      <div className="px-4 sm:px-6 pb-4">
        <div
          className="border border-gray-200 dark:border-gray-800
  rounded-xl overflow-hidden
  bg-white dark:bg-[#0f172a]"
        >
          <div className="overflow-x-auto">
            <table className="w-full">
              {/* HEADER */}

              <thead className="bg-gray-100 dark:bg-gray-900">
                <tr>
                  <th
                    className="px-16 py-3 text-left text-sm font-semibold
text-gray-800 dark:text-gray-200"
                  >
                    Combo
                  </th>

                  <th
                    className="px-4 py-3 text-left text-sm font-semibold
text-gray-800 dark:text-gray-200"
                  >
                    Category
                  </th>

                  <th
                    className="px-4 py-3 text-left text-sm font-semibold
text-gray-800 dark:text-gray-200"
                  >
                    Price
                  </th>

                  <th
                    className="px-25 py-3 text-left text-sm font-semibold
text-gray-800 dark:text-gray-200"
                  >
                    Combo Items
                  </th>

                  <th
                    className="px-4 py-3 text-left text-sm font-semibold
text-gray-800 dark:text-gray-200"
                  >
                    Cost/Combo
                  </th>

                  <th
                    className="pl-8 py-3 text-left text-sm font-semibold
text-gray-800 dark:text-gray-200"
                  >
                    Edit
                  </th>

                  <th
                    className="pl-8 py-3 text-left text-sm font-semibold
text-gray-800 dark:text-gray-200"
                  >
                    Delete
                  </th>
                </tr>
              </thead>

              {/* BODY */}

              <tbody>
                {combos.map((combo) => (
                  <React.Fragment key={combo.id}>
                    {/* MAIN ROW */}

                    <tr
                      className="border-t border-gray-200 dark:border-gray-800
  hover:bg-gray-50 dark:hover:bg-[#020617]"
                    >
                      {/* NAME */}

                      <td className="px-4 py-4">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() =>
                              setExpandedCombo(
                                expandedCombo === combo.id ? null : combo.id,
                              )
                            }
                            className="p-1 rounded hover:bg-gray-200 transition"
                          >
                            {expandedCombo === combo.id ? (
                              <RowOpen className="text-gray-600" />
                            ) : (
                              <RowClosed className="text-gray-600" />
                            )}
                          </button>

                          <span
                            className="font-medium text-sm
  text-gray-800 dark:text-gray-200"
                          >
                            {combo.name}
                          </span>
                        </div>
                      </td>

                      {/* CATEGORY */}

                      <td className="px-4 py-4">
                        <span
                          className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold
                          bg-gray-200 dark:bg-gray-700
text-gray-800 dark:text-gray-200"
                        >
                          {combo.type_name}
                        </span>
                      </td>

                      {/* PRICE */}

                      <td
                        className="px-4 py-4 text-sm font-medium
text-gray-800 dark:text-gray-200"
                      >
                        ₹{combo.selling_price ?? 0}
                      </td>

                      {/* DISH TAGS */}

                      <td className="px-4 py-4">
                        <div className="flex flex-wrap gap-2">
                          {combo.items.map((dish, index) => (
                            <span
                              key={index}
                              className="
        px-3 py-1 text-xs rounded-full border
        bg-green-100 dark:bg-green-900/20
        text-green-700 dark:text-green-300
        border-green-300 dark:border-green-800
        font-medium
      "
                            >
                              {dish.item_name}
                            </span>
                          ))}
                        </div>
                      </td>

                      {/* COST */}

                      <td
                        className="px-4 py-4 text-sm font-semibold
text-gray-800 dark:text-gray-200"
                      >
                        ₹{combo.computed_price}
                      </td>

                      {/* EDIT */}

                      <td className="px-4 py-4 text-center">
                        <button
                          onClick={() => {
                            setEditCombo(combo);
                            setShowComboModal(true);
                          }}
                          className="p-2 rounded
  hover:bg-gray-100 dark:hover:bg-gray-800
  text-gray-700 dark:text-gray-200"
                        >
                          <FiEdit />
                        </button>
                      </td>

                      {/* DELETE */}

                      <td className="px-4 py-4 text-center">
                        <button
                          onClick={() => {
                            setSelectedCombo(combo);
                            setShowDeleteModal(true);
                          }}
                          className="p-2 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                          <FiTrash2 className="text-red-600" />
                        </button>
                      </td>
                    </tr>

                    {/* EXPANDABLE ROW */}

                    {expandedCombo === combo.id && (
                      <tr>
                        <td colSpan={7} className="px-6 py-5">
                          {/* TITLE */}

                          <p className="text-orange-600 text-sm font-semibold mb-4">
                            Dish Breakdown
                          </p>

                          {/* CARDS */}

                          <div className="flex flex-wrap gap-4">
                            {combo.items.map((dish, index) => (
                              <div
                                key={index}
                                className="
  w-[150px]
  min-h-[150px]

  rounded-xl

  border border-gray-200
  dark:border-gray-700

  p-3

  bg-white
  dark:bg-[#0f172a]

  shadow-sm

  flex flex-col
  justify-between
"
                              >
                                <div className="space-y-1">
                                  <h3
                                    className="
      text-sm font-semibold
      text-gray-800 dark:text-gray-200

      line-clamp-2
      leading-5
    "
                                  >
                                    {dish.item_name}
                                  </h3>

                                  <p
                                    className="
      text-xs mt-1
      text-gray-500 dark:text-gray-400

      
    "
                                  >
                                    {dish.item_type === "semi_finished"
                                      ? "Prepared Item"
                                      : dish.item_type === "ingredient"
                                        ? "Inventory Item"
                                        : "Dish"}
                                  </p>
                                </div>

                                <div className="mt-3">
                                  <p className="text-orange-500 text-sm font-semibold">
                                    ₹{dish.line_cost}
                                  </p>

                                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                                    Qty: {dish.quantity}{" "}
                                    {dish.unit?.toLowerCase() === "piece"
                                      ? "plate"
                                      : dish.unit}
                                  </p>
                                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    Unit Cost: ₹{dish.cost_per_unit}
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {/* PAGINATION */}

          <div
            className="flex items-center justify-end gap-6 flex-wrap
  px-4 sm:px-6 py-5 border-t border-gray-200 dark:border-gray-800"
          >
            {/* ROWS PER PAGE */}
            <div
              className="flex items-center gap-2 text-sm
    text-gray-800 dark:text-gray-200"
            >
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

            {/* PAGINATION */}
            <div className="flex items-center gap-1 flex-wrap">
              {/* FIRST */}
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

              {/* PREVIOUS */}
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

              {/* DYNAMIC PAGES */}
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
                      key={`page-${page}`}
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

              {/* NEXT */}
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

              {/* LAST */}
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

      {/* DELETE MODAL */}

      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* BACKDROP */}

          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setShowDeleteModal(false)}
          />

          {/* MODAL */}

          <div
            className="relative w-full max-w-md rounded-2xl
      bg-white dark:bg-[#0f172a]
      border border-gray-200 dark:border-gray-800
      shadow-2xl p-6"
          >
            {/* TITLE */}

            <h2 className="text-xl font-bold text-gray-900 dark:text-white">
              Delete Combo
            </h2>

            <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
              Are you sure you want to delete{" "}
              <span className="font-semibold text-red-500">
                {selectedCombo?.name}
              </span>
              ?
            </p>

            {/* ACTIONS */}

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowDeleteModal(false)}
                className="px-4 py-2 rounded-xl
          border border-gray-300 dark:border-gray-700
          bg-white dark:bg-[#0f172a]
          text-gray-700 dark:text-gray-300
          hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                Cancel
              </button>

              <button
                onClick={handleDeleteCombo}
                disabled={deleteLoading}
                className="px-4 py-2 rounded-xl
          bg-red-500 hover:bg-red-600
          disabled:opacity-50
          text-white font-semibold"
              >
                {deleteLoading ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL */}

      <AddComboModal
        isOpen={showComboModal}
        onClose={() => {
          setShowComboModal(false);
          setEditCombo(null);
        }}
        editData={editCombo}
        fetchCombos={fetchCombos}
      />
    </div>
  );
}
