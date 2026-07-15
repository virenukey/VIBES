import { useEffect, useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";
import PhysicalCountModal from "./PhysicalCountModal";
import EditPhysicalModal from "./EditPhysicalModal";
import AdjustmentModal from "./AdjustmentModal";

export default function PeriodDetails({ periodId, onBack }) {

    const [period, setPeriod] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState("line_items");
    const [lineItems, setLineItems] = useState([]);
    const [loadingLineItems, setLoadingLineItems] = useState(false);
    const [flaggedOnly, setFlaggedOnly] = useState(false);
    const [initializing, setInitializing] = useState(false);

    const [physicalCounts, setPhysicalCounts] = useState([]);
    const [loadingPhysical, setLoadingPhysical] = useState(false);
    const [showPhysicalModal, setShowPhysicalModal] = useState(false);
    const [finalizing, setFinalizing] = useState(false);
    const [isFinalized, setIsFinalized] = useState(false);

    const [showEditModal, setShowEditModal] = useState(false);
    const [selectedLineItem, setSelectedLineItem] = useState(null);
    

    // 🔹 Adjustments State
    const [adjustments, setAdjustments] = useState([]);
    const [loadingAdjustments, setLoadingAdjustments] = useState(false);
    const [showAdjustmentModal, setShowAdjustmentModal] = useState(false);

    // 🔹 Summary State
    const [summaryData, setSummaryData] = useState(null);
    const [loadingSummary, setLoadingSummary] = useState(false);

    // 🔹 Workflow Action Loading
    const [actionLoading, setActionLoading] = useState(false);

    // 🔹 Export Loading
    const [exportLoading, setExportLoading] = useState(false);
    
    const fetchPeriod = async () => {
        try {
            const res = await api.get(`/reconciliation/periods/${periodId}`);
            if (res.data.success) {
                const data = res.data.data;
                setPeriod(data);

                // Detect finalized state
                if (data.total_physical_closing_value > 0) {
                    setIsFinalized(true);
                }
            }
        } catch (error) {
            toast.error("Failed to load period details");
        } finally {
            setLoading(false);
        }
    };

    const fetchLineItems = async () => {
        try {
            setLoadingLineItems(true);

            const res = await api.get(
                `/reconciliation/periods/${periodId}/line-items`,
                {
                    params: {
                        flagged_only: flaggedOnly,
                    },
                }
            );

            if (res.data.success) {
                setLineItems(res.data.data || []);
            }
        } catch (error) {
            toast.error("Failed to load line items");
        } finally {
            setLoadingLineItems(false);
        }
    };

    const handleInitialize = async () => {
        try {
            setInitializing(true);

            const res = await api.post(
                `/reconciliation/periods/${periodId}/initialize`
            );

            if (res.data.success) {
                toast.success(res.data.message);

                // Update period data with new response
                setPeriod(res.data.data);

                // Reload line items automatically
                if (activeTab === "line_items") {
                    fetchLineItems();
                }
            }
        } catch (error) {
            toast.error("Failed to initialize period");
        } finally {
            setInitializing(false);
        }
    };

    const fetchPhysicalCounts = async () => {
        try {
            setLoadingPhysical(true);

            const res = await api.get(
                `/reconciliation/periods/${periodId}/physical-counts`,
                {
                    params: {
                        count_type: "closing",
                    },
                }
            );

            if (res.data.success) {
                setPhysicalCounts(res.data.data || []);
            }
        } catch (error) {
            toast.error("Failed to load physical counts");
        } finally {
            setLoadingPhysical(false);
        }
    };

    const handleFinalize = async () => {
        try {
            setFinalizing(true);

            const res = await api.post(
                `/reconciliation/periods/${periodId}/finalize-physical-count`
            );

            if (res.data.success) {
                toast.success("Physical count finalized");

                setIsFinalized(true); // 👈 IMPORTANT

                await fetchLineItems();
                await fetchPeriod();
            }
        } catch (error) {
            toast.error("Failed to finalize physical count");
        } finally {
            setFinalizing(false);
        }
    };

    const fetchAdjustments = async () => {
        try {
            setLoadingAdjustments(true);

            const res = await api.get(
                `/reconciliation/periods/${periodId}/adjustments`
            );

            if (res.data.success) {
                setAdjustments(res.data.data || []);
            }
        } catch (error) {
            toast.error("Failed to load adjustments");
        } finally {
            setLoadingAdjustments(false);
        }
    };

    const fetchSummary = async () => {
        try {
            setLoadingSummary(true);

            const res = await api.get(
                `/reconciliation/periods/${periodId}/summary`
            );

            if (res.data.success) {
                setSummaryData(res.data.data);
            }
        } catch (error) {
            toast.error("Failed to load summary");
        } finally {
            setLoadingSummary(false);
        }
    };


    // 🔹 Submit For Approval
    const handleSubmit = async () => {
        try {
            setActionLoading(true);

            const res = await api.post(
                `/reconciliation/periods/${periodId}/submit`,
                { notes: "Submitted for approval" }
            );

            if (res.data.success) {
                toast.success(res.data.message);
                setPeriod(res.data.data);
            }
        } catch (error) {
            const message =
                error?.response?.data?.detail ||
                "Submission failed";

            toast.error(message);
        } finally {
            setActionLoading(false);
        }
    };

    // 🔹 Approve
    const handleApprove = async () => {
        try {
            setActionLoading(true);

            const res = await api.post(
                `/reconciliation/periods/${periodId}/approve`,
                { notes: "Approved by manager" }
            );

            if (res.data.success) {
                toast.success(res.data.message);
                setPeriod(res.data.data);
                fetchLineItems();
            }
        } catch (error) {
            toast.error("Approval failed");
        } finally {
            setActionLoading(false);
        }
    };

    // 🔹 Reject
    const handleReject = async () => {
        try {
            setActionLoading(true);

            const res = await api.post(
                `/reconciliation/periods/${periodId}/reject`,
                { rejection_reason: "Variance needs revision" }
            );

            if (res.data.success) {
                toast.success("Reconciliation rejected");
                setPeriod(res.data.data);
            }
        } catch (error) {
            toast.error("Rejection failed");
        } finally {
            setActionLoading(false);
        }
    };

    // 🔹 Close Period (Only if Approved)
    const handleClose = async () => {
        try {
            setActionLoading(true);

            const res = await api.post(
                `/reconciliation/periods/${periodId}/close`
            );

            if (res.data.success) {
                toast.success(res.data.message);
                setPeriod(res.data.data);
            }
        } catch (error) {
            toast.error("Close failed");
        } finally {
            setActionLoading(false);
        }
    };

    const handleExportExcel = async () => {
        try {
            setExportLoading(true);

            const res = await api.get(
                `/reconciliation/periods/${periodId}/export/excel`,
                { responseType: "blob" }   // VERY IMPORTANT
            );

            // Create download link
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement("a");
            link.href = url;

            link.setAttribute(
                "download",
                `reconciliation_${period.period_year}_${period.period_month}.xlsx`
            );

            document.body.appendChild(link);
            link.click();
            link.remove();

        } catch (error) {
            toast.error("Failed to export Excel");
        } finally {
            setExportLoading(false);
        }
    };

    const handleExportPDF = async () => {
        try {
            setExportLoading(true);

            const res = await api.get(
                `/reconciliation/periods/${periodId}/export/pdf`,
                { responseType: "blob" }   // IMPORTANT
            );

            const blob = new Blob([res.data], { type: "text/html" });

            const url = window.URL.createObjectURL(blob);
            const link = document.createElement("a");

            link.href = url;
            link.setAttribute(
                "download",
                `reconciliation_${period.period_year}_${period.period_month}.html`
            );

            document.body.appendChild(link);
            link.click();
            link.remove();

        } catch (error) {
            toast.error("Failed to export PDF");
        } finally {
            setExportLoading(false);
        }
    };

    useEffect(() => {
        fetchPeriod();
    }, [periodId]);

    useEffect(() => {
        if (activeTab === "line_items") {
            fetchLineItems();
        }
    }, [activeTab, flaggedOnly]);

    useEffect(() => {
        if (activeTab === "physical") {
            fetchPhysicalCounts();
        }
    }, [activeTab]);

    useEffect(() => {
        if (activeTab === "adjustments") {
            fetchAdjustments();
        }
    }, [activeTab]);

    useEffect(() => {
        if (activeTab === "summary") {
            fetchSummary();
        }
    }, [activeTab]);

    if (loading) {
        return (
            <div className="p-6 dark:bg-gray-900 min-h-screen text-gray-800 dark:text-white">
                Loading...
            </div>
        );
    }

    if (!period) return null;

    return (
        <div className="p-6 min-h-screen bg-gray-50 dark:bg-gray-900 transition">

            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <div>
                    <button
                        onClick={onBack}
                        className="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-white"
                    >
                        ← Back
                    </button>

                    <h2 className="text-2xl font-bold mt-2 text-gray-800 dark:text-white">
                        {period.period_label}
                    </h2>

                    <span
                        className={`mt-2 inline-block px-3 py-1 rounded-full text-xs font-medium ${period.status === "draft"
                                ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300"
                                : period.status === "approved"
                                    ? "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300"
                                    : "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300"
                            }`}
                    >
                        {period.status}
                    </span>
                </div>
               
                {/*  ACTION BUTTONS */}
                <div className="flex gap-3 items-center">

                    {/* EXPORT BUTTONS */}
                    {period.status !== "draft" && period.status !== "in_progress" && (
                        <>
                            <button
                                onClick={handleExportExcel}
                                disabled={exportLoading}
                                className="px-4 py-2 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white"
                            >
                                {exportLoading ? "Exporting..." : "Export Excel"}
                            </button>

                            <button
                                onClick={handleExportPDF}
                                disabled={exportLoading}
                                className="px-4 py-2 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white"
                            >
                                {exportLoading ? "Exporting..." : "Export PDF"}
                            </button>
                        </>
                    )}


                {period.status === "draft" && (
                    <button
                        onClick={handleInitialize}
                        disabled={initializing}
                        className="px-4 py-2 rounded-md bg-yellow-500 hover:bg-yellow-600 text-white"
                    >
                        {initializing ? "Initializing..." : "Initialize"}
                    </button>
                )}

                {period.status === "in_progress" && (
                    <button
                        onClick={handleSubmit}
                        disabled={actionLoading}
                        className="px-4 py-2 rounded-md bg-blue-600 hover:bg-blue-700 text-white"
                    >
                        {actionLoading ? "Submitting..." : "Submit"}
                    </button>
                )}

                {period.status === "pending_approval" && (
                    <>
                        <button
                            onClick={handleApprove}
                            disabled={actionLoading}
                            className="px-4 py-2 rounded-md bg-green-600 hover:bg-green-700 text-white"
                        >
                            Approve
                        </button>

                        <button
                            onClick={handleReject}
                            disabled={actionLoading}
                            className="px-4 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white"
                        >
                            Reject
                        </button>
                    </>
                )}

                {period.status === "approved" && (
                    <button
                        onClick={handleClose}
                        disabled={actionLoading}
                        className="px-4 py-2 rounded-md bg-purple-600 hover:bg-purple-700 text-white"
                    >
                        Close Period
                    </button>
                    )}
                    </div>
            </div>
            {period.status === "in_progress" && period.rejection_reason && (
                <div className="mb-6 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 p-4 rounded-lg">
                    <strong>Rejected:</strong> {period.rejection_reason}
                </div>
            )}

            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-5 mb-8">
                <StatCard title="Start Date" value={period.period_start_date} />
                <StatCard title="End Date" value={period.period_end_date} />
                <StatCard title="Variance %" value={period.variance_threshold_pct + "%"} />
                <StatCard
                    title="Total Variance"
                    value={`₹ ${Number(period.total_variance_value || 0).toFixed(2)}`}
                />
            </div>

            {/* Tabs */}
            <div className="flex gap-4 mb-6 border-b border-gray-200 dark:border-gray-700">
                {[
                    { key: "line_items", label: "Line Items" },
                    { key: "physical", label: "Physical Counts" },
                    { key: "adjustments", label: "Adjustments" },
                    { key: "summary", label: "Summary" },
                ].map((tab) => (
                    <button
                        key={tab.key}
                        onClick={() => setActiveTab(tab.key)}
                        className={`pb-3 px-3 text-sm font-medium transition ${activeTab === tab.key
                                ? "border-b-2 border-yellow-500 text-yellow-600 dark:text-yellow-400"
                                : "text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-white"
                            }`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content Placeholder */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-md p-6 border border-gray-200 dark:border-gray-700 min-h-[300px]">
                {activeTab === "line_items" && (
                    <div>

                        {/* Flagged Filter Toggle */}
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
                                Reconciliation Line Items
                            </h3>
                        </div>

                        {/* Table */}
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm border-t border-gray-200 dark:border-gray-700">
                                <thead className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
                                    <tr>
                                        <th className="p-3 text-left">Item</th>
                                        <th className="p-3 text-left">Opening</th>
                                        <th className="p-3 text-left">Purchases</th>
                                        <th className="p-3 text-left">Consumption</th>
                                        <th className="p-3 text-left">Wastage</th>
                                        <th className="p-3 text-left">Adjustment</th>
                                        <th className="p-3 text-left">Theoretical</th>
                                        <th className="p-3 text-left">Physical</th>
                                        <th className="p-3 text-left">Variance</th>
                                        <th className="p-3 text-left">Status</th>
                                        <th className="p-3 text-left">Edit</th>
                                    </tr>
                                </thead>

                                <tbody className="text-gray-700 dark:text-gray-300">
                                    {loadingLineItems ? (
                                        <tr>
                                            <td colSpan="8" className="text-center p-6">
                                                Loading...
                                            </td>
                                        </tr>
                                    ) : lineItems.length === 0 ? (
                                        <tr>
                                            <td colSpan="8" className="text-center p-6">
                                                No line items found
                                            </td>
                                        </tr>
                                    ) : (
                                        lineItems.map((item) => (
                                            <tr
                                                key={item.id}
                                                className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                                            >
                                                <td className="p-3 font-medium">
                                                    {item.item_name}
                                                </td>

                                                <td className="p-3">{item.opening_quantity ?? 0}</td>
                                                <td className="p-3">{item.purchases_quantity ?? 0}</td>
                                                <td className="p-3">{item.consumption_quantity ?? 0}</td>
                                                <td className="p-3">{item.wastage_quantity ?? 0}</td>
                                                <td className={`p-3 ${item.adjustment_quantity > 0
                                                        ? "text-blue-600 font-semibold"
                                                        : ""
                                                    }`}>
                                                    {item.adjustment_quantity ?? 0}
                                                </td>
                                                <td className="p-3 font-medium">
                                                    {item.theoretical_closing_quantity ?? 0}
                                                </td>

                                                <td className="p-3">
                                                    {item.physical_closing_quantity !== null
                                                        ? item.physical_closing_quantity
                                                        : "-"}
                                                </td>

                                                <td
                                                    className={`p-3 font-semibold ${item.physical_closing_quantity !== null &&
                                                            item.variance_status === "exceeded_threshold"
                                                            ? "text-red-600 dark:text-red-400"
                                                            : item.physical_closing_quantity !== null
                                                                ? "text-green-600 dark:text-green-400"
                                                                : ""
                                                        }`}
                                                >
                                                    {item.physical_closing_quantity !== null
                                                        ? item.variance_quantity
                                                        : "-"}
                                                </td>

                                                <td className="p-3">
                                                    {item.physical_closing_quantity !== null ? (
                                                        <span
                                                            className={`px-2 py-1 rounded-full text-xs font-semibold ${item.variance_status === "exceeds_threshold"
                                                                    ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
                                                                    : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300"
                                                                }`}
                                                        >
                                                            {item.variance_status === "exceeds_threshold"
                                                                ? "Exceeded"
                                                                : "Within Limit"}
                                                        </span>
                                                    ) : (
                                                        "-"
                                                    )}
                                                </td>
                                                <td className="p-3">
                                                    {period.status === "in_progress" ? (
                                                        <button
                                                            onClick={() => {
                                                                setSelectedLineItem(item);
                                                                setShowEditModal(true);
                                                            }}
                                                            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 cursor-pointer"
                                                        >
                                                            ✏️
                                                        </button>
                                                    ) : (
                                                        "-"
                                                    )}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {activeTab === "physical" && (
                    <div>

                        {/* Header Section */}
                        <div className="flex justify-between items-center mb-4 ">
                            <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
                                Physical Counts
                            </h3>

                            <div className="flex gap-3">

                                <button
                                    onClick={() => setShowPhysicalModal(true)}
                                    disabled={
                                        period.status !== "in_progress" ||
                                        finalizing ||
                                        isFinalized
                                    }
                                    className={`px-4 py-2 rounded-md text-white
        ${period.status !== "in_progress" || isFinalized
                                            ? "bg-gray-400 cursor-not-allowed"
                                            : "bg-yellow-500 hover:bg-yellow-600"}
    `}
                                >
                                    + Add Physical Count
                                </button>

                                <button
                                    onClick={handleFinalize}
                                    disabled={
                                        finalizing ||
                                        physicalCounts.length === 0 ||
                                        period.status !== "in_progress" ||
                                        isFinalized
                                    }
                                    className={`px-4 py-2 rounded-md text-white
        ${finalizing ||
                                            physicalCounts.length === 0 ||
                                            period.status !== "in_progress" ||
                                            isFinalized
                                            ? "bg-gray-400 cursor-not-allowed"
                                            : "bg-green-600 hover:bg-green-700"}
    `}
                                >
                                    {finalizing ? "Finalizing..." : "Finalize"}
                                </button>

                            </div>
                        </div>

                        {/* Table */}
                        <div className="overflow-x-auto text-gray-800 dark:text-white">
                            <table className="w-full text-sm border-t border-gray-200 dark:border-gray-700">
                                <thead className="bg-gray-100 dark:bg-gray-700">
                                    <tr>
                                        <th className="p-3 text-left">Item</th>
                                        <th className="p-3 text-left">Counted Qty</th>
                                        <th className="p-3 text-left">Unit</th>
                                        <th className="p-3 text-left">Notes</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    {loadingPhysical ? (
                                        <tr>
                                            <td colSpan="4" className="text-center p-6">
                                                Loading...
                                            </td>
                                        </tr>
                                    ) : physicalCounts.length === 0 ? (
                                        <tr>
                                            <td colSpan="4" className="text-center p-6">
                                                No physical counts submitted yet
                                            </td>
                                        </tr>
                                    ) : (
                                        physicalCounts.map((count) => (
                                            <tr
                                                key={count.id}
                                                className="border-t border-gray-200 dark:border-gray-700"
                                            >
                                                <td className="p-3">
                                                    {count.item_name}
                                                </td>
                                                <td className="p-3">
                                                    {count.counted_quantity}
                                                </td>
                                                <td className="p-3">
                                                    {count.unit}
                                                </td>
                                                <td className="p-3">
                                                    {count.notes || "-"}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {activeTab === "adjustments" && (
                    <div>

                        {/* Header */}
                        <div className="flex justify-between items-center mb-4">
                            <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
                                Manual Adjustments
                            </h3>

                            <button
                                onClick={() => setShowAdjustmentModal(true)}
                                disabled={period.status !== "in_progress"}
                                className={`px-4 py-2 rounded-md text-white ${period.status !== "in_progress"
                                        ? "bg-gray-400 cursor-not-allowed"
                                        : "bg-yellow-500 hover:bg-yellow-600"
                                    }`}
                            >
                                + Add Adjustment
                            </button>
                        </div>

                        {/* Table */}
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm border-t border-gray-200 dark:border-gray-700">
                                <thead className="bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-white">
                                    <tr>
                                        <th className="p-3 text-left">Item</th>
                                        <th className="p-3 text-left">Reason</th>
                                        <th className="p-3 text-left">Quantity</th>
                                        <th className="p-3 text-left">Unit Cost</th>
                                        <th className="p-3 text-left">Value</th>
                                        <th className="p-3 text-left">Notes</th>
                                        <th className="p-3 text-left">Created At</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    {loadingAdjustments ? (
                                        <tr>
                                            <td colSpan="7" className="text-center p-6">
                                                Loading...
                                            </td>
                                        </tr>
                                    ) : adjustments.length === 0 ? (
                                        <tr>
                                                <td colSpan="7" className="text-center p-6 text-gray-800 dark:text-white">
                                                No adjustments recorded
                                            </td>
                                        </tr>
                                    ) : (
                                        adjustments.map((adj) => (
                                            <tr
                                                key={adj.id}
                                                className="border-t border-gray-200 dark:border-gray-700"
                                            >
                                                <td className="p-3 font-medium">
                                                    {adj.item_name}
                                                </td>
                                                <td className="p-3">
                                                    {adj.reason}
                                                </td>
                                                <td className="p-3">
                                                    {adj.quantity_adjusted}
                                                </td>
                                                <td className="p-3">
                                                    ₹ {adj.unit_cost}
                                                </td>
                                                <td className="p-3 font-semibold">
                                                    ₹ {adj.value_adjusted}
                                                </td>
                                                <td className="p-3">
                                                    {adj.notes || "-"}
                                                </td>
                                                <td className="p-3">
                                                    {new Date(adj.created_at).toLocaleDateString()}
                                                </td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {activeTab === "summary" && (
                    <div>
                        {loadingSummary ? (
                            <div className="text-center py-10 text-gray-500 dark:text-gray-400">
                                Loading summary...
                            </div>
                        ) : !summaryData ? (
                            <div className="text-center py-10 text-gray-500 dark:text-gray-400">
                                No summary available
                            </div>
                        ) : (
                            <div className="space-y-8">

                                {/* ===== Period Info ===== */}
                                <div>
                                    <h3 className="text-xl font-semibold text-gray-800 dark:text-white mb-4">
                                        Monthly Overview
                                    </h3>

                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <StatCard
                                            title="Costing Method"
                                            value={summaryData.costing_method}
                                        />
                                        <StatCard
                                            title="Variance Threshold"
                                            value={`${summaryData.variance_threshold_pct}%`}
                                        />
                                        <StatCard
                                            title="Total Line Items"
                                            value={summaryData.total_line_items}
                                        />
                                        <StatCard
                                            title="Flagged Items"
                                            value={summaryData.flagged_items_count}
                                        />
                                    </div>
                                </div>

                                {/* ===== Financial Summary ===== */}
                                <div>
                                    <h3 className="text-xl font-semibold text-gray-800 dark:text-white mb-4">
                                        Financial Summary
                                    </h3>

                                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                                        <StatCard
                                            title="Opening Value"
                                            value={`₹ ${summaryData.summary.total_opening_value}`}
                                        />
                                        <StatCard
                                            title="Purchases Value"
                                            value={`₹ ${summaryData.summary.total_purchases_value}`}
                                        />
                                        <StatCard
                                            title="Wastage Value"
                                            value={`₹ ${summaryData.summary.total_wastage_value}`}
                                        />
                                        <StatCard
                                            title="Adjustment Value"
                                            value={`₹ ${summaryData.summary.total_adjustment_value}`}
                                        />
                                        <StatCard
                                            title="Theoretical Closing"
                                            value={`₹ ${summaryData.summary.total_theoretical_closing_value}`}
                                        />
                                        <StatCard
                                            title="Physical Closing"
                                            value={`₹ ${summaryData.summary.total_physical_closing_value}`}
                                        />
                                        <StatCard
                                            title="Total Variance"
                                            value={`₹ ${summaryData.summary.total_variance_value}`}
                                        />
                                        <StatCard
                                            title="Variance %"
                                            value={`${summaryData.summary.total_variance_pct}%`}
                                        />
                                    </div>
                                </div>

                                {/* ===== Flagged Items Table ===== */}
                                <div>
                                    <h3 className="text-xl font-semibold text-gray-800 dark:text-white mb-4">
                                        Flagged Items
                                    </h3>

                                            <div className="overflow-x-auto text-gray-800 dark:text-white">
                                        <table className="w-full text-sm border-t border-gray-200 dark:border-gray-700">
                                            <thead className="bg-gray-100 dark:bg-gray-700">
                                                <tr>
                                                    <th className="p-3 text-left">Item</th>
                                                    <th className="p-3 text-left">Variance Qty</th>
                                                    <th className="p-3 text-left">Variance Value</th>
                                                    <th className="p-3 text-left">Variance %</th>
                                                    <th className="p-3 text-left">Status</th>
                                                </tr>
                                            </thead>

                                            <tbody>
                                                {summaryData.flagged_items.map((item) => (
                                                    <tr
                                                        key={item.id}
                                                        className="border-t border-gray-200 dark:border-gray-700"
                                                    >
                                                        <td className="p-3 font-medium">
                                                            {item.item_name}
                                                        </td>
                                                        <td className="p-3">
                                                            {item.variance_quantity}
                                                        </td>
                                                        <td className="p-3">
                                                            ₹ {item.variance_value}
                                                        </td>
                                                        <td className="p-3">
                                                            {item.variance_pct.toFixed(2)}%
                                                        </td>
                                                        <td className="p-3">
                                                            <span className="px-2 py-1 rounded-full text-xs bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300">
                                                                Exceeded
                                                            </span>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                            </div>
                        )}
                    </div>
                )}

            </div>
            {showPhysicalModal && (
                <PhysicalCountModal
                    periodId={periodId}
                    lineItems={lineItems}
                    onClose={() => setShowPhysicalModal(false)}
                    onSuccess={() => {
                        fetchPhysicalCounts();
                        fetchLineItems();
                        setShowPhysicalModal(false);
                    }}
                />
            )}

            {showEditModal && selectedLineItem && (
                <EditPhysicalModal
                    periodId={periodId}
                    lineItem={selectedLineItem}
                    onClose={() => {
                        setShowEditModal(false);
                        setSelectedLineItem(null);
                    }}
                    onSuccess={() => {
                        fetchLineItems();
                        setShowEditModal(false);
                        setSelectedLineItem(null);
                    }}
                />
            )}  

            {showAdjustmentModal && (
                <AdjustmentModal
                    periodId={periodId}
                    lineItems={lineItems}
                    onClose={() => setShowAdjustmentModal(false)}
                    onSuccess={() => {
                        fetchAdjustments();
                        fetchLineItems();
                        fetchPeriod();
                        setShowAdjustmentModal(false);
                    }}
                />
            )}
        </div>
    );
}

function StatCard({ title, value }) {
    return (
        <div className="bg-white dark:bg-gray-800 p-5 rounded-xl shadow-md border border-gray-200 dark:border-gray-700">
            <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
            <h3 className="text-lg font-semibold mt-2 text-gray-800 dark:text-white">
                {value}
            </h3>
        </div>
    );
}