import { useState } from "react";
import PageHeader from "../PageHeader";
import OrderDishesTab from "./OrderDishesTab";
import OrderInProcessTab from "./OrderInProcessTab";
import OrderHistoryTab from "./OrderHistoryTab";

export default function OrderManagementTab() {
    const [activeTab, setActiveTab] = useState("dishes");

    return (
        <div className="w-full bg-white dark:bg-[#0f172a] rounded-xl border border-gray-200 dark:border-gray-800">
            <PageHeader
                title="Order Management"
                tabs={[
                    { key: "dishes", label: "Order Dishes" },
                    { key: "inprocess", label: "Order In Process" },
                    { key: "history", label: "Order History" },
                ]}
                activeTab={activeTab}
                setActiveTab={setActiveTab}
            />

            {/* Tab Content */}
            {activeTab === "dishes" && <OrderDishesTab />}
            {activeTab === "inprocess" && <OrderInProcessTab />}
            {activeTab === "history" && <OrderHistoryTab />}
        </div>
    );
}