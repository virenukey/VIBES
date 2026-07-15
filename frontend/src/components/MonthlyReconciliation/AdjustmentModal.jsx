import { useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function AdjustmentModal({
    periodId,
    lineItems,
    onClose,
    onSuccess,
}) {
    const [inventoryItemId, setInventoryItemId] = useState("");
    const [reason, setReason] = useState("physical_count_variance");
    const [quantity, setQuantity] = useState("");
    const [notes, setNotes] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async () => {
        if (!inventoryItemId || !quantity) {
            toast.error("Item and quantity are required");
            return;
        }

        try {
            setLoading(true);

            const res = await api.post(
                `/reconciliation/periods/${periodId}/adjustments`,
                {
                    inventory_item_id: Number(inventoryItemId),
                    reason,
                    quantity_adjusted: Number(quantity),
                    notes,
                }
            );

            if (res.data.success) {
                toast.success("Adjustment added");
                onSuccess();
            }
        } catch (error) {
            toast.error("Failed to add adjustment");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 px-4">
            <div className="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 p-6 transition-all duration-300">

                {/* Header */}
                <div className="flex justify-between items-center mb-6">
                    <h3 className="text-xl font-semibold text-gray-800 dark:text-white">
                        Add Adjustment
                    </h3>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-red-500 transition"
                    >
                        ✕
                    </button>
                </div>

                {/* Item Dropdown */}
                <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">
                        Select Item
                    </label>
                    <select
                        value={inventoryItemId}
                        onChange={(e) => setInventoryItemId(e.target.value)}
                        className="
                        w-full px-4 py-2.5 rounded-lg border 
                        border-gray-300 dark:border-gray-600
                        bg-gray-50 dark:bg-gray-800
                        text-gray-800 dark:text-white
                        focus:outline-none focus:ring-2 focus:ring-yellow-500
                        transition
                    "
                    >
                        <option value="">Select Item</option>
                        {lineItems.map((item) => (
                            <option key={item.id} value={item.inventory_item_id}>
                                {item.item_name}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Reason */}
                <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">
                        Reason
                    </label>
                    <select
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        className="
                        w-full px-4 py-2.5 rounded-lg border 
                        border-gray-300 dark:border-gray-600
                        bg-gray-50 dark:bg-gray-800
                        text-gray-800 dark:text-white
                        focus:outline-none focus:ring-2 focus:ring-yellow-500
                        transition
                    "
                    >
                        <option value="physical_count_variance">Physical Count Variance</option>
                        <option value="damage">Damage</option>
                        <option value="theft">Theft</option>
                        <option value="expiry">Expiry</option>
                        <option value="data_entry_error">Data Entry Error</option>
                        <option value="other">Other</option>
                    </select>
                </div>

                {/* Quantity */}
                <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">
                        Quantity Adjusted
                    </label>
                    <input
                        type="number"
                        placeholder="Enter quantity"
                        value={quantity}
                        onChange={(e) => setQuantity(e.target.value)}
                        className="
                        w-full px-4 py-2.5 rounded-lg border 
                        border-gray-300 dark:border-gray-600
                        bg-gray-50 dark:bg-gray-800
                        text-gray-800 dark:text-white
                        focus:outline-none focus:ring-2 focus:ring-yellow-500
                        transition
                    "
                    />
                </div>

                {/* Notes */}
                <div className="mb-6">
                    <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">
                        Notes
                    </label>
                    <textarea
                        rows="3"
                        placeholder="Optional notes..."
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        className="
                        w-full px-4 py-2.5 rounded-lg border 
                        border-gray-300 dark:border-gray-600
                        bg-gray-50 dark:bg-gray-800
                        text-gray-800 dark:text-white
                        focus:outline-none focus:ring-2 focus:ring-yellow-500
                        resize-none
                        transition
                    "
                    />
                </div>

                {/* Buttons */}
                <div className="flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="
                        px-4 py-2 rounded-lg border 
                        border-gray-300 dark:border-gray-600
                        text-gray-700 dark:text-gray-300
                        hover:bg-gray-100 dark:hover:bg-gray-800
                        transition
                    "
                    >
                        Cancel
                    </button>

                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="
                        px-5 py-2 rounded-lg 
                        bg-yellow-500 hover:bg-yellow-600 
                        disabled:opacity-50 disabled:cursor-not-allowed
                        text-white font-medium
                        shadow-md hover:shadow-lg
                        transition
                    "
                    >
                        {loading ? "Saving..." : "Save"}
                    </button>
                </div>
            </div>
        </div>
    );
}