import { useEffect, useState } from "react";
import { FiEye, FiTrash2 } from "react-icons/fi";
import { toast } from "react-toastify";
import api from "../../api/axios";
import ViewBatchModal from "./ViewBatchModal";

export default function SemiFinishedStockTable() {
    const [stocks, setStocks] = useState([]);
    const [loading, setLoading] = useState(false);
    const [selectedStock, setSelectedStock] = useState(null);
    const [showViewModal, setShowViewModal] = useState(false);

    // ✅ FETCH ALL PRODUCED BATCHES
    const fetchStock = async () => {
        try {
            setLoading(true);

            const res = await api.get(
                "/dish/get-semi-finished/productions-record"
            );

            console.log("All Productions API:", res.data);

            // API returns: { success: true, productions: [] }
            setStocks(Array.isArray(res.data?.productions) ? res.data.productions : []);

        } catch (err) {
            console.error("Failed to fetch productions", err);
            toast.error("Failed to load produced batches");
            setStocks([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchStock();
    }, []);

    const getExpiryStatus = (expiryDate) => {
        if (!expiryDate) {
            return { label: "NO EXPIRY", color: "text-gray-500" };
        }

        const now = new Date();
        const expiry = new Date(expiryDate);

        const diffTime = expiry - now;
        const diffDays = diffTime / (1000 * 60 * 60 * 24);

        if (diffDays <= 0) {
            return { label: "EXPIRED", color: "text-red-600" };
        }

        if (diffDays <= 3) {
            return { label: "NEAR EXPIRY", color: "text-yellow-600" };
        }

        return { label: "SAFE TO USE", color: "text-green-600" };
    };


    // const handleDeleteBatch = async (stockId) => {
    //     if (!window.confirm("Delete this batch?")) return;

    //     try {
    //         await api.delete(`/dish/semi-finished/stock/${stockId}`);
    //         toast.success("Batch deleted successfully");
    //         fetchStock();
    //     } catch (err) {
    //         console.error("Delete failed", err);
    //         toast.error(
    //             err.response?.data?.detail || "Cannot delete this batch"
    //         );
    //     }
    // };

    return (
        <div className="mt-8 border border-gray-200 dark:border-gray-800 rounded-xl">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
                <h3 className="text-md font-semibold text-gray-900 dark:text-gray-200">
                    All Produced Batches
                </h3>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-900">
                        <tr>
                            <th className="px-4 py-3 text-left">Batch ID</th>
                            <th className="px-4 py-3 text-left">Batch Number</th>
                            <th className="px-4 py-3 text-left">Item Name</th>
                            <th className="px-4 py-3 text-left">Produced Qty</th>
                            <th className="px-4 py-3 text-left">Remaining Qty</th>
                            <th className="px-4 py-3 text-left">Expiry</th>
                            <th className="px-4 py-3 text-left">Status</th>
                            <th className="px-4 py-3 text-center">View</th>
                            {/* <th className="px-4 py-3 text-center">Delete</th> */}
                        </tr>
                    </thead>

                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="9" className="text-center py-6">
                                    Loading batches...
                                </td>
                            </tr>
                        ) : stocks.length === 0 ? (
                            <tr>
                                <td colSpan="9" className="text-center py-6">
                                    No batches produced yet
                                </td>
                            </tr>
                        ) : (
                            stocks.map((stock) => (
                                <tr
                                    key={stock.stock_id}
                                    className="border-t border-gray-200 dark:border-gray-800"
                                >
                                    <td className="px-4 py-2">
                                        {stock.stock_id}
                                    </td>

                                    <td className="px-4 py-2">
                                        {stock.batch_number}
                                    </td>

                                    <td className="px-4 py-2">
                                        {stock.product_name}
                                    </td>

                                    <td className="px-4 py-2">
                                        {stock.quantity_produced} {stock.unit}
                                    </td>

                                    <td className="px-4 py-2">
                                        {stock.quantity_remaining} {stock.unit}
                                    </td>

                                    <td className="px-4 py-2">
                                        {stock.expiry_date
                                            ? new Date(stock.expiry_date).toLocaleString()
                                            : "No expiry"}
                                    </td>

                                    <td className="px-4 py-2">
                                        {(() => {
                                            const status = getExpiryStatus(stock.expiry_date);
                                            return (
                                              <span className={`px-2 py-1 rounded-full text-xs font-semibold ${status.color}`}>

                                                    {status.label}
                                                </span>
                                            );
                                        })()}
                                    </td>


                                    <td className="px-4 py-2 text-center">
                                        <button
                                            className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                                            onClick={() => {
                                                setSelectedStock(stock);
                                                setShowViewModal(true);
                                            }}
                                        >
                                            <FiEye />
                                        </button>
                                    </td>
{/* 
                                    <td className="px-4 py-2 text-center">
                                        <button
                                            onClick={() =>
                                                handleDeleteBatch(stock.stock_id)
                                            }
                                            className="p-2 rounded hover:bg-red-50 dark:hover:bg-red-900/20"
                                        >
                                            <FiTrash2 className="text-red-600" />
                                        </button>
                                    </td> */}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            <ViewBatchModal
                isOpen={showViewModal}
                onClose={() => {
                    setShowViewModal(false);
                    setSelectedStock(null);
                }}
                stock={selectedStock}
            />
        </div>
    );
}
