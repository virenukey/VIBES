import { useEffect, useState } from "react";
import api from "../../api/axios";
import AddDishWastageModal from "./AddDishWastageModal";

export default function DishWastageTab() {
    const [totalDishRecords, setTotalDishRecords] = useState(0);
    const [totalDishCost, setTotalDishCost] = useState(0);
    const [monthlyDishCost, setMonthlyDishCost] = useState(0);
    const [spoilageCount, setSpoilageCount] = useState(0);
    const [reasonBreakdown, setReasonBreakdown] = useState([]);
    const [showModal, setShowModal] = useState(false);
    const [records, setRecords] = useState([]);
    const [selectedRecord, setSelectedRecord] = useState(null);

    const fetchDishStats = async () => {
        try {
            const res = await api.get("/wastage/unsold-dishes");

            const data = res.data;

            setTotalDishRecords(data.total_records || 0);
            setTotalDishCost(data.total_cost_wasted || 0);
            setMonthlyDishCost(data.total_cost_wasted || 0);
            setSpoilageCount(0);

            setReasonBreakdown([
                {
                    reason: "unsold_dish",
                    record_count: data.total_records || 0,
                    total_cost: data.total_cost_wasted || 0
                }
            ]);

            setRecords(data.data || []);

        } catch (error) {
            console.error("Failed to fetch dish wastage stats", error);
        }
    };

    useEffect(() => {
        fetchDishStats();
    }, []);

    return (
        <div className="px-4 py-4 space-y-6 text-gray-900 dark:text-gray-100">
            <button
                onClick={() => setShowModal(true)}
                className="px-4 py-2 bg-yellow-400 rounded-md"
            >
                Add Dish Waste
            </button>
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">

                <StatCard title="Total Dish Records" value={totalDishRecords} />
                <StatCard
                    title="Total Dish Cost"
                    value={`₹${Number(totalDishCost).toFixed(2)}`}
                />
                <StatCard
                    title="This Month Dish Cost"
                    value={`₹${Number(monthlyDishCost).toFixed(2)}`}
                />                <StatCard title="Spoilage Dish Count" value={spoilageCount} />

            </div>

            {/* Reason Breakdown */}
            {/* <div className="bg-white dark:bg-gray-900 border rounded-lg p-4">
                <h3 className="font-semibold mb-4">Reason Breakdown</h3>

                {reasonBreakdown.length === 0 ? (
                    <p className="text-sm text-gray-500">No data available</p>
                ) : (
                    <div className="space-y-2">
                        {reasonBreakdown.map((reason, index) => (
                            <div
                                key={index}
                                className="flex justify-between text-sm border-b py-2"
                            >
                                <span className="capitalize">
                                    {reason.reason.replace("_", " ")}
                                </span>
                                <span>
                                    {reason.record_count} records | ₹{reason.total_cost}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div> */}

            {/* Dish Wastage Table */}
            <div className="overflow-x-auto border rounded-lg bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-800">
                <table className="min-w-[900px] w-full  ">
                <thead className="bg-gray-50 dark:bg-gray-800">                        <tr>
                            <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Dish</th>
                            <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Quantity</th>
                            <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Total Cost</th>
                            <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Date</th>
                            <th className="px-4 py-3 text-left text-sm text-gray-800 dark:text-gray-200">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {records.map((item) => (
                            <tr key={item.wastage_id} className="border-t border-gray-200 dark:border-gray-800">
                                <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200 ">
                                    {item.dish_name}
                                </td>
                                <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200">
                                    {item.quantity_unsold}
                                </td>
                                <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200">
                                    ₹{Number(item.total_dish_cost).toFixed(2)}
                                </td>
                                <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200">
                                    {new Date(item.wastage_date).toLocaleDateString()}
                                </td>
                                <td className="px-4 py-3 text-sm text-gray-800 dark:text-gray-200 text-gray-800 dark:text-gray-200">
                                    <button
                                        onClick={() => setSelectedRecord(item)}
                                        className="text-blue-600 hover:underline"
                                    >
                                        View Breakdown
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {selectedRecord && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50  ">
                    <div className="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-6 rounded-lg w-[600px] max-h-[80vh] overflow-y-auto">
                        <h2 className="text-lg font-semibold mb-4">
                            Ingredient Breakdown - {selectedRecord.dish_name}
                        </h2>

                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-gray-200 dark:border-gray-800">                                    <th className="text-left py-2">Ingredient</th>
                                    <th className="text-left py-2 text-gray-800 dark:text-gray-200">Quantity</th>
                                    <th className="text-left py-2 text-gray-800 dark:text-gray-200">Cost</th>
                                </tr>
                            </thead>
                            <tbody>
                                {selectedRecord.ingredient_breakdown.map((ing) => (
                                    <tr key={ing.wastage_id} className="border-b border-gray-200 dark:border-gray-800">                                        <td className="py-2">
                                            {ing.inventory_item_name || "Unknown"}
                                        </td>
                                        <td className="py-2 text-gray-700 dark:text-gray-300">
                                            {ing.quantity_wasted} {ing.unit}
                                        </td>
                                        <td className="py-2 text-gray-700 dark:text-gray-300">
                                            ₹{Number(ing.cost_value).toFixed(2)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>

                        <div className="flex justify-end mt-4">
                            <button
                                onClick={() => setSelectedRecord(null)}
                                className="px-4 py-2 bg-yellow-400 rounded-md"
                            >
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            )}  

            <AddDishWastageModal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                onSuccess={fetchDishStats}
            />

            {/* View Button */}
            {/* <button className="px-6 py-2 bg-yellow-400 hover:bg-yellow-500 text-black rounded-md">
                View
            </button> */}

            

        </div>

        
    );
}


function StatCard({ title, value }) {
    return (
        <div className="bg-white dark:bg-gray-900 border rounded-lg p-4 shadow-sm">
            <p className="text-sm text-gray-500 dark:text-gray-400">{title}</p>
            <p className="text-2xl font-bold mt-2">{value}</p>
        </div>


    );
}