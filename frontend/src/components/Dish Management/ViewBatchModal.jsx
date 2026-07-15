import { FiX } from "react-icons/fi";

export default function ViewBatchModal({ isOpen, onClose, stock }) {
    if (!isOpen || !stock) return null;

    const formatDate = (date) =>
        date ? new Date(date).toLocaleString() : "N/A";


    const getExpiryStatus = () => {
        if (!stock.expiry_date) {
            return { label: "NO EXPIRY", color: "text-gray-500" };
        }

        const now = new Date();
        const expiry = new Date(stock.expiry_date);

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


    const status = getExpiryStatus();

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            <div
                className="absolute inset-0 bg-black/40"
                onClick={onClose}
            ></div>

            <div className="relative w-full max-w-md bg-white dark:bg-[#0f172a] rounded-xl shadow-xl border border-gray-200 dark:border-gray-800 p-6">

                <div className="flex justify-between items-center mb-4">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                        Batch Details
                    </h3>
                    <button onClick={onClose}>
                        <FiX className="text-xl" />
                    </button>
                </div>

                <div className="space-y-3 text-sm text-gray-700 dark:text-gray-200">

                    <div><strong>Batch ID:</strong> {stock.stock_id}</div>

                    <div><strong>Batch Number:</strong> {stock.batch_number}</div>

                    <div><strong>Item Name:</strong> {stock.product_name}</div>

                    <div>
                        <strong>Quantity Produced:</strong>{" "}
                        {stock.quantity_produced} {stock.unit}
                    </div>

                    <div>
                        <strong>Quantity Remaining:</strong>{" "}
                        {stock.quantity_remaining} {stock.unit}
                    </div>

                    <div>
                        <strong>Produced At:</strong>{" "}
                        {formatDate(stock.produced_at)}
                    </div>

                    <div>
                        <strong>Expiry Date:</strong>{" "}
                        {formatDate(stock.expiry_date)}
                    </div>

                    <div className={status.color}>
                        <strong>Status:</strong> {status.label}
                    </div>

                    <div>
                        <strong>Total Cost:</strong> ₹{stock.total_cost}
                    </div>

                    <div>
                        <strong>Cost Per Unit:</strong> ₹{stock.cost_per_unit}
                    </div>

                </div>
            </div>
        </div>
    );
}
