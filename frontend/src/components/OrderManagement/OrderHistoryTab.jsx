import { useEffect, useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";
import { FiInfo, FiChevronLeft, FiChevronRight } from "react-icons/fi";

export default function OrderHistoryTab() {
    const [orders, setOrders] = useState([]);
    const [dishMap, setDishMap] = useState({});
    const [statusFilter, setStatusFilter] = useState("ALL");

    const [rowsPerPage, setRowsPerPage] = useState(10);
    const [currentPage, setCurrentPage] = useState(1);

    useEffect(() => {
        fetchDishes();
        fetchOrders();
    }, []);

    const fetchDishes = async () => {
        try {
            const res = await api.get("/dish/dishes");
            const dishes = Array.isArray(res.data)
                ? res.data
                : res.data.data || [];

            const map = {};
            dishes.forEach((dish) => {
                map[dish.id] = {
                    name: dish.name,
                    category: dish.type?.name,
                };
            });

            setDishMap(map);
        } catch {
            console.error("Failed to fetch dishes");
        }
    };

    const fetchOrders = async () => {
        try {
            const res = await api.get("/oders/");
            const orderList = res.data || [];

            const historyOrders = orderList.filter((order) =>
                ["COMPLETED", "CANCELLED", "REFUNDED"].includes(order.status)
            );

            const detailedOrders = await Promise.all(
                historyOrders.map(async (order) => {
                    const detailRes = await api.get(`/oders/${order.id}`);
                    return detailRes.data;
                })
            );

            setOrders(detailedOrders);
        } catch {
            toast.error("Failed to fetch order history ❌");
        }
    };

    /* ================= FILTER + PAGINATION ================= */

    const filteredOrders = orders.filter((order) =>
        statusFilter === "ALL" ? true : order.status === statusFilter
    );

    const totalPages =
        Math.ceil(filteredOrders.length / rowsPerPage) || 1;

    const startIndex = (currentPage - 1) * rowsPerPage;

    const paginatedOrders = filteredOrders.slice(
        startIndex,
        startIndex + rowsPerPage
    );

    return (
        <div className="px-6 py-4 text-gray-800 dark:text-gray-200">

            {/* Header */}
            <div className="flex justify-between items-center mb-4">
                <h3 className="font-medium">Orders History</h3>

                <div className="flex gap-3">
                    {["ALL", "COMPLETED", "CANCELLED"].map((status) => (
                        <button
                            key={status}
                            onClick={() => {
                                setStatusFilter(status);
                                setCurrentPage(1);
                            }}
                            className={`px-4 py-1.5 rounded-lg text-sm font-medium border transition-all duration-200 ${statusFilter === status
                                    ? "bg-orange-500 text-white border-orange-500 shadow-sm"
                                    : "bg-white dark:bg-[#0f172a] text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
                                }`}
                        >
                            {status}
                        </button>
                    ))}
                </div>
            </div>

            {/* Table */}
            <table className="w-full border-t border-gray-200 dark:border-gray-800">
                <thead className="bg-gray-50 dark:bg-gray-900">
                    <tr>
                        <th className="px-4 py-3 text-left text-sm font-semibold">
                            Dish Name
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-semibold">
                            Order Number
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-semibold">
                            Amount
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-semibold">
                            Payment Status
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-semibold">
                            Payment Mode
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-semibold">
                            Order Type
                        </th>
                        <th className="px-4 py-3 text-left text-sm font-semibold">
                            Status
                        </th>
                    </tr>
                </thead>

                <tbody>
                    {paginatedOrders.length === 0 ? (
                        <tr>
                            <td
                                colSpan={7}
                                className="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400"
                            >
                                No orders found
                            </td>
                        </tr>
                    ) : (
                        paginatedOrders.map((order) => {
                            const firstItem = order.items?.[0];
                            const dishDetails =
                                dishMap[firstItem?.dish_id] || {};

                            const paymentMode =
                                order.payments?.[0]?.payment_method || "-";

                            return (
                                <tr
                                    key={order.id}
                                    className="border-t border-gray-200 dark:border-gray-800"
                                >
                                    <td className="px-4 py-2 text-sm">
                                        {dishDetails.name || "-"}
                                    </td>
                                    <td className="px-4 py-2 text-sm">
                                        {order.order_number}
                                    </td>
                                    <td className="px-4 py-2 text-sm">
                                        ₹ {order.total_amount}
                                    </td>
                                    <td className="px-4 py-2 text-sm">
                                        {order.payment_status}
                                    </td>
                                    <td className="px-4 py-2 text-sm">
                                        {paymentMode}
                                    </td>
                                    <td className="px-4 py-2 text-sm">
                                        {order.order_type}
                                    </td>
                                    <td
                                        className={`px-4 py-2 text-sm font-semibold ${order.status === "CANCELLED"
                                                ? "text-red-600"
                                                : order.status === "COMPLETED"
                                                    ? "text-green-600"
                                                    : ""
                                            }`}
                                    >
                                        {order.status}
                                    </td>
                                </tr>
                            );
                        })
                    )}
                </tbody>
            </table>

            {/* Pagination */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 px-4 py-4">
                <div className="flex items-center gap-2 text-sm">
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

                <div className="text-sm font-medium">
                    Page {currentPage} of {totalPages}
                </div>

                <div className="flex items-center gap-2">
                    <button
                        disabled={currentPage === 1}
                        onClick={() =>
                            setCurrentPage((p) => Math.max(1, p - 1))
                        }
                        className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                    >
                        <FiChevronLeft />
                    </button>

                    <button
                        disabled={currentPage === totalPages}
                        onClick={() =>
                            setCurrentPage((p) =>
                                Math.min(totalPages, p + 1)
                            )
                        }
                        className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                    >
                        <FiChevronRight />
                    </button>
                </div>
            </div>
        </div>
    );
}