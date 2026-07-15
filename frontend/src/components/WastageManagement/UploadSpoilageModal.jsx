import { useEffect, useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function UploadSpoilageModal({
    isOpen,
    onClose,
    onSuccess,
}) {
    const [items, setItems] = useState([]);
    const [selectedItem, setSelectedItem] = useState("");
    const [quantity, setQuantity] = useState("");
    const [reason, setReason] = useState("");
    const [notes, setNotes] = useState("");
    const [photo, setPhoto] = useState(null);

    // Fetch inventory items
    const fetchInventory = async () => {
        try {
            const res = await api.get("/inventory/", {
                params: { lifecycle_stage: "fresh" },
            });
            setItems(res.data.data || []);
        } catch (err) {
            console.error("Failed to fetch inventory", err);
        }
    };

    useEffect(() => {
        if (isOpen) fetchInventory();
    }, [isOpen]);

    const handleSubmit = async () => {
        if (!selectedItem || !quantity || !reason) {
            toast.error("Please fill all required fields");
            return;
        }

        try {
            const formData = new FormData();
            formData.append("inventory_item_id", selectedItem);
            formData.append("quantity_wasted", quantity);
            formData.append("unit", items.find(i => i.id == selectedItem)?.unit);
            formData.append("wastage_reason", reason);
            formData.append("notes", notes);
            formData.append("wastage_date", new Date().toISOString());

            if (photo) formData.append("photo", photo);

            await api.post("/wastage/add-inventory-wastage", formData, {
                headers: { "Content-Type": "multipart/form-data" },
            });

            toast.success("Spoilage recorded successfully");
            onSuccess();
            onClose();

            setSelectedItem("");
            setQuantity("");
            setReason("");
            setNotes("");
            setPhoto(null);

        } catch (err) {
            console.error("Failed to save spoilage", err);
            toast.error("Failed to record spoilage");
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 px-4">
            <div className="w-full max-w-md bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-xl shadow-xl p-6 space-y-5">

                <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    Upload Spoilage
                </h2>

                {/* Select Item */}
                <div className="space-y-1">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Item *
                    </label>
                    <select
                        value={selectedItem}
                        onChange={(e) => setSelectedItem(e.target.value)}
                        className="w-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-md px-3 py-2 focus:ring-2 focus:ring-yellow-400 outline-none"
                    >
                        <option value="">Select Item</option>
                        {items.map(item => (
                            <option key={item.id} value={item.id}>
                                {item.name}
                            </option>
                        ))}
                    </select>
                </div>

                {/* Quantity */}
                <div className="space-y-1">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Quantity *
                    </label>
                    <input
                        type="number"
                        placeholder="Enter quantity"
                        value={quantity}
                        onChange={(e) => setQuantity(e.target.value)}
                        className="w-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-md px-3 py-2 focus:ring-2 focus:ring-yellow-400 outline-none"
                    />
                </div>

                {/* Reason */}
                <div className="space-y-1">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Reason *
                    </label>
                    <select
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        className="w-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-md px-3 py-2 focus:ring-2 focus:ring-yellow-400 outline-none"
                    >
                        <option value="">Select Reason</option>
                        <option value="damage">Damage</option>
                        <option value="contamination">Contamination</option>
                        <option value="spillage">Spillage</option>
                    </select>
                </div>

                {/* Upload Photo - Improved */}
                <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Upload Proof
                    </label>

                    <label className="flex flex-col items-center justify-center w-full border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg cursor-pointer bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition p-4 text-center">

                        <span className="text-sm text-gray-600 dark:text-gray-400">
                            {photo ? photo.name : "Click to upload image"}
                        </span>

                        <input
                            type="file"
                            accept="image/*"
                            onChange={(e) => setPhoto(e.target.files[0])}
                            className="hidden"
                        />
                    </label>
                </div>

                {/* Notes */}
                <div className="space-y-1">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Notes (Optional)
                    </label>
                    <textarea
                        placeholder="Enter notes..."
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        rows={3}
                        className="w-full border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-md px-3 py-2 focus:ring-2 focus:ring-yellow-400 outline-none resize-none"
                    />
                </div>

                {/* Buttons */}
                <div className="flex justify-end gap-3 pt-2">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-md border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
                    >
                        Cancel
                    </button>

                    <button
                        onClick={handleSubmit}
                        className="px-4 py-2 bg-green-500 hover:bg-green-600 text-white rounded-md transition"
                    >
                        Save
                    </button>
                </div>

            </div>
        </div>
    );
}