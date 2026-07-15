import { useEffect, useState } from "react";
import api from "../../api/axios";
import { FiTrash2, FiUpload } from "react-icons/fi";
import UploadSpoilageModal from "./UploadSpoilageModal";

export default function NonPerishableWasteTab() {
    const [records, setRecords] = useState([]);
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(false);
    const [showModal, setShowModal] = useState(false);

    const [startDate, setStartDate] = useState("");
    const [endDate, setEndDate] = useState("");

    const [rowsPerPage, setRowsPerPage] = useState(5);
    const [currentPage, setCurrentPage] = useState(1);

    const [filterType, setFilterType] = useState("daily");
    const [selectedDate, setSelectedDate] = useState(
        new Date().toISOString().split("T")[0]
    );

    //  Fetch Data
    const fetchData = async () => {
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
                perishable_type: "non_perishable",
                start_date,
                end_date
            };

            const res = await api.get(
                "/wastage/get-wastage/perishable-non-perishable",
                { params }
            );

            const block = res.data.data?.find(
                (d) => d.perishable_type === "non_perishable"
            );

            setSummary(block || null);
            setRecords(block?.records || []);
            setCurrentPage(1);

        } catch (err) {
            console.error("Failed to fetch non-perishable data", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, [filterType, selectedDate]);

    useEffect(() => {
        console.log(
            records.map(r => ({
                item: r.item_name,
                category: r.category_name
            }))
        );
    }, [records]);

    const handleFilter = () => {
        fetchData();
    };

    const expiredCount = records.filter(
        (r) => r.wastage_reason?.toLowerCase() === "expiry"
    ).length;

     const spoilageCount = records.filter((r) =>
         ["break", "damage", "contamination", "spillage"].includes(
             r.wastage_reason?.toLowerCase()
         )
     ).length;

    // Pagination
    const totalPages = Math.ceil(records.length / rowsPerPage);
    const startIndex = (currentPage - 1) * rowsPerPage;
    const paginatedData = records.slice(
        startIndex,
        startIndex + rowsPerPage
    );

    return (
        <div className="px-4 py-4 space-y-6 text-gray-900 dark:text-gray-100">

            <div className="flex flex-wrap items-center gap-3 px-1 pb-2">

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

                <input
                    type="date"
                    value={selectedDate}
                    onChange={(e) => setSelectedDate(e.target.value)}
                    className=" date-input px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700
        bg-white dark:bg-[#020617] text-gray-700 dark:text-gray-300 text-sm
        outline-none focus:ring-2 focus:ring-orange-400"
                />

            </div>

            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

                <StatCard
                    title="Item Waste"
                    value={summary?.total_records || 0}
                />

                <StatCard
                    title="Expired Item"
                    value={expiredCount}
                />

                {/* <StatCard
                    title="Spoilage Item"
                    value={spoilageCount}
                /> */}

                <StatCard
                    title="Total Cost"
                    value={`₹${summary?.total_cost_wasted || 0}`}
                />

            </div>

            {/* Table */}
            {/* Table + Pagination Wrapper */}
            <div className="border rounded-lg bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800 overflow-hidden">

                {/* Table Scroll Area */}
                <div className="overflow-x-auto">
                    <table className="min-w-[900px] w-full">
                        <thead className="bg-gray-50 dark:bg-gray-800">
                            <tr>
                                <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200"> Wastage Item</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Quantity</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Reason</th>
                                <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Date</th>
                                {/* <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Delete</th> */}
                            </tr>
                        </thead>

                        <tbody>
                            {loading ? (
                                <tr>
                                    <td colSpan="5" className="text-center py-6 text-gray-600 dark:text-gray-400">
                                        Loading...
                                    </td>
                                </tr>
                            ) : paginatedData.length === 0 ? (
                                <tr>
                                    <td colSpan="5" className="text-center py-6 text-gray-600 dark:text-gray-400">
                                            No non-perishable waste records found for selected date
                                    </td>
                                </tr>
                            ) : (
                                paginatedData.map((item) => (
                                    <tr
                                        key={item.wastage_id}
                                        className="border-t border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                                    >
                                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                                            {item.item_name}
                                        </td>

                                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                                            <span className="font-medium">
                                                {item.quantity_wasted}
                                            </span>
                                            <span className="text-gray-900 dark:text-gray-300 ml-1">
                                                {item.unit || ""}
                                            </span>
                                        </td>

                                        <td className="px-4 py-3 text-sm capitalize text-gray-700 dark:text-gray-300">
                                            {item.wastage_reason?.replaceAll("_", " ") || "-"}
                                        </td>

                                        <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                                            {new Date(item.wastage_date).toLocaleDateString()}
                                        </td>

                                        {/* <td className="px-4 py-3 text-sm">
                                            <button className="text-red-600">
                                                <FiTrash2 />
                                            </button>
                                        </td> */}
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Pagination INSIDE SAME CONTAINER */}
                <div className="flex justify-end items-center gap-4 px-4 py-4 border-t border-gray-200 dark:border-gray-800">
                    <div className="text-sm text-gray-700 dark:text-gray-300">
                        Rows per page
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

                    <div className="text-sm text-gray-700 dark:text-gray-300">
                        Page {currentPage} of {totalPages || 1}
                    </div>

                    <button
                        disabled={currentPage === 1}
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        className="px-3 py-1 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded disabled:opacity-40"
                    >
                        ←
                    </button>

                    <button
                        disabled={currentPage === totalPages}
                        onClick={() =>
                            setCurrentPage((p) =>
                                Math.min(totalPages, p + 1)
                            )
                        }
                        className="px-3 py-1 border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded disabled:opacity-40"
                    >
                        →
                    </button>
                </div>

            </div>
            <UploadSpoilageModal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                onSuccess={fetchData}
            />
        </div>
    );
}

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