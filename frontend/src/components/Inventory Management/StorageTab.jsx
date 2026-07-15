import { useEffect, useState } from "react";
import {
  FiPlus,
  FiSearch,
  FiEdit,
  FiTrash2,
  FiChevronLeft,
  FiChevronRight,
} from "react-icons/fi";
import AddStorageModal from "./AddStorageModal";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function StorageTab() {

  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);

  const [searchText, setSearchText] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editStorageData, setEditStorageData] = useState(null);

  const [storages, setStorages] = useState([]);
  const [loading, setLoading] = useState(false);

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteStorageId, setDeleteStorageId] = useState(null);

  const [selectedInstruction, setSelectedInstruction] = useState(null);

  useEffect(() => {
    fetchStorages();
  }, []);

  const fetchStorages = async () => {
    try {
      setLoading(true);
      const res = await api.get("/inventory/get-all-storage/all");
      setStorages(res.data.data || []);
    } catch (err) {
      console.error("Failed to fetch storage", err);
    } finally {
      setLoading(false);
    }
  };

  const filteredStorages = storages.filter(
    (s) =>
      s.name.toLowerCase().includes(searchText.toLowerCase()) ||
      s.special_handling_instructions
        ?.toLowerCase()
        .includes(searchText.toLowerCase())
  );

  const totalPages = Math.ceil(filteredStorages.length / rowsPerPage);

  const startIndex = (currentPage - 1) * rowsPerPage;

  const paginatedData = filteredStorages.slice(
    startIndex,
    startIndex + rowsPerPage
  );

  // Save storage
  const handleSaveStorage = async (data) => {

    const tenant_id = localStorage.getItem("tenant_id");

    try {

      if (editStorageData) {

        await api.put(`/inventory/update-storage/${editStorageData.id}`, {
          name: data.name,
          storage_temp_min: Number(data.minTemp),
          storage_temp_max: Number(data.maxTemp),
          tenant_id,
          special_handling_instructions: data.instruction,
          is_active: data.is_active,
        });

        toast.success("Storage updated successfully");

      } else {

        await api.post("/inventory/add-storage", {
          name: data.name,
          storage_temp_min: Number(data.minTemp),
          storage_temp_max: Number(data.maxTemp),
          tenant_id,
          special_handling_instructions: data.instruction,
        });

        toast.success("Storage added successfully");

      }

      fetchStorages();

      setTimeout(() => {
        setShowModal(false);
        setEditStorageData(null);
      }, 200);

    } catch (err) {
      console.error("Save storage failed", err);
      toast.error("Something went wrong ❌");
    }
  };

  // Delete storage
  const handleDelete = async () => {

    try {

      await api.delete(`/inventory/delete-storage-id/${deleteStorageId}`);

      toast.success("Storage deleted successfully 🗑️");

      fetchStorages();

      setShowDeleteModal(false);
      setDeleteStorageId(null);

    } catch (err) {
      console.error("Delete storage failed", err);
      toast.error("Failed to delete storage ❌");
    }
  };

  return (
    <div className="w-full text-gray-800 dark:text-gray-200">

      {/* Toolbar */}
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3 px-4 sm:px-6 py-4">

        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Storage
        </h2>

        <div className="flex flex-wrap items-center gap-3">

          {/* Search */}
          <div className="relative group">

            <FiSearch className="absolute left-3 top-3 text-gray-400 group-hover:text-orange-500 transition" />

            <input
              type="text"
              placeholder="Search storage..."
              value={searchText}
              onChange={(e) => {
                setSearchText(e.target.value);
                setCurrentPage(1);
              }}
              className="w-64 sm:w-72 pl-10 pr-4 py-2 rounded-xl
    border border-gray-200 dark:border-gray-700
    bg-white dark:bg-[#0f172a]
    text-sm text-gray-800 dark:text-gray-200
    shadow-sm hover:shadow-md focus:shadow-md
    outline-none focus:ring-2 focus:ring-orange-400
    transition-all duration-200"
            />

          </div>

          {/* Add storage */}
          <button
            onClick={() => {
              setEditStorageData(null);
              setShowModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium transition"
          >
            <FiPlus />
            Add Storage
          </button>

        </div>
      </div>


      {/* Table Card */}
      <div className="px-4 sm:px-6">
        <div className="bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm overflow-hidden">

          <div className="overflow-x-auto">

            <table className="w-full text-sm">

              <thead className="bg-gray-50 dark:bg-[#020617] border-b border-gray-200 dark:border-gray-800">

                <tr>

                  <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Storage Name
                  </th>

                  <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Min Temp (°C)
                  </th>

                  <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Max Temp (°C)
                  </th>

                  <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                    Instructions
                  </th>

                  <th className="px-6 py-3 text-center">
                    Edit
                  </th>

                  <th className="px-6 py-3 text-center">
                    Delete
                  </th>

                </tr>

              </thead>


              <tbody>

                {paginatedData.length === 0 ? (

                  <tr>
                    <td
                      colSpan={6}
                      className="px-6 py-8 text-center text-gray-500 dark:text-gray-400"
                    >
                      No storage found.
                    </td>
                  </tr>

                ) : (

                  paginatedData.map((s) => (

                    <tr
                      key={s.id}
                      className="border-b border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#020617] transition"
                    >

                      <td className="px-6 py-4 font-medium">
                        {s.name}
                      </td>

                      <td className="px-6 py-4">
                        {s.storage_temp_min}
                      </td>

                      <td className="px-6 py-4">
                        {s.storage_temp_max}
                      </td>

                      <td className="px-6 py-4">

                        {s.special_handling_instructions ? (

                          <div className="max-w-[220px]">

                            {/* Badge */}
                            <span
                              className="px-3 py-1 text-xs rounded-full bg-red-100 text-red-600 
        dark:bg-red-900/30 dark:text-red-400 
        inline-block truncate w-full"
                              title={s.special_handling_instructions}
                            >
                              {s.special_handling_instructions}
                            </span>

                            {/* Read more aligned right */}
                            {s.special_handling_instructions.length > 60 && (
                              <div className="flex justify-end mt-1">
                                <button
                                  onClick={() => setSelectedInstruction(s.special_handling_instructions)}
                                  className="text-orange-500 text-xs"
                                >
                                  Read more
                                </button>
                              </div>
                            )}

                          </div>

                        ) : (
                          <span className="text-gray-400">—</span>
                        )}

                      </td>


                      {/* Edit */}
                      <td className="px-6 py-4 text-center">

                        <button
                          onClick={() => {
                            setEditStorageData({
                              id: s.id,
                              name: s.name,
                              minTemp: s.storage_temp_min,
                              maxTemp: s.storage_temp_max,
                              instruction: s.special_handling_instructions,
                              is_active: s.is_active,
                            });

                            setShowModal(true);
                          }}
                          className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition"
                        >
                          <FiEdit />
                        </button>

                      </td>


                      {/* Delete */}
                      <td className="px-6 py-4 text-center">

                        <button
                          onClick={() => {
                            setDeleteStorageId(s.id);
                            setShowDeleteModal(true);
                          }}
                          className="p-2 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition"
                        >
                          <FiTrash2 className="text-red-600 dark:text-red-400" />
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
                  className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                >
                  <FiChevronLeft />
                </button>

                <button
                  disabled={currentPage === totalPages || totalPages === 0}
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                >
                  <FiChevronRight />
                </button>

              </div>

            </div>
          </div>

        </div>
      </div>

      {/* Delete Modal */}
      {showDeleteModal && (

        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">

          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>

          <div className="relative w-full max-w-sm bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-xl p-6">

            <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-white">
              Delete Storage
            </h3>

            <p className="text-sm text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to delete this storage?
            </p>

            <div className="flex justify-end gap-3">

              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteStorageId(null);
                }}
                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 text-sm hover:bg-gray-100 dark:hover:bg-gray-800"
              >
                Cancel
              </button>

              <button
                onClick={handleDelete}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm"
              >
                Delete
              </button>

            </div>

          </div>

        </div>

      )}
      {selectedInstruction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">

          {/* Overlay */}
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => setSelectedInstruction(null)}
          />

          {/* Modal */}
          <div className="relative bg-white dark:bg-[#0f172a] p-6 rounded-xl max-w-lg w-full shadow-xl">

            <h3 className="text-lg font-semibold mb-3 text-gray-900 dark:text-white">
              Full Instruction
            </h3>

            <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
              {selectedInstruction}
            </p>

            <div className="mt-4 text-right">
              <button
                onClick={() => setSelectedInstruction(null)}
                className="px-4 py-2 bg-orange-500 text-white rounded-lg"
              >
                Close
              </button>
            </div>

          </div>
        </div>
      )}


      {/* Add/Edit Modal */}
      <AddStorageModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false);
          setEditStorageData(null);
        }}
        onSave={handleSaveStorage}
        editData={editStorageData}
      />

    </div>
    
  );
}