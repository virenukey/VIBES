import { useEffect, useState } from "react";
import api from "../../api/axios";
import { FiChevronLeft, FiChevronRight, FiEye, FiX } from "react-icons/fi";

export default function TopWastageTab() {
    const [wastageData, setWastageData] = useState([]);
    const [loading, setLoading] = useState(false);

    const [rowsPerPage, setRowsPerPage] = useState(10);
    const [currentPage, setCurrentPage] = useState(1);
    const [selectedImage, setSelectedImage] = useState(null);

    const fetchWastageRecords = async () => {
        try {
            setLoading(true);

            const res = await api.get("/wastage/records");

            setWastageData(res.data.data || []);

        } catch (err) {
            console.error("Failed to fetch wastage records", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchWastageRecords();
    }, []);

    // Pagination
    const totalPages = Math.ceil(wastageData.length / rowsPerPage);
    const startIndex = (currentPage - 1) * rowsPerPage;
    const endIndex = startIndex + rowsPerPage;
    const paginatedData = wastageData.slice(startIndex, endIndex);

    const formatDate = (dateString) => {
        if (!dateString) return "-";
        const date = new Date(dateString);
        return date.toLocaleDateString();
    };

    
    return (
        <div className="px-3 sm:px-4 py-4 text-gray-900 dark:text-gray-100">

            {/* Table Wrapper */}
            <div className="w-full overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">

                <table className="min-w-[900px] w-full border-collapse">
                    <thead className="bg-gray-50 dark:bg-gray-900">
                        <tr>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Item
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Type
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Batch
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Quantity
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Cost
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Reason
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Date
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Recorded By
                            </th>
                            <th className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold text-left whitespace-nowrap">
                                Proof
                            </th>
                        </tr>
                    </thead>

                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="8" className="text-center py-6 text-sm">
                                    Loading...
                                </td>
                            </tr>
                        ) : paginatedData.length === 0 ? (
                            <tr>
                                <td colSpan="8" className="text-center py-6 text-sm">
                                    No wastage records found
                                </td>
                            </tr>
                        ) : (
                            paginatedData.map((item) => (
                                <tr
                                    key={item.id}
                                    className="border-t border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                                >
                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-medium">
                                        {item.wastage_type === "dish"
                                            ? item.dish_name
                                            : item.item_name}
                                    </td>

                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm capitalize">
                                        {item.wastage_type}
                                    </td>

                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm">
                                        {item.batch_number || "-"}
                                    </td>

                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm whitespace-nowrap">
                                        {item.quantity_wasted} {item.unit}
                                    </td>

                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm font-semibold whitespace-nowrap">
                                        ₹{Number(item.cost_value).toFixed(2)}
                                    </td>

                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm capitalize whitespace-nowrap">
                                        {item.wastage_reason.replace("_", " ")}
                                    </td>

                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm whitespace-nowrap">
                                        {formatDate(item.wastage_date)}
                                    </td>

                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm">
                                        {item.recorded_by || "-"}
                                    </td>
                                    <td className="px-3 sm:px-4 py-3 text-xs sm:text-sm text-center">
                                        {item.photo_url ? (
                                            <button
                                                onClick={() => setSelectedImage(item.photo_url)}
                                                className="text-blue-600 hover:text-blue-800 transition"
                                            >
                                                <FiEye />
                                            </button>
                                        ) : (
                                            "-"
                                        )}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mt-4">

                <div className="flex items-center gap-2 text-xs sm:text-sm">
                    <span>Rows per page</span>
                    <select
                        value={rowsPerPage}
                        onChange={(e) => {
                            setRowsPerPage(Number(e.target.value));
                            setCurrentPage(1);
                        }}
                        className="px-2 py-1 border rounded text-xs sm:text-sm"
                    >
                        <option value={10}>10</option>
                        <option value={25}>25</option>
                        <option value={50}>50</option>
                    </select>
                </div>

                <div className="text-xs sm:text-sm">
                    Page {currentPage} of {totalPages || 1}
                </div>

                <div className="flex gap-2 justify-end">
                    <button
                        disabled={currentPage === 1}
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        className="p-2 border rounded disabled:opacity-40"
                    >
                        <FiChevronLeft />
                    </button>

                    <button
                        disabled={currentPage === totalPages}
                        onClick={() =>
                            setCurrentPage((p) => Math.min(totalPages, p + 1))
                        }
                        className="p-2 border rounded disabled:opacity-40"
                    >
                        <FiChevronRight />
                    </button>
                </div>
            </div>
            {selectedImage && (
                <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60">

                    <div className="relative bg-white dark:bg-gray-900 rounded-lg shadow-xl max-w-3xl w-full mx-4 p-6">

                        {/* Close Button */}
                        <button
                            onClick={() => setSelectedImage(null)}
                            className="absolute -top-4 -right-4 bg-white dark:bg-gray-800 shadow-md rounded-full p-2 hover:bg-gray-100 dark:hover:bg-gray-700 transition z-10"
                        >
                            <FiX size={22} className="text-black dark:text-white" />
                        </button>

                        {/* Image */}
                        <img
                            src={selectedImage}
                            alt="Wastage Proof"
                            className="w-full max-h-[70vh] object-contain rounded-md"
                        />

                    </div>
                </div>
            )}
        </div>
    );
}