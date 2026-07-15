import { useState, useEffect } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function EditPeriodModal({
    period,
    onClose,
    onSuccess,
}) {
    const [variance, setVariance] = useState("");
    const [costingMethod, setCostingMethod] = useState("");
    const [notes, setNotes] = useState("");
    const [loading, setLoading] = useState(false);


    useEffect(() => {
        if (period) {
            setVariance(period.variance_threshold_pct ?? "");
            setCostingMethod(period.costing_method ?? "weighted_average");
            setNotes(period.notes ?? "");
        }
    }, [period]);
    const handleUpdate = async () => {
        try {
            setLoading(true);

            const res = await api.put(
                `/reconciliation/periods/${period.id}`,
                {
                    variance_threshold_pct: Number(variance),
                    costing_method: costingMethod,
                    notes: notes,
                }
            );

            // 👇 ADD THESE CONSOLE LOGS HERE
            console.log("Full Response:", res.data);
            console.log("Updated Costing Method:", res.data.data.costing_method);

            if (res.data.success) {
                toast.success("Period updated successfully");
                onSuccess();
            }

        } catch (error) {
            toast.error("Failed to update period");
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
                        Edit Period Settings
                    </h3>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-red-500 transition"
                    >
                        ✕
                    </button>
                </div>

                {/* Variance */}
                <div className="mb-5">
                    <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">
                        Variance Threshold (%)
                    </label>
                    <input
                        type="number"
                        value={variance}
                        onChange={(e) => setVariance(e.target.value)}
                        className="w-full px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition"
                    />
                </div>

                {/* Costing Method */}
                <div className="mb-5">
                    <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">
                        Costing Method
                    </label>
                    <select
                        value={costingMethod}
                        onChange={(e) => setCostingMethod(e.target.value)}
                        className="w-full px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition"
                    >
                        <option value="weighted_average">
                            Weighted Average
                        </option>
                        <option value="fifo">
                            FIFO (First In First Out)
                        </option>
                    </select>
                </div>

                {/* Notes */}
                <div className="mb-6">
                    <label className="block text-sm font-medium text-gray-600 dark:text-gray-300 mb-1">
                        Notes
                    </label>
                    <textarea
                        rows="3"
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        className="w-full px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 text-gray-800 dark:text-white focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition resize-none"
                    />
                </div>

                {/* Buttons */}
                <div className="flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
                    >
                        Cancel
                    </button>

                    <button
                        onClick={handleUpdate}
                        disabled={loading}
                        className="px-5 py-2 rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium transition shadow-md hover:shadow-lg"
                    >
                        {loading ? "Updating..." : "Update"}
                    </button>
                </div>
            </div>
        </div>
    );
}