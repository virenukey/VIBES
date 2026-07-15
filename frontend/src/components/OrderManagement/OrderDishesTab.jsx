import { useState, useEffect } from "react";
import {
    FiSearch,
    FiChevronLeft,
    FiChevronRight,
} from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";
import OrderConfirmationModal from "./OrderConfirmationModal";

export default function OrderDishesTab() {
    const [dishes, setDishes] = useState([]);
    const [rowsPerPage, setRowsPerPage] = useState(10);
    const [currentPage, setCurrentPage] = useState(1);
    const [searchText, setSearchText] = useState("");
    const [loading, setLoading] = useState(false);
    const [selectedDish, setSelectedDish] = useState(null);
    const [showModal, setShowModal] = useState(false);

    /* ================= FETCH DISHES ================= */
    useEffect(() => {
        fetchDishes();
    }, []);

    const fetchDishes = async () => {
        try {
            setLoading(true);

            const res = await api.get("/dish/dishes");
            
            setDishes(res.data.data || []);
        } catch (err) {
            console.error("Failed to fetch dishes", err);
            toast.error("Failed to load dishes ❌");
        } finally {
            setLoading(false);
        }
    };

    const filteredData = dishes.filter(
        (d) =>
            d.name?.toLowerCase().includes(searchText.toLowerCase()) ||
            d.type?.name?.toLowerCase().includes(searchText.toLowerCase())
    );

    const totalPages = Math.ceil(filteredData.length / rowsPerPage) || 1;

    const paginatedData = filteredData.slice(
        (currentPage - 1) * rowsPerPage,
        currentPage * rowsPerPage
    );

    return (
        <div className="w-full">
            {/* Toolbar */}
            <div className="flex flex-col xl:flex-row xl:items-center xl:justify-end gap-3 px-4 sm:px-6 py-4">
                <div className="relative">
                    <FiSearch className="absolute left-3 top-3 text-gray-400 dark:text-gray-500" />
                    <input
                        type="text"
                        placeholder="Search dish..."
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
            </div>

            {/* Table */}
            <div className="w-full overflow-x-auto">
                <table className="w-full border-t border-gray-200 dark:border-gray-800">
                    <thead className="bg-gray-50 dark:bg-gray-900">
                        <tr>
                            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                                Item Name
                            </th>
                            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                                Category
                            </th>
                            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                                Price
                            </th>
                            <th className="px-4 py-3 text-center w-32 text-sm font-semibold text-gray-800 dark:text-gray-200">
                                Order
                            </th>
                        </tr>
                    </thead>

                    <tbody>
                        {loading ? (
                            <tr>
                                <td
                                    colSpan={4}
                                    className="px-4 py-6 text-center text-sm text-gray-500"
                                >
                                    Loading dishes...
                                </td>
                            </tr>
                        ) : paginatedData.length === 0 ? (
                            <tr>
                                <td
                                    colSpan={4}
                                    className="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400"
                                >
                                    No dishes found
                                </td>
                            </tr>
                        ) : (
                            paginatedData.map((dish) => (
                                <tr
                                    key={dish.id}
                                    className="border-t border-gray-200 dark:border-gray-800"
                                >
                                    <td className="px-4 py-2 text-sm text-gray-800 dark:text-gray-200">
                                        {dish.name}
                                    </td>

                                    <td className="px-4 py-2 text-sm text-gray-800 dark:text-gray-200">
                                        {dish.type?.name}
                                    </td>

                                    <td className="px-4 py-2 text-sm text-gray-800 dark:text-gray-200">
                                        ₹ {dish.selling_price}
                                    </td>

                                    <td className="px-4 py-2 text-center">
                                        <button
                                            onClick={() => {
                                                setSelectedDish(dish);
                                                setShowModal(true);
                                            }}
                                            className="px-4 py-1.5 rounded-lg text-sm font-medium bg-orange-500 text-white hover:bg-orange-600 transition"
                                        >
                                            Order
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
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
                        className="px-3 py-1 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
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
                        className="p-2 rounded-md 
border border-gray-200 dark:border-gray-700 
text-gray-700 dark:text-gray-200
hover:bg-gray-100 dark:hover:bg-gray-800 
disabled:opacity-40 disabled:cursor-not-allowed"                    >
                        <FiChevronLeft />
                    </button>

                    <button
                        disabled={currentPage === totalPages}
                        onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                        className="p-2 rounded-md 
border border-gray-200 dark:border-gray-700 
text-gray-700 dark:text-gray-200
hover:bg-gray-100 dark:hover:bg-gray-800 
disabled:opacity-40 disabled:cursor-not-allowed"                    >
                        <FiChevronRight />
                    </button>
                </div>
            </div>
            <OrderConfirmationModal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                dish={selectedDish}
                onSuccess={() => {
                    setShowModal(false);
                }}
            />
        </div>
        
    );
}