import { useEffect, useState } from "react";
import api from "../../api/axios";
import { toast } from "react-toastify";
import PaymentModal from "./PaymentModal";
import CancelOrderModal from "./CancelOrderModal";
import PackagingModal from "./PackagingModal";

export default function OrderInProcessTab() {
    const [orders, setOrders] = useState([]);
    const [dishMap, setDishMap] = useState({});
    const [loading, setLoading] = useState(false);

    const [selectedOrder, setSelectedOrder] = useState(null);
    const [showPayment, setShowPayment] = useState(false);
    const [showCancelModal, setShowCancelModal] = useState(false);
    const [selectedOrderId, setSelectedOrderId] = useState(null);

    const [inventoryItems, setInventoryItems] = useState([]);
    const [showPackagingModal, setShowPackagingModal] = useState(false);
    const [selectedPackagingOrder, setSelectedPackagingOrder] = useState(null);
    

    useEffect(() => {
        fetchDishes();
        fetchOrders();
        fetchInventory();
    }, []);

    /* ================= FETCH ALL DISHES ================= */
    const fetchDishes = async () => {
        try {
            const res = await api.get("/dish/dishes");

            const dishes =
                Array.isArray(res.data)
                    ? res.data
                    : res.data.data || [];

            const map = {};

            dishes.forEach((dish) => {
                map[dish.id] = {
                    name: dish.name,
                    category: dish.type?.name,
                };
            });

            setDishMap(map);
        } catch (err) {
            console.error("Dish API Error:", err.response?.data || err.message);
        }
    };

    /* ================= FETCH ORDERS ================= */
    const fetchOrders = async () => {
        try {
            setLoading(true);

            const res = await api.get("/oders/");
            const orderList = res.data || [];
            const activeOrders = orderList.filter(
                (order) =>
                    !["COMPLETED", "CANCELLED", "REFUNDED"].includes(order.status)
            );

            const detailedOrders = await Promise.all(
                activeOrders.map(async (order) => {
                    const detailRes = await api.get(`/oders/${order.id}`);
                    return detailRes.data;
                })
            );

            setOrders(detailedOrders);
        } catch (err) {
            toast.error("Failed to fetch orders ❌");
        } finally {
            setLoading(false);
        }
    };

    const getNextAction = (order) => {
        const { status, order_type } = order;

        switch (status) {
            case "PENDING":
                return { label: "Confirm", type: "CONFIRM" };

            case "CONFIRMED":
                return { label: "Start Preparing", type: "PREPARE" };

            case "READY":
                if (order_type === "DINE_IN") {
                    return { label: "Serve", type: "STATUS", nextStatus: "SERVED" };
                }
                return { label: "Checkout", type: "CHECKOUT" };

            case "SERVED":
                return { label: "Checkout", type: "CHECKOUT" };

            default:
                return null;
        }
    };

    const updateStatus = async (orderId, newStatus) => {
        try {
            await api.patch(`/oders/${orderId}/status`, {
                status: newStatus,
                notes: "",
                cancellation_reason: "",
            });

            toast.success("Order status updated ");

            fetchOrders();
        } catch (err) {
            toast.error("Failed to update status ");
        }
    };

    const prepareOrder = async (orderId) => {
        try {
            const res = await api.post(`/oders/${orderId}/prepare`, {
                notes: "Kitchen preparation started",
            });

            const data = res.data;

            toast.success(
                `Prepared: ${data.items_prepared}, Cost: ₹${data.total_cost}`
            );

            if (data.warnings && data.warnings.length > 0) {
                toast.warning(data.warnings.join(", "));
            }

            fetchOrders();
        } catch (err) {
            const errorData = err.response?.data;

        
            if (errorData?.detail) {
                if (Array.isArray(errorData.detail)) {
                    toast.error(
                        errorData.detail.map((e) => e.msg).join(", ")
                    );
                } else {
                    toast.error(errorData.detail);
                }
            } else {
                toast.error("Insufficient inventory to prepare this order ❌");
            }
        }
    };
    const cancelOrder = (orderId) => {
        setSelectedOrderId(orderId);
        setShowCancelModal(true);
    };
    const confirmCancelOrder = async (reason) => {
        try {
            await api.post(`/oders/${selectedOrderId}/cancel`, null, {
                params: { reason },
            });

            toast.success("Order cancelled successfully ");

            setShowCancelModal(false);
            setSelectedOrderId(null);

            fetchOrders();
        } catch (err) {
            console.error(err.response?.data || err.message);
            toast.error("Failed to cancel order ");
        }
    };

    const fetchInventory = async () => {
        try {
            const res = await api.get("/inventory/");

            const allItems = res.data.data || [];
            const packagingItems = allItems.filter(
                item => item.unit?.toLowerCase() === "pcs"
            );

            setInventoryItems(packagingItems);
        } catch (err) {
            toast.error("Failed to fetch inventory items");
        }
    };
    
    return (
        <div className="px-6 py-4 text-gray-800 dark:text-gray-200">
            <h3 className="mb-4 font-medium">Orders Process</h3>

            <div className="w-full overflow-x-auto">
                <table className="w-full border-t border-gray-200 dark:border-gray-800">
                    <thead className="bg-gray-50 dark:bg-gray-900">
                        <tr>
                            <th className="px-4 py-3 text-left text-sm font-semibold">
                                Item Name
                            </th>
                            <th className="px-4 py-3 text-left text-sm font-semibold">
                                Category
                            </th>
                            <th className="px-4 py-3 text-left text-sm font-semibold">
                                Order Type
                            </th>
                            <th className="px-4 py-3 text-left text-sm font-semibold">
                                Action
                            </th>
                            <th className="px-4 py-3 text-left text-sm font-semibold">
                                Status
                            </th>
                            <th className="px-4 py-3 text-left text-sm font-semibold">
                                Total
                            </th>
                        </tr>
                    </thead>

                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-6 text-center">
                                    Loading orders...
                                </td>
                            </tr>
                        ) : orders.length === 0 ? (
                            <tr>
                                <td colSpan={5} className="px-4 py-6 text-center">
                                    No orders found
                                </td>
                            </tr>
                        ) : (
                                    orders.map((order) => {
                                        const firstItem = order.items?.[0];
                                        const dishDetails = dishMap[firstItem?.dish_id] || {};
                                        const action = getNextAction(order);

                                        return (
                                            <tr
                                                key={order.id}
                                                className="border-t border-gray-200 dark:border-gray-800"
                                            >
                                                <td className="px-4 py-2 text-sm">
                                                    {dishDetails.name || "—"}
                                                </td>

                                                <td className="px-4 py-2 text-sm">
                                                    {dishDetails.category || "—"}
                                                </td>

                                                <td className="px-4 py-2 text-sm">
                                                    {order.order_type}
                                                </td>


                                                <td className="px-4 py-2 flex gap-2">
                                                
                                                    {action && (
                                                        <button
                                                            onClick={() => {
                                                                if (action.type === "CONFIRM") {
                                                                    updateStatus(order.id, "CONFIRMED");
                                                                }

                                                                else if (action.type === "PREPARE") {
                                                                    prepareOrder(order.id);
                                                                }

                                                                else if (action.type === "STATUS") {
                                                                    updateStatus(order.id, action.nextStatus);
                                                                }

                                                                else if (action.type === "CHECKOUT") {
                                                                    if (order.order_type === "TAKEAWAY" || order.order_type === "DELIVERY") {
                                                                        setSelectedPackagingOrder(order);
                                                                        setShowPackagingModal(true);
                                                                    } else {
                                                                        setSelectedOrder(order);
                                                                        setShowPayment(true);
                                                                    }
                                                                }
                                                            }}
                                                            className="px-3 py-1 rounded-lg text-sm bg-green-500 text-white hover:bg-green-600"
                                                        >
                                                            {action.label}
                                                        </button>
                                                    )}

                                         
                                                    {order.status !== "COMPLETED" &&
                                                        order.status !== "CANCELLED" &&
                                                        order.status !== "REFUNDED" && (
                                                            <button
                                                            onClick={() => cancelOrder(order.id)}
                                                                className="px-3 py-1 rounded-lg text-sm bg-red-500 text-white hover:bg-red-600"
                                                            >
                                                                Cancel
                                                            </button>
                                                        )}
                                                </td>


                                                <td className="px-4 py-2 text-sm font-medium">
                                                    {order.status}
                                                </td>

                                                <td className="px-4 py-2 text-sm">
                                                    ₹ {order.total_amount}
                                                </td>
                                            </tr>
                                        );
                                    })
                        )}
                    </tbody>
                </table>
                <PaymentModal
                    isOpen={showPayment}
                    order={selectedOrder}
                    onClose={() => setShowPayment(false)}
                    onSuccess={() => {
                        fetchOrders();
                    }}
                />

                <CancelOrderModal
                    isOpen={showCancelModal}
                    onClose={() => setShowCancelModal(false)}
                    onConfirm={confirmCancelOrder}
                />

                <PackagingModal
                    isOpen={showPackagingModal}
                    order={selectedPackagingOrder}
                    inventoryItems={inventoryItems}
                    onClose={() => setShowPackagingModal(false)}
                    onSuccess={() => {
                        setShowPackagingModal(false);
                        setSelectedOrder(selectedPackagingOrder);
                        setShowPayment(true);
                    }}
                />
            </div>
        </div>
    );
}