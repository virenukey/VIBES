import { useState, useEffect } from "react";
import {
  FiPlus,
  FiSearch,
  FiEye,
  FiEdit,
  FiTrash2,
  FiChevronLeft,
  FiChevronRight,
} from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";

import AddPreparedStuffModal from "./AddPreparedStuffModal";
import ViewPreparedStuffModal from "./ViewPreparedStuffModal";
import ProduceSemiFinishedModal from "./ProduceSemiFinishedModal";
import SemiFinishedStockTable from "./SemiFinishedStockTable";



export default function PreparedStuffTab() {
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [preparedList, setPreparedList] = useState([]);
  const [searchText, setSearchText] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState(null);
  const [showViewModal, setShowViewModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showProduceModal, setShowProduceModal] = useState(false);

  const fetchPreparedStuff = async () => {
    try {
      setLoading(true);

      const res = await api.get("/dish/get-all-semi-finished");

      // Adjust if backend wraps response in { data: [] }
      const data = res.data?.data || res.data || [];

      setPreparedList(data);
      
    } catch (err) {
      console.error("Failed to fetch prepared stuff", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPreparedStuff();
  }, []);

  useEffect(() => {
    console.log("FULL API RESPONSE:", preparedList);
  }, [preparedList]);

  // 🔍 Search
  const filteredData = preparedList.filter((item) =>
    item.name?.toLowerCase().includes(searchText.toLowerCase())
  );

  const totalPages = Math.ceil(filteredData.length / rowsPerPage) || 1;  const startIndex = (currentPage - 1) * rowsPerPage;
  const paginatedData = filteredData.slice(
    startIndex,
    startIndex + rowsPerPage
  );

  // ❌ DELETE
  const handleDelete = async (id) => {
    if (!window.confirm("Delete this prepared stuff?")) return;

    try {
      const res = await api.delete(`/dish/delete-semi-finished/${id}`);

      toast.success("Prepared stuff deleted successfully");

      fetchPreparedStuff();

    } catch (err) {
      console.error("Delete failed", err);

      const message =
        err.response?.data?.detail ||
        "Failed to delete prepared stuff";

      toast.error(" Failed to delete, Items using this prepared stuff need to be deleted first");
    }
  };


  return (
    <div className="w-full text-gray-800 dark:text-gray-200">
      {/* 🔹 Toolbar */}
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3 px-4 sm:px-6 py-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-200">
          Prepared Stuff List
        </h2>

        <div className="flex items-center gap-3">
          {/* Search */}
          <div className="relative">
            <FiSearch className="absolute left-3 top-3 text-gray-400" />
            <input
              type="text"
              placeholder="Search prepared stuff..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              className="w-64 pl-10 pr-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0f172a] text-sm"
            />
          </div>

          {/* Add */}
          <button
            onClick={() => {
              setSelectedItem(null);
              setShowModal(true);
            }}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium bg-white dark:bg-[#0f172a]"
          >
            <FiPlus />
            Add Prepared Stuff
          </button>
        </div>
      </div>

      {/* 🔹 Table */}
      <div className="w-full overflow-x-auto">
        <table className="w-full border-t border-gray-200 dark:border-gray-800">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold">
                Item Name
              </th>
              <th className="px-4 py-3 text-center text-sm font-semibold w-20">
                View
              </th>
              <th className="px-4 py-3 text-center text-sm font-semibold w-20">
                Edit
              </th>
              <th className="px-4 py-3 text-center text-sm font-semibold w-20">
                Delete
              </th>
              
            </tr>
          </thead>

          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="text-center py-6">
                  Loading...
                </td>
              </tr>
            ) : paginatedData.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-center py-6">
                  No prepared stuff found
                </td>
              </tr>
            ) : (
              paginatedData.map((item) => (
                <tr
                  key={item.product_id}
                  onClick={() => setSelectedItem(item)}
                  className={`border-t border-gray-200 dark:border-gray-800 cursor-pointer
    ${selectedItem?.product_id === item.product_id
                      ? "bg-green-50 dark:bg-green-900/20"
                      : ""
                    }
  `}
                >
                  <td className="px-4 py-2 text-sm">
                    {item.name}
                  </td>

                  {/* View */}
                  <td className="px-4 py-2 text-center">
                    <button
                      onClick={async () => {
                        try {
                          const res = await api.get(
                            `/dish/get-semi-finished/${item.product_id}`
                          );

                          setSelectedItem(res.data);
                          setShowModal(true);

                        } catch (err) {
                          console.error("Failed to fetch product details", err);
                          toast.error("Failed to load product details");
                        }
                      }}
                      className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                    >
                      <FiEye />
                    </button>
                  </td>

                  {/* Edit */}
                  <td className="px-4 py-2 text-center">
                    <button
                      onClick={() => {
                        setSelectedItem(item);
                        setShowModal(true);
                      }}
                      className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                    >
                      <FiEdit />
                    </button>
                  </td>

                  {/* Delete */}
                  <td className="px-4 py-2 text-center">
                    <button
                      onClick={() => handleDelete(item.product_id)}
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
      </div>

      

      {/* 🔹 Pagination */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 px-4 sm:px-6 py-4">

        {/* Rows per page */}
        <div className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
          <span className="font-medium">Rows per page</span>

          <select
            value={rowsPerPage}
            onChange={(e) => {
              setRowsPerPage(Number(e.target.value));
              setCurrentPage(1);
            }}
            className="px-3 py-1 rounded-md 
                 border border-gray-200 dark:border-gray-700
                 bg-white dark:bg-gray-900 
                 text-gray-800 dark:text-gray-200"
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
        </div>

        {/* Page Info */}
        <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
          Page {currentPage} of {totalPages}
        </div>

        {/* Arrows */}
        <div className="flex items-center gap-2">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            className="p-2 rounded-md 
                 border border-gray-200 dark:border-gray-700 
                 text-gray-700 dark:text-gray-200
                 hover:bg-gray-100 dark:hover:bg-gray-800
                 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FiChevronLeft />
          </button>

          <button
            disabled={currentPage === totalPages}
            onClick={() =>
              setCurrentPage((p) => Math.min(totalPages, p + 1))
            }
            className="p-2 rounded-md 
                 border border-gray-200 dark:border-gray-700 
                 text-gray-700 dark:text-gray-200
                 hover:bg-gray-100 dark:hover:bg-gray-800
                 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FiChevronRight />
          </button>
        </div>
      </div>

      {/* 🔹 Modals */}
      <AddPreparedStuffModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false);
          setSelectedItem(null);
        }}
        editData={selectedItem}
        onSave={() => {
          fetchPreparedStuff();
        }}
      />

      <ViewPreparedStuffModal
        isOpen={showViewModal}
        onClose={() => {
          setShowViewModal(false);
          setSelectedItem(null);
        }}
        data={selectedItem}
      />

      <ProduceSemiFinishedModal
        isOpen={showProduceModal}
        onClose={() => setShowProduceModal(false)}
        product={selectedItem}
        onSuccess={() => {
       
        }}
      />
      {/* Create Button Below Table */}
      <div className="flex justify-end px-6 py-4">
        <button
          disabled={!selectedItem}
          onClick={() => setShowProduceModal(true)}
          className={`px-6 py-2 rounded-md text-white font-medium transition
      ${selectedItem
              ? "bg-green-500 hover:bg-green-600"
              : "bg-gray-300 cursor-not-allowed"
            }
    `}
        >
          Create +
        </button>
      </div>
      <SemiFinishedStockTable />



    </div>

    
  );
}
