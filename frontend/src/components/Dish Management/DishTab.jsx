import React, { useState, useEffect, useMemo } from "react";
import PageHeader from "../PageHeader";
import {
  FiPlus,
  FiSearch,
  FiEdit,
  FiTrash2,
  FiFileText,
  FiChevronLeft,
  FiChevronRight,
  FiChevronRight as RowClosed,
  FiChevronDown as RowOpen,
  FiArrowUp,
  FiArrowDown,
  FiMinus,
} from "react-icons/fi";
import { toast } from "react-toastify";

import AddDishModal from "./AddDishModal";
import DishCategoryTab from "./DishCategoryTab";
import api from "../../api/axios";
import ViewDishModal from "./ViewDishModal";
import AddExcelModal from "../Inventory Management/AddExcelModal";
import IngredientManagementTab from "./IngredientManagementTab";
import PreparedItemTab from "./PreparedItemTab";
import ComboTab from "./ComboTab";
import { capitalizeWords } from "../../utils/text";

export default function DishTab() {
  const [activeTab, setActiveTab] = useState("dish");

  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [dishes, setDishes] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [categoryOptions, setCategoryOptions] = useState([]);

  const [showDishModal, setShowDishModal] = useState(false);
  const [editDish, setEditDish] = useState(null);
  const [viewDish, setViewDish] = useState(null);

  const [expandedDish, setExpandedDish] = useState(null);
  const [showExcelModal, setShowExcelModal] = useState(false);
  const [deleteId, setDeleteId] = useState(null);
  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: null,
  });

  /* ================= FETCH ================= */

  useEffect(() => {
    if (activeTab === "dish") {
      fetchDishes();
    }
  }, [activeTab, currentPage, rowsPerPage, searchText, selectedCategoryId]);

  const fetchDishes = async () => {
    try {
      const safePage = currentPage < 1 ? 1 : currentPage;

      const queryParams = new URLSearchParams({
        page: safePage,
        page_size: rowsPerPage,
        search: searchText || "",
      });

      if (selectedCategoryId) {
        queryParams.append("type_id", selectedCategoryId);
      }

      const res = await api.get(
        `/dish/get-dishes-with-ingredients?${queryParams.toString()}`,
      );
      // console.log("FULL API RESPONSE:", res.data);
      // console.log(res.data.dishes);

      const formatted = res.data.dishes.map((dish) => ({
        id: dish.id,
        name: dish.name,
        category_name: dish.category_name,
        selling_price: dish.selling_price,
        cost_per_dish: dish.total_dish_cost,
        ingredients: dish.ingredients?.map((ing) => {
          const isPrepared =
            ing.is_semi_finished === true || ing.semi_finished_id !== null;
          return {
            item: isPrepared
              ? `prep-${ing.semi_finished_id}` //  using ID
              : `inv-${ing.ingredient_id}`,
            name: ing.ingredient_name,
            qty: ing.quantity_required,
            unit: ing.unit,
            cost: ing.ingredient_total_cost,
            cost_per_unit: ing.cost_per_unit,
            fixed_cost_amount: ing.fixed_cost_amount, //  pass this too
          };
        }),
      }));
      setDishes(formatted);

      setTotalPages(res.data.meta?.total_pages || 1);
    } catch (err) {
      console.error("Failed to fetch dishes", err);
    }
  };

  const fetchDishTypes = async () => {
    try {
      const res = await api.get("/dish/get_dish_types");

      setCategoryOptions(res.data?.data || []);
    } catch (err) {
      console.error("Failed to fetch dish types", err);
    }
  };

  useEffect(() => {
    fetchDishTypes();
  }, []);
  /* ================= CATEGORY OPTIONS ================= */

  const sortedData = [...dishes].sort((a, b) => {
    if (!sortConfig.key) return 0;

    let aValue = 0;
    let bValue = 0;

    switch (sortConfig.key) {
      case "price":
        aValue = a.selling_price || 0;
        bValue = b.selling_price || 0;
        break;

      case "cost":
        aValue = a.cost_per_dish || 0;
        bValue = b.cost_per_dish || 0;
        break;

      default:
        return 0;
    }

    if (sortConfig.direction === "asc") return aValue - bValue;
    if (sortConfig.direction === "desc") return bValue - aValue;

    return 0;
  });
  /* ================= DELETE ================= */

  const handleDelete = async () => {
    if (!deleteId) return;

    try {
      await api.delete(`/dish/delete_dish/${deleteId}`);

      toast.success("Dish deleted successfully 🗑️");

      fetchDishes();
    } catch (err) {
      console.error("Delete failed", err);

      toast.error("Failed to delete dish ❌");
    } finally {
      setDeleteId(null);
    }
  };

  const handleSort = (key) => {
    setSortConfig((prev) => {
      if (prev.key !== key) return { key, direction: "asc" };
      if (prev.direction === "asc") return { key, direction: "desc" };
      return { key: null, direction: null };
    });
  };
  return (
    <div className="w-full bg-white dark:bg-[#0f172a] rounded-xl border border-gray-200 dark:border-gray-800">
      <PageHeader
        title="Dish Management"
        tabs={[
          { key: "dish-category", label: "Dish Category" },
          { key: "dish", label: "Dishes" },
          { key: "combo", label: "Combos" },
          { key: "prepared", label: "Prepared Item" },
          // { key: "ingredient", label: "Ingredient management" },
        ]}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      {/* ================= DISH TAB ================= */}

      {activeTab === "dish" && (
        <div className="w-full">
          {/* Toolbar */}

          <div className="flex flex-col gap-3 px-4 sm:px-6 py-4">
            {/* TOP ROW → Category + Download */}
            <div className="flex justify-between items-center">
              {/* LEFT → Category Dropdown */}
              <select
                value={selectedCategoryId}
                onChange={(e) => {
                  setSelectedCategoryId(e.target.value);
                  setCurrentPage(1);
                  setCurrentPage(1);
                }}
                className="w-xs px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700
      bg-white dark:bg-[#0f172a]
      text-sm text-gray-800 dark:text-gray-200 outline-none
      focus:ring-2 focus:ring-orange-400"
              >
                <option value="">All Categories</option>

                {categoryOptions.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>

              {/* RIGHT → Download Button */}
              <a
                href="/dish_upload_sheet.xlsx"
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

            {/* SECOND ROW → Search + Actions */}
            <div className="flex flex-wrap items-center gap-3 justify-end">
              {/* Search */}
              <div className="relative">
                {/* Search Icon */}
                <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg" />

                <input
                  type="text"
                  placeholder="Search dish..."
                  value={searchText}
                  onChange={(e) => {
                    setSearchText(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="w-64 sm:w-72 pl-10 pr-4 py-2 rounded-xl 
    border-2 border-orange-400
    bg-white dark:bg-[#0f172a]
    text-sm text-gray-800 dark:text-gray-200
    outline-none
    transition-all duration-200"
                />
              </div>

              {/* Add Dish */}
              <button
                onClick={() => {
                  setEditDish(null);
                  setShowDishModal(true);
                }}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium
    bg-white dark:bg-[#0f172a] text-gray-800 dark:text-gray-200
    border-gray-200 dark:border-gray-700
    hover:bg-gray-50 dark:hover:bg-gray-800 transition"
              >
                <FiPlus />
                Add Dish
              </button>

              {/* Add via Excel */}
              <button
                onClick={() => setShowExcelModal(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 
    bg-white dark:bg-[#0f172a] text-sm font-medium text-gray-800 dark:text-gray-200 
    hover:bg-gray-50 dark:hover:bg-gray-800 transition"
              >
                <FiFileText className="text-lg" />
                Add via excel
              </button>
            </div>
          </div>

          {/* TABLE */}
          <div className="px-4 sm:px-6 pb-4">
            <div className="border border-gray-200 dark:border-gray-800 rounded-xl overflow-hidden">
              <div className="overflow-x-auto overflow-y-auto max-h-[400px]">
                <table className="w-full">
                  <thead className="sticky top-0 bg-gray-100 dark:bg-gray-900 z-10">
                    <tr>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                        Dish
                      </th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                        Category
                      </th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
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
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                        Ingredients
                      </th>
                      <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                        <div className="flex items-center gap-1">
                          Cost/Dish
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
                      <th className="px-4 py-3 text-center text-sm font-semibold text-gray-800 dark:text-gray-200">
                        Edit
                      </th>
                      <th className="px-4 py-3 text-center text-sm font-semibold text-gray-800 dark:text-gray-200">
                        Delete
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {sortedData.length === 0 ? (
                      <tr>
                        <td
                          colSpan={7}
                          className="text-center py-10 text-gray-500 dark:text-gray-400"
                        >
                          <div className="flex flex-col items-center justify-center gap-2">
                            <FiFileText className="text-3xl opacity-50" />
                            <p className="text-sm font-medium">
                              No dishes found
                            </p>
                            <p className="text-xs">
                              Try adjusting filters or add a new dish
                            </p>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      sortedData.map((dish) => (
                        <React.Fragment key={dish.id}>
                          <tr
                            key={dish.id}
                            className="border-t border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#020617]"
                          >
                            <td className="px-4 py-3 text-sm font-medium flex items-center gap-2 text-gray-800 dark:text-gray-200">
                              <button
                                onClick={() =>
                                  setExpandedDish(
                                    expandedDish === dish.id ? null : dish.id,
                                  )
                                }
                                className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition"
                              >
                                {expandedDish === dish.id ? (
                                  <RowOpen className="text-gray-600 dark:text-gray-300" />
                                ) : (
                                  <RowClosed className="text-gray-600 dark:text-gray-300" />
                                )}
                              </button>
                              {capitalizeWords(dish.name)}
                            </td>

                            {/* Category */}

                            <td className="px-4 py-3 text-sm">
                              <span
                                className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold 
    bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200
    whitespace-normal break-words text-center"
                              >
                                {capitalizeWords(dish.category_name)}
                              </span>
                            </td>

                            {/* Price */}

                            <td className="px-4 py-3 text-sm font-medium text-gray-800 dark:text-gray-200">
                              ₹{dish.selling_price || 0}
                            </td>

                            {/* Ingredients */}

                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-2">
                                {dish.ingredients?.map((ing, i) => {
                                  const isPrepared =
                                    ing.item.startsWith("prep-"); // detect type

                                  return (
                                    <span
                                      key={i}
                                      className={`px-3 py-1 text-xs rounded-full
      ${
        isPrepared
          ? "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300"
          : "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
      }`}
                                    >
                                      {capitalizeWords(ing.name)}
                                    </span>
                                  );
                                })}
                              </div>
                            </td>

                            {/* Cost */}

                            <td className="px-4 py-3 text-sm font-semibold text-gray-800 dark:text-gray-200">
                              ₹{dish.cost_per_dish || 0}
                            </td>

                            {/* Edit */}

                            <td className="px-4 py-3 text-center">
                              <button
                                onClick={() => {
                                  setEditDish(dish);
                                  setShowDishModal(true);
                                }}
                                className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200"
                              >
                                <FiEdit />
                              </button>
                            </td>

                            {/* Delete */}

                            <td className="px-4 py-3 text-center">
                              <button
                                onClick={() => setDeleteId(dish.id)}
                                className="p-2 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                              >
                                <FiTrash2 className="text-red-600" />
                              </button>
                            </td>
                          </tr>

                          {/* EXPANDABLE ROW */}

                          {expandedDish === dish.id && (
                            <tr className="bg-gray-50 dark:bg-[#020617]">
                              <td colSpan={7} className="px-6 py-4">
                                <p className="text-green-600 dark:text-green-400 text-sm font-semibold mb-3">
                                  Ingredient Breakdown
                                </p>

                                <div className="flex flex-wrap gap-3">
                                  {dish.ingredients?.map((ing, index) => {
                                    const isPrepared =
                                      ing.item.startsWith("prep-");

                                    return (
                                      <div
                                        key={index}
                                        className={`border rounded-lg px-4 py-3
      ${
        isPrepared
          ? "border-orange-200 dark:border-orange-300 bg-orange-50 dark:bg-orange-900/30"
          : "border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0b1220]"
      }`}
                                      >
                                        <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                                          {ing.name}
                                        </p>

                                        <p className="text-xs text-gray-500 dark:text-gray-400">
                                          {ing.qty} {ing.unit} per dish
                                        </p>

                                        <p className="text-xs text-orange-500 font-semibold">
                                          ₹{ing.cost}
                                        </p>
                                      </div>
                                    );
                                  })}
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

                  {/* Dynamic Page Numbers */}
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
        </div>
      )}

      {activeTab === "ingredient" && <IngredientManagementTab />}

      {activeTab === "dish-category" && <DishCategoryTab />}

      {activeTab === "prepared" && <PreparedItemTab />}
      {activeTab === "combo" && <ComboTab />}

      <AddDishModal
        isOpen={showDishModal}
        onClose={() => {
          setShowDishModal(false);
          setEditDish(null);
        }}
        editData={editDish}
        onSuccess={fetchDishes}
      />

      {viewDish && (
        <ViewDishModal
          isOpen={!!viewDish}
          data={viewDish}
          onClose={() => setViewDish(null)}
        />
      )}

      <AddExcelModal
        isOpen={showExcelModal}
        onClose={() => setShowExcelModal(false)}
        onSuccess={fetchDishes}
        uploadUrl="/dish/add-ingredients-to-dish-via-excel"
      />
      {deleteId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          <div className="relative bg-white dark:bg-[#0f172a] rounded-2xl shadow-xl p-6 w-[90%] max-w-sm border border-gray-200 dark:border-gray-800">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
              Delete Dish
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to delete this dish? This action cannot be
              undone.
            </p>

            <div className="flex justify-end gap-3">
              {/* Cancel */}
              <button
                onClick={() => setDeleteId(null)}
                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700
          text-gray-800 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                Cancel
              </button>

              {/* Confirm */}
              <button
                onClick={handleDelete}
                className="px-4 py-2 rounded-lg bg-red-500 hover:bg-red-600 text-white"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
