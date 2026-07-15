import { useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function PhysicalCountModal({
    periodId,
    lineItems,
    onClose,
    onSuccess,
}) {
    const [selectedItemId, setSelectedItemId] = useState("");
    const [quantity, setQuantity] = useState("");
    const [notes, setNotes] = useState("");
    const [loading, setLoading] = useState(false);

    const handleSubmit = async () => {
        if (!selectedItemId || !quantity) {
            toast.error("Please fill all required fields");
            return;
        }

        try {
            setLoading(true);

            const selectedItem = lineItems.find(
                (i) => i.inventory_item_id === Number(selectedItemId)
            );

            const payload = {
                counts: [
                    {
                        inventory_item_id: selectedItem.inventory_item_id,
                        count_type: "closing",
                        counted_quantity: Number(quantity),
                        unit: selectedItem.unit,
                        storage_location: "Main Storage",
                        batch_number: "",
                        notes: notes,
                    },
                ],
            };

            const res = await api.post(
                `/reconciliation/periods/${periodId}/physical-counts`,
                payload
            );

            if (res.data.success) {
                toast.success("Physical count submitted");
                onSuccess();
            }
        } catch (error) {
            toast.error("Failed to submit physical count");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 text-gray-800 dark:text-white">
            <div className="bg-white dark:bg-gray-800 w-[420px] p-6 rounded-xl shadow-xl">

                <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-white">
                    Add Physical Count
                </h3>

                {/* Dropdown */}
                <select
                    value={selectedItemId}
                    onChange={(e) => setSelectedItemId(e.target.value)}
                    className="
        w-full mb-4 px-4 py-2.5 
        rounded-lg border 
        border-gray-300 dark:border-gray-600
        bg-white dark:bg-gray-800
        text-gray-800 dark:text-white
        shadow-sm
        focus:outline-none 
        focus:ring-2 focus:ring-green-500 
        focus:border-transparent
        hover:border-gray-400 dark:hover:border-gray-500
        transition duration-200
        cursor-pointer
    "
                >
                    <option value="" className="text-gray-400">
                        Select Item
                    </option>

                    {lineItems.map((item) => (
                        <option
                            key={item.inventory_item_id}
                            value={item.inventory_item_id}
                            className="bg-white dark:bg-gray-800 text-gray-800 dark:text-white"
                        >
                            {item.item_name}
                        </option>
                    ))}
                </select>

                <input
                    type="number"
                    placeholder="Enter counted quantity"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    className="w-full mb-3 px-3 py-2 border rounded-md"
                />

                <textarea
                    placeholder="Notes (optional)"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="w-full mb-3 px-3 py-2 border rounded-md"
                />

                <div className="flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 border rounded"
                    >
                        Cancel
                    </button>

                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="px-4 py-2 bg-green-500 text-white rounded"
                    >
                        {loading ? "Submitting..." : "Submit"}
                    </button>
                </div>
            </div>
        </div>
    );
}