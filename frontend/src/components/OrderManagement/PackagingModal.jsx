import { useState, useEffect } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function PackagingModal({
    isOpen,
    onClose,
    order,
    inventoryItems,
    onSuccess
}) {
    const [selectedItems, setSelectedItems] = useState([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!isOpen) {
            setSelectedItems([]);
        }
    }, [isOpen]);

    if (!isOpen || !order || !Array.isArray(inventoryItems)) return null;

    /* ================= ADD ITEM ================= */
    const handleAddItem = (itemId) => {
        const exists = selectedItems.find(
            item => item.inventory_item_id === itemId
        );

        if (exists) {
            toast.warning("Item already selected");
            return;
        }

        setSelectedItems((prev) => [
            ...prev,
            { inventory_item_id: itemId, quantity: 1 }
        ]);
    };

    /* ================= CHANGE QUANTITY ================= */
    const handleQuantityChange = (index, value) => {
        const updated = [...selectedItems];
        updated[index].quantity = value;
        setSelectedItems(updated);
    };

    /* ================= SUBMIT ================= */
    const handleSubmit = async () => {
        if (selectedItems.length === 0) {
            toast.error("Select at least one packaging item");
            return;
        }

        try {
            setLoading(true);

            await api.post(`/oders/${order.id}/packaging`, selectedItems);

            toast.success("Packaging added successfully");

            onSuccess();
            onClose();
        } catch (err) {
            console.error(err.response?.data || err.message);
            toast.error("Packaging failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
            <div className="bg-white w-full max-w-lg rounded-xl p-6">
                <h2 className="text-lg font-semibold mb-4">
                    Add Packaging for {order.order_number}
                </h2>

                <div className="space-y-3 max-h-64 overflow-y-auto">
                    {inventoryItems.map((item) => (
                        <button
                            key={item.id}
                            onClick={() => handleAddItem(item.id)}
                            className="w-full border p-2 rounded hover:bg-gray-100 text-left"
                        >
                            {item.name}
                        </button>
                    ))}
                </div>

                {selectedItems.map((item, index) => (
                    <div key={index} className="flex gap-2 mt-3">
                        <span className="flex-1">
                            {inventoryItems.find(i => i.id === item.inventory_item_id)?.name}
                        </span>
                        <input
                            type="number"
                            value={item.quantity}
                            min="1"
                            onChange={(e) =>
                                handleQuantityChange(index, parseInt(e.target.value))
                            }
                            className="w-20 border rounded px-2"
                        />
                    </div>
                ))}

                <div className="flex gap-3 mt-6">
                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="px-4 py-2 bg-green-600 text-white rounded"
                    >
                        {loading ? "Adding..." : "Add & Continue"}
                    </button>

                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-gray-300 rounded"
                    >
                        Cancel
                    </button>
                </div>
            </div>
        </div>
    );
}