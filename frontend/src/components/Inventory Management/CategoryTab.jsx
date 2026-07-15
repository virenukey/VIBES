import { useState } from "react";
import {
  FiPlus,
  FiSearch,
  FiEdit,
  FiTrash2,
  FiChevronLeft,
  FiChevronRight,
} from "react-icons/fi";
import { toast } from "react-toastify";


import AddCategoryModal from "./AddCategoryModal";
import AddExcelModal from "./AddExcelModal";
import { capitalizeWords } from "../../utils/text";
import api from "../../api/axios";
import { useEffect } from "react";


export default function CategoryTab() {
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);

  const [searchText, setSearchText] = useState("");
  const [showCategoryModal, setShowCategoryModal] = useState(false);
  const [showExcelModal, setShowExcelModal] = useState(false);

  const [editCategoryData, setEditCategoryData] = useState(null);

  const [showDeleteModal, setShowDeleteModal] = useState(false);
const [deleteCategoryId, setDeleteCategoryId] = useState(null);

  useEffect(() => {
    fetchCategories();
  }, []);

  const fetchCategories = async () => {
    try {
      setLoading(true);
      const res = await api.get("/inventory/get-item-categories");
      setCategories(res.data.data || []);
      console.log(res.data)
    } catch (err) {
      console.error("Failed to fetch categories", err);
    } finally {
      setLoading(false);
    }
  };

  const filteredCategories = categories.filter(
    (cat) =>
      cat.name.toLowerCase().includes(searchText.toLowerCase()) ||
      cat.category_type.toLowerCase().includes(searchText.toLowerCase())
  );

  const totalPages = Math.ceil(filteredCategories.length / rowsPerPage);

  const startIndex = (currentPage - 1) * rowsPerPage;
  const endIndex = startIndex + rowsPerPage;

  const paginatedData = filteredCategories.slice(startIndex, endIndex);


  const handleSaveCategory = async (data) => {
    const tenant_id = localStorage.getItem("tenant_id");
    const user_id = Number(localStorage.getItem("user_id"));

    try {
      if (editCategoryData) {
       
        await api.put(
          `/inventory/update-item-category/${editCategoryData.id}`,
          {
            name: data.name,
            category_type: data.type.toLowerCase(),
          }
        );

        toast.success("Category updated successfully ");

      } else {
       
        await api.post("/inventory/add-item-category", {
          name: data.name,
          category_type: data.type.toLowerCase(),
          tenant_id,
          user_id,
        });

        toast.success("Category added successfully ");
      }

      fetchCategories();

      setTimeout(() => {
        setShowCategoryModal(false);
        setEditCategoryData(null);
      }, 200);

    } catch (err) {
      console.error("Save category failed", err);
      toast.error("Failed to save category ❌");
    }
  };

  // ✅ Delete Category
  const handleDeleteCategory = async () => {
    try {
      await api.delete(`/inventory/delete-item-categories/${deleteCategoryId}`);

      toast.success("Category deleted successfully 🗑️");

      fetchCategories();

      setShowDeleteModal(false);
      setDeleteCategoryId(null);

    } catch (err) {
      console.error("Delete failed", err);
      toast.error("Failed to delete category ❌");
    }
  };


  return (
    <div className="w-full">
      {/* Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 px-4 sm:px-6 py-4">

        {/* Left Side */}
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Categories
          </h2>
        </div>

        {/* Right Side */}
        <div className="flex items-center gap-3 flex-wrap">

          {/* Search */}
          <div className="relative group">
            <FiSearch className="absolute left-3 top-3 text-gray-400 group-hover:text-orange-500 transition" />

            <input
              type="text"
              placeholder="Search Category ....."
              value={searchText}
              onChange={(e) => {
                setSearchText(e.target.value);
                setCurrentPage(1);
              }}
              className="w-64 pl-10 pr-4 py-2 rounded-xl 
    border border-gray-200 dark:border-gray-700
    bg-white dark:bg-[#0f172a] 
    text-sm text-gray-800 dark:text-gray-200
    shadow-sm hover:shadow-md
    focus:shadow-md
    outline-none focus:ring-2 focus:ring-orange-400
    transition-all duration-200"
            />
          </div>

          {/* Add Category */}
          <button
            onClick={() => {
              setEditCategoryData(null);
              setShowCategoryModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition"
          >
            <FiPlus />
            Add category
          </button>

          {/* Add via Excel */}
          <button
            onClick={() => setShowExcelModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 
      bg-white dark:bg-[#0f172a] text-sm font-medium text-gray-800 dark:text-gray-200 
      hover:bg-gray-50 dark:hover:bg-gray-800 transition"
          >
            <img
              src="https://cdn-icons-png.flaticon.com/512/732/732220.png"
              alt="excel"
              className="w-4 h-4"
            />
            Add via excel
          </button>

        </div>
      </div>
      {/* Table */}
      <div className="px-4 sm:px-6">
        <div className="w-full overflow-x-auto border border-gray-200 dark:border-gray-800 rounded-xl bg-white dark:bg-[#0f172a] shadow-sm">

          <table className="w-full">

            {/* Header */}
            <thead className="bg-gray-50 dark:bg-[#020617] border-b border-gray-200 dark:border-gray-800">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-200">
                  Category Name
                </th>

                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-200">
                  Type
                </th>
                <th className="px-6 py-3 text-center text-sm font-semibold text-gray-700 dark:text-gray-200 w-24">
                  <FiEdit className="mx-auto text-gray-600 dark:text-white" />
                </th>

                <th className="px-6 py-3 text-center text-sm font-semibold text-gray-700 dark:text-gray-200 w-24">
                  <FiTrash2 className="mx-auto text-black dark:text-red-400" />
                </th>
              </tr>
            </thead>

            {/* Body */}
            <tbody>

              {paginatedData.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="px-6 py-8 text-center text-sm text-gray-500"
                  >
                    No categories found.
                  </td>
                </tr>
              ) : (

                paginatedData.map((cat) => (

                  <tr
                    key={cat.id}
                    className="border-t border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                  >

                    {/* Category Name */}
                    <td className="px-6 py-4 text-sm text-gray-800 dark:text-gray-200 font-medium">
                      {capitalizeWords(cat.name)}
                    </td>

                    {/* Type */}
                    <td className="px-6 py-4 text-sm">

                      <span
                        className="px-3 py-1 rounded-full text-xs font-medium 
  bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
                      >
                        {cat.category_type.replace("_", " ")}
                      </span>

                    </td>

                    {/* Edit */}
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={() => {
                          setEditCategoryData(cat);
                          setShowCategoryModal(true);
                        }}
                        className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition"
                      >
                        <FiEdit className="text-gray-700 dark:text-gray-200" />
                      </button>
                    </td>

                    {/* Delete */}
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={() => {
                          setDeleteCategoryId(cat.id);
                          setShowDeleteModal(true);
                        }}
                        className="p-2 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition"
                      >
                        <FiTrash2 className="text-black dark:text-red-400" />
                      </button>
                    </td>

                  </tr>

                ))

              )}

            </tbody>

          </table>
          {/* Pagination */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 px-4 sm:px-6 py-4 border-t border-gray-200 dark:border-gray-800">

            {/* Rows per page */}
            <div className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
              <span className="font-medium">Rows per page</span>

              <select
                value={rowsPerPage}
                onChange={(e) => {
                  setRowsPerPage(Number(e.target.value));
                  setCurrentPage(1);
                }}
                className="px-3 py-1 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
              >
                <option value={5}>5</option>
                <option value={10}>10</option>
                <option value={25}>25</option>
              </select>
            </div>

            {/* Page indicator */}
            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
              Page {currentPage} of {totalPages || 1}
            </div>

            {/* Navigation */}
            <div className="flex items-center gap-2">

              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <FiChevronLeft />
              </button>

              <button
                disabled={currentPage === totalPages || totalPages === 0}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <FiChevronRight />
              </button>

            </div>

          </div>

        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">

          {/* Overlay */}
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>

          {/* Modal */}
          <div className="relative w-full max-w-md bg-white dark:bg-[#0f172a] rounded-xl shadow-xl border border-gray-200 dark:border-gray-800 p-6">

            {/* Title */}
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Delete Category
            </h3>

            {/* Message */}
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to delete this category? This action cannot be undone.
            </p>

            {/* Buttons */}
            <div className="flex justify-end gap-3">

              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteCategoryId(null);
                }}
                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
              >
                Cancel
              </button>

              <button
                onClick={handleDeleteCategory}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white transition"
              >
                Delete
              </button>

            </div>

          </div>

        </div>
      )}

      {/* ✅ Add/Edit Modal */}
      <AddCategoryModal
        isOpen={showCategoryModal}
        onClose={() => {
          setShowCategoryModal(false);
          setEditCategoryData(null);
        }}
        onSave={handleSaveCategory}
        editData={editCategoryData}
      />
      <AddExcelModal
        isOpen={showExcelModal}
        onClose={() => setShowExcelModal(false)}
        onSuccess={fetchCategories}
        uploadUrl="/inventory/add-item-categories-via-excel"
      />
    </div>
  );
}
