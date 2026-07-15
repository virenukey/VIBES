import { useEffect, useState } from "react";
import api from "../../api/axios";
import { FiUpload } from "react-icons/fi";
import UploadSpoilageModal from "./UploadSpoilageModal";

export default function PerishableWasteTab() {

    const [records, setRecords] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(false);
    const [showModal, setShowModal] = useState(false);

    const [rowsPerPage, setRowsPerPage] = useState(5);
    const [currentPage, setCurrentPage] = useState(1);

    const [startDate, setStartDate] = useState("");
    const [endDate, setEndDate] = useState("");

    const [filterType, setFilterType] = useState("daily");
    const getTodayDate = () => {
        const today = new Date();
        return today.toISOString().split("T")[0];
    };

    const [selectedDate, setSelectedDate] = useState(getTodayDate());
    /* ================= FETCH DATA ================= */
    const fetchSummary = async () => {
        try {

            setLoading(true);

            let start_date = null;
            let end_date = null;

            if (selectedDate) {

                const selected = new Date(selectedDate);

                // DAILY
                if (filterType === "daily") {
                    start_date = selectedDate + "T00:00:00";
                    end_date = selectedDate + "T23:59:59";
                }

                // WEEKLY
                if (filterType === "weekly") {

                    const firstDay = new Date(selected);
                    firstDay.setDate(selected.getDate() - selected.getDay());

                    const lastDay = new Date(firstDay);
                    lastDay.setDate(firstDay.getDate() + 6);

                    start_date = firstDay.toISOString().split("T")[0] + "T00:00:00";
                    end_date = lastDay.toISOString().split("T")[0] + "T23:59:59";
                }

                // MONTHLY
                if (filterType === "monthly") {

                    const year = selected.getFullYear();
                    const month = selected.getMonth();

                    const firstDay = new Date(year, month, 1);
                    const lastDay = new Date(year, month + 1, 0);

                    start_date = firstDay.toISOString().split("T")[0] + "T00:00:00";
                    end_date = lastDay.toISOString().split("T")[0] + "T23:59:59";
                }

            }

            const params = {
                perishable_type: "perishable",
                start_date,
                end_date
            };

            const res = await api.get(
                "/wastage/get-wastage/perishable-non-perishable",
                { params }
            );

            const data = res.data.data?.find(
                (item) => item.perishable_type === "perishable"
            );

            setSummary(data || null);
            setRecords(data?.records || []);
            setCurrentPage(1);

        } catch (err) {
            console.error("Failed to fetch perishable data", err);
        } finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        setCurrentPage(1);
        fetchSummary();
    }, [filterType, selectedDate]);

    const handleFilter = () => {
        fetchSummary();
    };

    /* ================= DERIVED STATS ================= */

    const expiredCount = records.filter(
        (r) => r.wastage_reason === "expiry"
    ).length;

    // const spoilageCount = records.filter((r) =>
    //     ["damage", "contamination", "spillage"].includes(r.wastage_reason)
    // ).length;

    /* ================= PAGINATION ================= */

    const totalPages = Math.ceil(records.length / rowsPerPage) || 1;

    const paginatedData = records.slice(
        (currentPage - 1) * rowsPerPage,
        currentPage * rowsPerPage
    );

    return (

        <div className="w-full bg-white dark:bg-[#0f172a] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm p-6 space-y-6">

            <div className="flex flex-wrap items-center gap-3 px-1 pb-2">

                {/* FILTER TYPE BUTTONS */}
                <div className="flex bg-gray-100 dark:bg-[#020617] p-1 rounded-full">

                    {["daily", "weekly", "monthly"].map((type) => (

                        <button
                            key={type}
                            onClick={() => setFilterType(type)}
                            className={`px-4 py-1.5 text-sm rounded-full font-medium transition
                ${filterType === type
                                    ? "bg-orange-500 text-white"
                                    : "text-gray-700 dark:text-gray-300"
                                }`}
                        >
                            {type.charAt(0).toUpperCase() + type.slice(1)}
                        </button>

                    ))}

                </div>

                {/* DATE INPUT */}
                <input
                    type="date"
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    className="date-input px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700
        bg-white dark:bg-[#020617] text-gray-700 dark:text-gray-300 text-sm
        outline-none focus:ring-2 focus:ring-orange-400"
                />

            </div>

            {/* ================= STATS ================= */}

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">

                <StatCard
                    title="Total Items"
                    value={summary?.total_records || 0}
                />

                <StatCard
                    title="Expired Items"
                    value={expiredCount}
                />

                {/* <StatCard
                    title="Spoilage Items"
                    value={spoilageCount}
                /> */}

                <StatCard
                    title="Total Cost"
                    value={`₹${summary?.total_cost_wasted || 0}`}
                />

            </div>

            {/* ================= TABLE ================= */}

            <div className="px-0">

                <div className="border border-gray-200 dark:border-gray-800 rounded-xl overflow-x-auto">

                    <table className="w-full min-w-[900px]">

                        {/* HEADER */}
                        <thead className="bg-gray-100 dark:bg-[#020617] border-b border-gray-200 dark:border-gray-700">
                            <tr>

                                <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                                    Wastage Item

                                </th>

                                <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                                    Quantity
                                </th>

                                <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                                    Cost
                                </th>

                                <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                                    Reason
                                </th>

                                <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300">
                                    Date
                                </th>

                            </tr>
                        </thead>

                        {/* BODY */}
                        <tbody>

                            {loading ? (
                                <tr>
                                    <td colSpan="5" className="text-center py-6 text-gray-500 dark:text-gray-400">
                                        Loading...
                                    </td>
                                </tr>
                            ) : paginatedData.length === 0 ? (
                                <tr>
                                        <td colSpan="5" className="text-center py-10 text-gray-500 dark:text-gray-400">
                                            <div className="flex flex-col items-center gap-2">
                                                <span> No perishable waste records found for selected date</span>
                                            </div>
                                        </td>
                                </tr>
                            ) : (

                                paginatedData.map((item) => (

                                    <tr
                                        key={item.wastage_id}
                                        className="border-t border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#020617] transition"
                                    >

                                        {/* ITEM */}
                                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                                            {item.item_name}
                                        </td>

                                        {/* QUANTITY */}
                                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                                            <span className="font-medium">
                                                {item.quantity_wasted}
                                            </span>
                                            <span className="text-gray-800 dark:text-gray-300 ml-1">
                                                {item.unit || ""}
                                            </span>
                                        </td>

                                        {/* COST */}
                                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                                            ₹{Number(item.cost_value || 0).toFixed(2)}
                                        </td>

                                        {/* REASON */}
                                        <td className="px-4 py-3 text-sm">
                                            <span className="px-2 py-1 text-xs rounded-full bg-red-100 dark:bg-red-500/20 text-red-600 dark:text-red-400 capitalize">
                                                {item.wastage_reason?.replaceAll("_", " ") || "-"}
                                            </span>
                                        </td>

                                        {/* DATE */}
                                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                                            {item.wastage_date
                                                ? new Date(item.wastage_date)
                                                    .toLocaleDateString("en-GB")
                                                    .replace(/\//g, "-")
                                                : "-"
                                            }
                                        </td>

                                    </tr>

                                ))

                            )}

                        </tbody>

                    </table>

                    {/* ================= PAGINATION ================= */}

                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-4 px-6 py-4 border-t border-gray-200 dark:border-gray-800">

                        <div className="flex items-center gap-2 text-sm">

                            <span className="font-medium text-gray-700 dark:text-gray-300">
                                Rows per page
                            </span>

                            <select
                                value={rowsPerPage}
                                onChange={(e) => {
                                    setRowsPerPage(Number(e.target.value));
                                    setCurrentPage(1);
                                }}
                                className="px-3 py-1 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300"
                            >
                                <option value={5}>5</option>
                                <option value={10}>10</option>
                                <option value={20}>20</option>
                            </select>

                        </div>

                        <div className="text-sm font-medium text-gray-700 dark:text-gray-300">
                            Page {currentPage} of {totalPages || 1}
                        </div>

                        <div className="flex gap-2">

                            <button
                                disabled={currentPage === 1}
                                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                                className="p-2 rounded-md border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                            >
                                ←
                            </button>

                            <button
                                disabled={currentPage === totalPages}
                                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                                className="p-2 rounded-md border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                            >
                                →
                            </button>

                        </div>

                    </div>

                </div>

            </div>
            {/* ================= MODAL ================= */}

            <UploadSpoilageModal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                onSuccess={fetchSummary}
            />

        </div>
    );
}

/* ================= STAT CARD ================= */

function StatCard({ title, value }) {
    return (
        <div className="bg-white dark:bg-[#020617] border border-gray-200 dark:border-gray-700 rounded-xl px-5 py-4 shadow-sm">
            <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mt-1">
                {value}
            </h2>
        </div>
    );
}