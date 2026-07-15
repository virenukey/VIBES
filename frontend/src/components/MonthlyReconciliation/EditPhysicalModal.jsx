import { useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function EditPhysicalModal({
    periodId,
    lineItem,
    onClose,
    onSuccess,
}) {
    const [quantity, setQuantity] = useState(
        lineItem.physical_closing_quantity ?? ""
    );
    const [notes, setNotes] = useState(lineItem.variance_notes || "");
    const [loading, setLoading] = useState(false);

    const handleUpdate = async () => {
        if (quantity === "") {
            toast.error("Physical quantity is required");
            return;
        }

        try {
            setLoading(true);

            const res = await api.put(
                `/reconciliation/periods/${periodId}/line-items/${lineItem.id}`,
                {
                    physical_closing_quantity: Number(quantity),
                    variance_notes: notes,
                }
            );

            if (res.data.success) {
                toast.success("Physical count updated");
                onSuccess();
            }
        } catch (error) {
            toast.error("Failed to update physical count");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 w-[400px] p-6 rounded-xl shadow-xl">

                <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-white">
                    Edit Physical Count
                </h3>

                <p className="text-sm mb-3 text-gray-500 dark:text-gray-400">
                    Item: {lineItem.item_name}
                </p>

                <input
                    type="number"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    placeholder="Physical Quantity"
                    className="w-full mb-3 px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
                />

                <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Variance Notes (optional)"
                    className="w-full mb-3 px-3 py-2 border rounded-md dark:bg-gray-700 dark:border-gray-600"
                />

                <div className="flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 border rounded"
                    >
                        Cancel
                    </button>

                    <button
                        onClick={handleUpdate}
                        disabled={loading}
                        className="px-4 py-2 bg-green-600 text-white rounded"
                    >
                        {loading ? "Updating..." : "Update"}
                    </button>
                </div>
            </div>
        </div>
    );
}