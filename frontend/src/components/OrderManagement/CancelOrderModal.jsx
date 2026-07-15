import { useState } from "react";
import { toast } from "react-toastify";
export default function CancelOrderModal({
    isOpen,
    onClose,
    onConfirm,
}) {
    const [reason, setReason] = useState("");

    if (!isOpen) return null;

    const handleConfirm = () => {
        if (!reason || reason.length < 5) {
            toast.error("Cancellation reason must be at least 5 characters");
            return;
        }

        onConfirm(reason);
        setReason("");
    };

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white w-full max-w-md rounded-2xl shadow-2xl p-6">

                <h2 className="text-lg font-semibold mb-4 text-gray-800">
                    Cancel Order
                </h2>

                <p className="text-sm text-gray-600 mb-3">
                    Please provide a reason for cancellation.
                </p>

                <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Enter cancellation reason..."
                    className="w-full border rounded-lg p-3 text-sm focus:ring-2 focus:ring-red-400 outline-none resize-none"
                    rows={3}
                />

                <div className="flex justify-end gap-3 mt-5">
                    <button
                        onClick={() => {
                            setReason("");
                            onClose();
                        }}
                        className="px-4 py-2 rounded-lg bg-gray-200 hover:bg-gray-300 transition"
                    >
                        Close
                    </button>

                    <button
                        onClick={handleConfirm}
                        className="px-4 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 transition"
                    >
                        Confirm Cancel
                    </button>
                </div>
            </div>
        </div>
    );
}