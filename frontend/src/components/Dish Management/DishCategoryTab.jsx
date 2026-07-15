import { useState, useEffect } from "react";
import {
  FiPlus,
  FiSearch,
  FiEdit,
  FiTrash2,
  FiChevronLeft,
  FiChevronRight,
  FiFileText,
} from "react-icons/fi";
import { AiOutlineFileExcel } from "react-icons/ai";
import api from "../../api/axios";
import AddDishCategoryModal from "./AddDishCategoryModal";
import AddExcelModal from "../Inventory Management/AddExcelModal";
import { toast } from "react-toastify";
import { capitalizeWords } from "../../utils/text";

export default function DishCategoryTab() {
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);
  const [categories, setCategories] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editCategory, setEditCategory] = useState(null);
  const [deleteId, setDeleteId] = useState(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showExcelModal, setShowExcelModal] = useState(false);

  useEffect(() => {
    fetchCategories();
  }, []);

  const fetchCategories = async () => {
    try {
      const res = await api.get("/dish/get_dish_types");
      setCategories(res.data.data || []);
    } catch (err) {
      console.error("Failed to fetch dish categories", err);
    }
  };

  const filteredData = categories.filter((c) =>
    c.name.toLowerCase().includes(searchText.toLowerCase())
  );

  const totalPages = Math.ceil(filteredData.length / rowsPerPage) || 1;

  const startIndex = (currentPage - 1) * rowsPerPage;

  const paginatedData = filteredData.slice(
    startIndex,
    startIndex + rowsPerPage
  );

  const handleSave = async (data) => {
    try {
      if (editCategory) {
        const cleanName = data.name
          .trim()
          .replace(/\s+/g, " ");

        await api.put(`/dish/update_dish_types/${editCategory.id}`, {
          name: cleanName,
        });
        
      } else {
        const cleanName = data.name
          .trim()
          .replace(/\s+/g, " ");

        await api.post("/dish/add_dish_type", {
          name: cleanName,
        });
      }

      setShowModal(false);
      setEditCategory(null);
      fetchCategories();
    } catch (err) {
      console.error("Save failed", err);
      console.log("Backend response:", err?.response?.data);

      let errorMessage = "Failed to save category";

      if (err?.response?.data) {
        const data = err.response.data;

        if (Array.isArray(data.detail)) {
          errorMessage = data.detail.map(e => e.msg).join(", ");
        } else if (typeof data.detail === "string") {
          errorMessage = data.detail;
        } else if (data.message) {
          errorMessage = data.message;
        } else {
          errorMessage = JSON.stringify(data);
        }
      }

      throw new Error(errorMessage);
    }
  };

  const handleDelete = async () => {
    try {
      await api.delete(`/dish/delete_dish_type/${deleteId}`);

      toast.success("Category deleted successfully 🗑️");

      setShowDeleteModal(false);
      setDeleteId(null);

      fetchCategories();

    } catch (err) {
      console.error("Delete failed", err);
      console.log("Backend response:", err?.response?.data);

      let errorMessage = "Failed to delete category";

      if (err?.response?.data) {
        const data = err.response.data;

        if (Array.isArray(data.detail)) {
          errorMessage = data.detail.map(e => e.msg).join(", ");
        } else if (typeof data.detail === "string") {
          errorMessage = data.detail;
        } else if (data.message) {
          errorMessage = data.message;
        } else {
          errorMessage = JSON.stringify(data);
        }
      }

      toast.error(errorMessage);
    }
  };

  return (
    <div className="w-full">

      {/* Top Controls */}
      <div className="flex flex-col gap-3 px-4 sm:px-6 py-4">

        {/* ROW 1 → Search (left) + Download (right) */}
        <div className="flex justify-between items-center">

          {/* LEFT → Search */}
          <div className="relative">
            <FiSearch className="absolute left-3 top-3 text-gray-400 dark:text-gray-500" />
            <input
              type="text"
              placeholder="Search Category ....."
              value={searchText}
              onChange={(e) => {
                setSearchText(e.target.value);
                setCurrentPage(1);
              }}
              className="w-64 pl-10 pr-4 py-2 rounded-lg
        border border-gray-200 dark:border-gray-700
        bg-white dark:bg-[#0f172a]
        text-sm text-gray-800 dark:text-gray-200
        outline-none focus:ring-2 focus:ring-orange-400"
            />
          </div>

          {/* RIGHT → Download */}
          <a
            href="/dish_category_sheet.xlsx"
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

        {/* ROW 2 → Buttons (right aligned) */}
        <div className="flex justify-end items-center gap-3">

          {/* Add Category */}
          <button
            onClick={() => {
              setEditCategory(null);
              setShowModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg
      bg-orange-500 text-white text-sm font-medium"
          >
            <FiPlus />
            Add Category
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
      {/* Table Container */}
      <div className="px-4 sm:px-6 pb-4">
        <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">

          <table className="w-full">

            <thead className="bg-gray-100 dark:bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                  Category Name
                </th>

                <th className="px-4 py-3 text-center w-24 text-sm font-semibold text-gray-800 dark:text-gray-200">
                  Edit
                </th>

                <th className="px-4 py-3 text-center w-24 text-sm font-semibold text-gray-800 dark:text-gray-200">
                  Delete
                </th>
              </tr>
            </thead>

            <tbody>

              {paginatedData.length === 0 ? (
                <tr>
                  <td
                    colSpan={3}
                    className="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400"
                  >
                    No categories found
                  </td>
                </tr>
              ) : (
                paginatedData.map((cat) => (
                  <tr
                    key={cat.id}
                    className="border-t border-gray-200 dark:border-gray-800"
                  >
                    <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200">
                      {capitalizeWords(cat.name)}
                    </td>

                    <td className="text-center">
                      <button
                        onClick={() => {
                          setEditCategory(cat);
                          setShowModal(true);
                        }}
                        className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200"
                      >
                        <FiEdit />
                      </button>
                    </td>

                    <td className="text-center">

                      <button
                        onClick={() => {
                          setDeleteId(cat.id);
                          setShowDeleteModal(true);
                        }}
                        className="p-2 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                      >
                        <FiTrash2 className="text-red-600" />
                      </button>
                    </td>
                  </tr>
                ))
              )}

            </tbody>
          </table>

          {/* Pagination */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 px-4 sm:px-6 py-4 border-t border-gray-200 dark:border-gray-800">

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

            <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
              Page {currentPage} of {totalPages}
            </div>

            <div className="flex items-center gap-2">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                className="p-2 rounded-md border border-gray-200 dark:border-gray-700
                 hover:bg-gray-100 dark:hover:bg-gray-800
                 disabled:opacity-40"
              >
                <FiChevronLeft />
              </button>

              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                className="p-2 rounded-md border border-gray-200 dark:border-gray-700
                 hover:bg-gray-100 dark:hover:bg-gray-800
                 disabled:opacity-40"
              >
                <FiChevronRight />
              </button>
            </div>

          </div>
        </div>
      </div>

      {/* Modal */}
      <AddDishCategoryModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false);
          setEditCategory(null);
        }}
        editData={editCategory}
        onSave={handleSave}
      />
      <AddExcelModal
        isOpen={showExcelModal}
        onClose={() => setShowExcelModal(false)}
        onSuccess={fetchCategories}
        uploadUrl="/dish/add_dish_types_via_excel"
      />

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">

          <div className="bg-white dark:bg-[#0f172a] rounded-xl p-6 w-[480px] shadow-xl">

            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-200 mb-3">
              Delete Category
            </h3>

            <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
              Are you sure you want to delete this category?
              This action cannot be undone.
            </p>

            <div className="flex justify-end gap-3">

              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteId(null);
                }}
                className="px-4 py-2 rounded-lg border border-gray-300
                     text-sm text-gray-700 dark:text-gray-200
                     hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                Cancel
              </button>

              <button
                onClick={handleDelete}
                className="px-4 py-2 rounded-lg bg-red-600 text-white text-sm
                     hover:bg-red-700"
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