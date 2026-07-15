import { useState } from "react";
import { toast } from "react-toastify";
import api from "../../api/axios";
import {
    FiDollarSign,
    FiCreditCard,
    FiSmartphone,
    FiBriefcase,
    FiHome,
    FiMoreHorizontal,
} from "react-icons/fi";

export default function PaymentModal({
    isOpen,
    onClose,
    order,
    onSuccess,
}) {
    const [paymentMode, setPaymentMode] = useState("CASH");
    const [loading, setLoading] = useState(false);

    if (!isOpen || !order) return null;

    const handlePayment = async () => {
        try {
            setLoading(true);

            await api.post(`/oders/${order.id}/payments`, {
                payment_method: paymentMode,
                amount: parseFloat(order.total_amount),
                transaction_id: "",
                reference_number: "",
                notes: "",
            });

            await api.patch(`/oders/${order.id}/status`, {
                status: "COMPLETED",
                notes: "",
            });

            toast.success("Payment successful & Order completed ");

            onSuccess();
            onClose();
        } catch (err) {
            console.error(err.response?.data || err.message);
            toast.error("Payment failed ❌");
        } finally {
            setLoading(false);
        }
    };

        return (
            <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl p-6 sm:p-8 animate-fadeIn">

                    {/* Header */}
                    <h2 className="text-xl sm:text-2xl font-semibold text-gray-800 mb-6">
                        Payment Process
                    </h2>

                    {/* Order Info */}
                    <div className="bg-gray-50 rounded-lg p-4 mb-6 border">
                        <p className="text-sm sm:text-base text-gray-700">
                            <span className="font-medium">Order:</span>{" "}
                            <span className="text-gray-900">{order.order_number}</span>
                        </p>

                        <p className="text-lg sm:text-xl font-semibold text-gray-900 mt-2">
                            Total: ₹{order.total_amount}
                        </p>
                    </div>

                    {/* Payment Methods */}
                    <div className="mb-6">
                        <p className="text-sm font-medium text-gray-600 mb-3">
                            Select Payment Method
                        </p>

                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                            {[
                                { label: "CASH", icon: <FiDollarSign /> },
                                { label: "CARD", icon: <FiCreditCard /> },
                                { label: "UPI", icon: <FiSmartphone /> },
                                { label: "WALLET", icon: <FiBriefcase /> },
                                { label: "BANK_TRANSFER", icon: <FiHome /> },
                                { label: "OTHER", icon: <FiMoreHorizontal /> },
                            ].map((mode) => (
                                <button
                                    key={mode.label}
                                    onClick={() => setPaymentMode(mode.label)}
                                    className={`
                    flex items-center justify-center gap-2
                    px-3 py-2 rounded-lg border text-sm font-medium
                    transition-all duration-200 cursor-pointer
                    ${paymentMode === mode.label
                                            ? "bg-orange-500 text-white border-orange-500 shadow-md scale-105"
                                            : "bg-white text-gray-700 hover:bg-orange-50 hover:border-orange-400"
                                        }
                `}
                                >
                                    <span className="text-lg">{mode.icon}</span>
                                    {mode.label.replace("_", " ")}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex flex-col sm:flex-row gap-3">
                        <button
                            onClick={handlePayment}
                            disabled={loading}
                            className={`
                            w-full sm:flex-1 py-2.5 rounded-lg font-medium text-white
                            transition-all duration-200 cursor-pointer
                            ${loading
                                    ? "bg-green-400 cursor-not-allowed"
                                    : "bg-green-600 hover:bg-green-700 active:scale-95"
                                }
                        `}
                        >
                            {loading ? "Processing..." : "Pay"}
                        </button>

                        <button
                            onClick={onClose}
                            className="w-full sm:flex-1 py-2.5 rounded-lg bg-gray-200 hover:bg-gray-300 active:scale-95 transition-all duration-200 font-medium cursor-pointer"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        );
}