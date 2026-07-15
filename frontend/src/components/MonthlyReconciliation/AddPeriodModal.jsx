import { useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function AddPeriodModal({ onClose, onSuccess }) {
    const [formData, setFormData] = useState({
        period_year: new Date().getFullYear(),
        period_month: new Date().getMonth() + 1,
        costing_method: "weighted_average",
        variance_threshold_pct: 5,
        notes: "",
        tenant_id: 0,
    });

    const handleChange = (e) => {
        setFormData({
            ...formData,
            [e.target.name]: e.target.value,
        });
    };

    const handleSubmit = async () => {
        try {
            const res = await api.post(
                "/reconciliation/periods",
                formData
            );

            if (res.data.success) {
                toast.success("Period created successfully");
                onSuccess();
                onClose();
            }
        } catch (error) {
            toast.error("Failed to create period");
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 flex justify-center items-center z-50">
            <div
                className="bg-white dark:bg-gray-800 w-[420px] rounded-xl shadow-2xl 
                   p-6 border border-gray-200 dark:border-gray-700"
            >
                <h3 className="text-xl font-semibold mb-5 text-gray-800 dark:text-white">
                    Create New Period
                </h3>

                <div className="space-y-4">
                    <Input
                        label="Year"
                        name="period_year"
                        type="number"
                        value={formData.period_year}
                        onChange={handleChange}
                    />

                    <Input
                        label="Month"
                        name="period_month"
                        type="number"
                        value={formData.period_month}
                        onChange={handleChange}
                    />

                    <Input
                        label="Variance Threshold %"
                        name="variance_threshold_pct"
                        type="number"
                        value={formData.variance_threshold_pct}
                        onChange={handleChange}
                    />

                    <div>
                        <label className="text-sm text-gray-600 dark:text-gray-400">
                            Notes
                        </label>
                        <textarea
                            name="notes"
                            value={formData.notes}
                            onChange={handleChange}
                            className="w-full mt-1 border border-gray-300 dark:border-gray-600 
                         bg-white dark:bg-gray-700 text-gray-800 dark:text-white
                         p-2 rounded-md focus:outline-none focus:ring-2 
                         focus:ring-yellow-500"
                        />
                    </div>
                </div>

                <div className="flex justify-end gap-3 mt-6">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-md border border-gray-300 dark:border-gray-600 
                       text-gray-700 dark:text-gray-300 hover:bg-gray-100 
                       dark:hover:bg-gray-700 transition"
                    >
                        Cancel
                    </button>

                    <button
                        onClick={handleSubmit}
                        className="px-4 py-2 rounded-md bg-green-500 hover:bg-green-600 
                       text-white shadow-md transition"
                    >
                        Submit
                    </button>
                </div>
            </div>
        </div>
    );
}

function Input({ label, ...props }) {
    return (
        <div>
            <label className="text-sm text-gray-600 dark:text-gray-400">
                {label}
            </label>
            <input
                {...props}
                className="w-full mt-1 border border-gray-300 dark:border-gray-600 
                   bg-white dark:bg-gray-700 text-gray-800 dark:text-white
                   p-2 rounded-md focus:outline-none focus:ring-2 
                   focus:ring-yellow-500"
            />
        </div>
    );
}