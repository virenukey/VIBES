import { useState, useEffect } from "react";
import { useNavigate, useSearchParams, useLocation } from "react-router-dom";
import {
  FiChevronLeft,
  FiChevronRight,
  FiEdit,
  FiTrash2,
  FiArrowLeft,
} from "react-icons/fi";
import PageHeader from "../components/PageHeader";
import api from "../api/axios";

export default function ItemDetails() {
  const [searchParams] = useSearchParams();
  const itemId = searchParams.get("itemId");
  const location = useLocation();

  const category = location.state?.category || "N/A";
  const storage = location.state?.storage || "N/A";

  const navigate = useNavigate();

  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [data, setData] = useState([]);
  const [itemName, setItemName] = useState("");

  useEffect(() => {
    if (!itemId) return;

    const fetchBatches = async () => {
      try {
        const res = await api.get(`/inventory/items/${itemId}/batches`);
        if (res.data?.success) {
          setItemName(res.data.item_name);
          setData(res.data.data || []);
        }
      } catch (err) {
        console.error("Failed to fetch batch details", err);
      }
    };

    fetchBatches();
  }, [itemId]);

  const totalPages = Math.ceil(data.length / rowsPerPage);
  const startIndex = (currentPage - 1) * rowsPerPage;
  const paginatedData = data.slice(startIndex, startIndex + rowsPerPage);

  const formatTime = (date) =>
    new Date(date).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });

  const formatDay = (date) =>
    new Date(date).toLocaleDateString("en-US", { weekday: "short" });

  return (
    <div className="w-full max-w-full overflow-x-hidden">
      <div className="bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm overflow-hidden">
        <PageHeader
          title={
            <>
              Inventory -{" "}
              <span className="text-orange-500 dark:text-orange-400 font-bold">
                {itemName}
              </span>
            </>
          }
        />

        {/* Back button */}
        <div className="flex items-center justify-between px-4 sm:px-6 py-4">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg border
                       border-gray-200 dark:border-gray-700
                       bg-white dark:bg-[#0f172a]
                       text-sm font-medium
                       text-gray-800 dark:text-gray-200
                       hover:bg-gray-50 dark:hover:bg-gray-800 transition"
          >
            <FiArrowLeft className="text-lg" />
            Back
          </button>
          <div />
        </div>

        {/* Table */}
        <div className="w-full overflow-x-auto">
          <table className="w-full table-fixed border-t border-gray-200 dark:border-gray-800">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[15%] text-gray-800 dark:text-gray-200">
                  Batch
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[10%] text-gray-800 dark:text-gray-200">
                  Category
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[9%] text-gray-800 dark:text-gray-200">
                  Total
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[7%] text-gray-800 dark:text-gray-200">
                  Qty
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[9%] text-gray-800 dark:text-gray-200">
                  Price/unit
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[10%] text-gray-800 dark:text-gray-200">
                  Storage
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[7%] text-gray-800 dark:text-gray-200">
                  Unit
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[7%] text-gray-800 dark:text-gray-200">
                  Time
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[6%] text-gray-800 dark:text-gray-200">
                  Day
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-left w-[10%] text-gray-800 dark:text-gray-200">
                  Status
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-center w-[5%] text-gray-800 dark:text-gray-200">
                  Edit
                </th>
                <th className="px-2 py-3 text-sm font-semibold text-center w-[5%] text-gray-800 dark:text-gray-200">
                  Del
                </th>
              </tr>
            </thead>

            <tbody>
              {paginatedData.map((item) => (
                <tr
                  key={item.id}
                  className="border-t border-gray-200 dark:border-gray-800"
                >
                  <td className="px-2 py-2 text-sm truncate text-gray-800 dark:text-gray-200">
                    {item.batch_number}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-600 dark:text-gray-400">
                    {category}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-800 dark:text-gray-200">
                    ₹{(item.quantity_received * item.unit_cost).toFixed(2)}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-800 dark:text-gray-200">
                    {item.quantity_remaining}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-800 dark:text-gray-200">
                    ₹{item.unit_cost}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-600 dark:text-gray-400">
                    {storage}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-800 dark:text-gray-200">
                    {item.unit}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-800 dark:text-gray-200">
                    {formatTime(item.created_at)}
                  </td>

                  <td className="px-2 py-2 text-sm truncate text-gray-800 dark:text-gray-200">
                    {formatDay(item.created_at)}
                  </td>

                  <td className="px-2 py-2 text-sm">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${
                        item.lifecycle_stage !== "fresh"
                          ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
                          : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300"
                      }`}
                    >
                      {item.lifecycle_stage}
                    </span>
                  </td>

                  <td className="px-2 py-2 text-center">
                    <button className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800">
                      <FiEdit className="text-gray-700 dark:text-gray-200" />
                    </button>
                  </td>

                  <td className="px-2 py-2 text-center">
                    <button className="p-2 rounded hover:bg-red-50 dark:hover:bg-red-900/20">
                      <FiTrash2 className="text-red-600" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 px-4 sm:px-6 py-4">
          <div className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
            <span className="font-medium">Rows per page</span>

            <select
              value={rowsPerPage}
              onChange={(e) => {
                setRowsPerPage(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="px-3 py-1 rounded-md border
                         border-gray-200 dark:border-gray-700
                         bg-white dark:bg-gray-900
                         text-gray-800 dark:text-gray-200 outline-none"
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </div>

          <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
            Page {currentPage} of {totalPages}
          </div>

          <div className="flex items-center gap-2">
            <button
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              className="p-2 rounded-md border
                         border-gray-200 dark:border-gray-700
                         text-gray-800 dark:text-gray-200
                         hover:bg-gray-100 dark:hover:bg-gray-800
                         transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <FiChevronLeft />
            </button>

            <button
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              className="p-2 rounded-md border
                         border-gray-200 dark:border-gray-700
                         text-gray-800 dark:text-gray-200
                         hover:bg-gray-100 dark:hover:bg-gray-800
                         transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <FiChevronRight />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
