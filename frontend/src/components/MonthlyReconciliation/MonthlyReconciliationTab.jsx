import { useEffect, useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";
import AddPeriodModal from "./AddPeriodModal";
import { useNavigate } from "react-router-dom";
import PeriodDetails from "./PeriodDetails";
import EditPeriodModal from "./EditPeriodModal";

export default function MonthlyReconciliationTab() {
    const [periods, setPeriods] = useState([]);
    const [loading, setLoading] = useState(false);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [selectedPeriod, setSelectedPeriod] = useState(null);
    const navigate = useNavigate();

    const [selectedPeriodId, setSelectedPeriodId] = useState(null);


    const fetchPeriods = async () => {
        try {
            setLoading(true);
            const res = await api.get("/reconciliation/periods");

            if (res.data.success) {
                setPeriods(res.data.data);
            }
        } catch (error) {
            toast.error("Failed to fetch periods");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchPeriods();
    }, []);

    const totalPeriods = periods.length;
    const pendingApproval = periods.filter(
        (p) => p.status === "pending_approval"
    ).length;

    const closedPeriods = periods.filter(
        (p) => p.status === "closed"
    ).length;

    const totalAdjustment = periods.reduce(
        (acc, p) => acc + (p.total_variance_value || 0),
        0
    );

    if (selectedPeriodId) {
        return (
            <PeriodDetails
                periodId={selectedPeriodId}
                onBack={() => setSelectedPeriodId(null)}
            />
        );
    }

    return (

        
        <div className="p-6 min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300">
            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                    Monthly Reconciliation
                </h2>

                <button
                    onClick={() => setIsModalOpen(true)}
                    className="bg-yellow-500 hover:bg-yellow-600 dark:bg-yellow-400 dark:hover:bg-yellow-500 
                     text-white px-4 py-2 rounded-lg shadow-md transition"
                >
                    + New Period
                </button>
            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <SummaryCard title="Total Periods" value={totalPeriods} />
                <SummaryCard title="Pending Approval" value={pendingApproval} />
                <SummaryCard
                    title="Adjustment"
                    value={`₹ ${Number(totalAdjustment).toFixed(2)}`}
                />
                <SummaryCard title="Closed Period" value={closedPeriods} />
            </div>

            {/* Table */}
            <div className="bg-white dark:bg-gray-800 shadow-lg rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700">
                <table className="w-full text-sm">
                    <thead className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
                        <tr>
                            <th className="p-4 text-left">ID</th>
                            <th className="p-4 text-left">Label</th>
                            <th className="p-4 text-left">Year</th>
                            <th className="p-4 text-left">Month</th>
                            <th className="p-4 text-left">Status</th>
                            <th className="p-4 text-left">Variance</th>
                            <th className="p-4 text-left">Created</th>
                            <th className="p-4 text-left">Edit</th>
                        </tr>
                    </thead>

                    <tbody className="text-gray-700 dark:text-gray-300">
                        {loading ? (
                            <tr>
                                <td colSpan="7" className="text-center p-6">
                                    Loading...
                                </td>
                            </tr>
                        ) : periods.length === 0 ? (
                            <tr>
                                <td colSpan="7" className="text-center p-6">
                                    No periods found
                                </td>
                            </tr>
                        ) : (
                            periods.map((period) => (
                                <tr
                                    key={period.id}
                                    onClick={() => setSelectedPeriodId(period.id)}
                                    className="cursor-pointer border-t border-gray-200 dark:border-gray-700 
               hover:bg-gray-50 dark:hover:bg-gray-700 transition"
                                >
                                    <td className="p-4">{period.id}</td>
                                    <td className="p-4">{period.period_label}</td>
                                    <td className="p-4">{period.period_year}</td>
                                    <td className="p-4">{period.period_month}</td>
                                    <td className="p-4 capitalize">
                                        <span
                                            className={`px-2 py-1 rounded-full text-xs font-medium ${period.status === "draft"
                                                    ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300"
                                                    : period.status === "approved"
                                                        ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                                                        : period.status === "rejected"
                                                            ? "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300"
                                                            : "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                                                }`}
                                        >
                                            {period.status}
                                        </span>
                                    </td>
                                    <td className="p-4">
                                        ₹ {Number(period.total_variance_value || 0).toFixed(2)}
                                    </td>
                                    <td className="p-4">
                                        {new Date(period.created_at).toLocaleDateString()}
                                    </td>

                                    <td
                                        className="p-4"
                                        onClick={(e) => e.stopPropagation()}  // VERY IMPORTANT
                                    >
                                        {(period.status === "draft" || period.status === "in_progress") ? (
                                            <button
                                                onClick={async () => {
                                                    try {
                                                        const res = await api.get(
                                                            `/reconciliation/periods/${period.id}`
                                                        );

                                                        if (res.data.success) {
                                                            setSelectedPeriod(res.data.data);
                                                            setShowEditModal(true);
                                                        }
                                                    } catch (error) {
                                                        toast.error("Failed to load period details");
                                                    }
                                                }}
                                                className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                                            >
                                                ✏️
                                            </button>
                                        ) : (
                                            <span className="text-gray-400">—</span>
                                        )}
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {isModalOpen && (
                <AddPeriodModal
                    onClose={() => setIsModalOpen(false)}
                    onSuccess={fetchPeriods}
                />
            )}

            {showEditModal && selectedPeriod && (
                <EditPeriodModal
                    period={selectedPeriod}
                    onClose={() => {
                        setShowEditModal(false);
                        setSelectedPeriod(null);
                    }}
                    onSuccess={() => {
                        fetchPeriods();
                        setShowEditModal(false);
                        setSelectedPeriod(null);
                    }}
                />
            )}
        </div>
    );
}

function SummaryCard({ title, value }) {
    return (
        <div
            className="bg-white dark:bg-gray-800 p-5 rounded-xl shadow-md 
                 border border-gray-200 dark:border-gray-700 
                 hover:shadow-lg transition"
        >
            <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
            <h3 className="text-2xl font-bold mt-2 text-gray-800 dark:text-white">
                {value}
            </h3>
        </div>
    );
}