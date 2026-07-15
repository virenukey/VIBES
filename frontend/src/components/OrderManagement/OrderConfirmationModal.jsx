import { useState } from "react";
import { toast } from "react-toastify";
import api from "../../api/axios";

export default function OrderConfirmationModal({
    isOpen,
    onClose,
    dish,
    onSuccess,
}) {
    const [quantity, setQuantity] = useState(1);
    const [orderType, setOrderType] = useState("DINE_IN");
    const [loading, setLoading] = useState(false);
    const [deliveryAddress, setDeliveryAddress] = useState("");
    const [customerName, setCustomerName] = useState("");
    const [customerPhone, setCustomerPhone] = useState("");

    if (!isOpen || !dish) return null;

    const handleSave = async () => {
        try {
            if (orderType === "PARCEL" && !deliveryAddress.trim()) {
                toast.error("Delivery address is required for Parcel orders ❌");
                return;
            }

            setLoading(true);

            const payload = {
                order_type: orderType === "PARCEL" ? "DELIVERY" : orderType,
                customer_name: customerName.trim() || null,
                customer_phone: customerPhone.trim() || null,
                customer_email: "",
                table_number: orderType === "DINE_IN" ? "1" : "",
                delivery_address:
                    orderType === "PARCEL" ? deliveryAddress : "",
                tax_rate: 0,
                discount_amount: 0,
                delivery_charge: 0,
                notes: "",
                special_instructions: "",
                items: [
                    {
                        dish_id: dish.id,
                        quantity: quantity,
                        unit_price: parseFloat(dish.selling_price),
                        discount_amount: 0,
                        special_instructions: "",
                    },
                ],
            };

            await api.post("/oders/", payload);

            toast.success("Order created successfully ");

            onSuccess();
            onClose();
        } catch (err) {
            console.error(err.response?.data || err.message);
            toast.error("Failed to create order ");
        } finally {
            setLoading(false);
        }
    };
    
    
    return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-3">

            {/* Modal Container */}
            <div className="bg-white dark:bg-[#0f172a] 
                      w-full max-w-4xl 
                      max-h-[90vh] overflow-y-auto
                      rounded-xl shadow-xl p-5 sm:p-6">

                <h2 className="text-lg sm:text-xl font-semibold mb-6">
                    Order Confirmation
                </h2>

                {/* Dish Info */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                    <div>
                        <label className="text-sm font-medium">Dish Name</label>
                        <input
                            value={dish.name}
                            disabled
                            className="w-full mt-1 px-3 py-2 border rounded-lg bg-gray-100 text-sm"
                        />
                    </div>

                    <div>
                        <label className="text-sm font-medium">Category</label>
                        <input
                            value={dish.type?.name}
                            disabled
                            className="w-full mt-1 px-3 py-2 border rounded-lg bg-gray-100 text-sm"
                        />
                    </div>
                </div>
           
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">

                    <div>
                        <label className="text-sm font-medium">
                            Customer Name
                        </label>
                        <input
                            type="text"
                            value={customerName}
                            onChange={(e) => setCustomerName(e.target.value)}
                            className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                            placeholder="Enter customer name"
                        />
                    </div>

                    <div>
                        <label className="text-sm font-medium">
                            Customer Phone
                        </label>
                        <input
                            type="tel"
                            value={customerPhone}
                            onChange={(e) => setCustomerPhone(e.target.value)}
                            className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                            placeholder="Enter phone number"
                        />
                    </div>

                </div>

            
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">

                    <div>
                        <label className="text-sm font-medium">Type</label>
                        <select
                            value={orderType}
                            onChange={(e) => setOrderType(e.target.value)}
                            className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                        >
                            <option value="DINE_IN">Dine In</option>
                            <option value="TAKEAWAY">Takeaway</option>
                            <option value="PARCEL">Parcel</option>
                        </select>
                    </div>

                    {/* Quantity */}
                    <div>
                        <label className="text-sm font-medium">Total Quantity</label>
                        <div className="flex items-center gap-3 mt-2">
                            <button
                                onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                                className="px-3 py-1 border rounded-lg text-sm"
                            >
                                -
                            </button>
                            <span className="min-w-[30px] text-center">{quantity}</span>
                            <button
                                onClick={() => setQuantity((q) => q + 1)}
                                className="px-3 py-1 border rounded-lg text-sm"
                            >
                                +
                            </button>
                        </div>
                    </div>
                </div>

                {/* Parcel Section */}
               
                {orderType === "PARCEL" && (
                    <div className="mt-4">
                        <label className="text-sm font-medium">
                            Delivery Address *
                        </label>
                        <textarea
                            value={deliveryAddress}
                            onChange={(e) => setDeliveryAddress(e.target.value)}
                            rows={3}
                            className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                            placeholder="Enter delivery address"
                        />
                    </div>
                )}
              
                <div className="flex flex-col sm:flex-row gap-4 mt-8">
                    <button
                        onClick={handleSave}
                        disabled={loading}
                        className="w-full sm:w-auto px-6 py-2 rounded-lg bg-green-500 text-white text-sm font-medium"
                    >
                        {loading ? "Saving..." : "Save"}
                    </button>

                    <button
                        onClick={onClose}
                        className="w-full sm:w-auto px-6 py-2 rounded-lg bg-yellow-400 text-white text-sm font-medium"
                    >
                        Cancel
                    </button>
                </div>

            </div>
        </div>
    );
}