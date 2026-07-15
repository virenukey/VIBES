
import { FiX } from "react-icons/fi";
import api from "../../api/axios";
import { useState, useEffect } from "react";

export default function ProduceSemiFinishedModal({
    isOpen,
    onClose,
    product,
    onSuccess
}) {
    const [quantity, setQuantity] = useState("");
    const [notes, setNotes] = useState("");
    const [loading, setLoading] = useState(false);
    useEffect(() => {
        if (isOpen) {
            resetForm();
        }
    }, [isOpen, product]);

    if (!isOpen || !product) return null;
    const resetForm = () => {
        setQuantity("");
        setNotes("");
    };

    const handleSubmit = async () => {
        if (!quantity) {
            alert("Enter quantity to produce");
            return;
        }

        try {
            setLoading(true);

            await api.post("/dish/semi-finished/produce", {
                product_id: product.product_id,
                quantity_to_produce: Number(quantity),
                notes: notes
            });

            alert("Batch produced successfully");
            onSuccess();
            onClose();

        } catch (err) {
            console.error(err);
            alert("Failed to produce batch");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
            <div className="absolute inset-0 bg-black/40" onClick={onClose} />

            <div className="relative w-full max-w-md bg-white dark:bg-[#0f172a]
                      rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">

                {/* Header */}
                <div className="flex items-center justify-between px-5 py-4 border-b">
                    <h2 className="text-lg font-semibold">
                        Produce Batch
                    </h2>

                    <button onClick={onClose}>
                        <FiX />
                    </button>
                </div>

                {/* Body */}
                <div className="px-5 py-5 space-y-5">

                    {/* Product Info */}
                    <div>
                        <p className="text-sm text-gray-500">Product</p>
                        <p className="font-semibold text-lg">{product.name}</p>
                    </div>

                    {/* Quantity */}
                    <div>
                        <label className="text-sm font-medium">
                            Quantity to Produce ({product.unit})
                        </label>
                        <input
                            type="number"
                            value={quantity}
                            onChange={(e) => setQuantity(e.target.value)}
                            className="mt-2 w-full border rounded-md px-3 py-2"
                        />
                    </div>

                    {/* Info Box */}
                    <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 text-sm space-y-2">
                        <div>
                            <strong>Yield Per Batch:</strong> {product.yield_quantity} {product.unit}
                        </div>

                        {product.shelf_life_hours && (
                            <div>
                                <strong>Shelf Life:</strong> {product.shelf_life_hours} hours
                            </div>
                        )}

                        {product.shelf_life_hours && (
                            <div>
                                <strong>Estimated Expiry:</strong>{" "}
                                {new Date(
                                    Date.now() + product.shelf_life_hours * 60 * 60 * 1000
                                ).toLocaleString()}
                            </div>
                        )}
                    </div>

                    {/* Ingredients Required */}
                    <div>
                        <p className="font-medium mb-2">Ingredients Required:</p>

                        <div className="border rounded-lg divide-y">
                            {(product.ingredients || []).map((ing, index) => {

                                const multiplier =
                                    quantity && product.yield_quantity
                                        ? Number(quantity) / Number(product.yield_quantity)
                                        : 0;

                                const requiredQty =
                                    multiplier > 0
                                        ? (ing.quantity_required * multiplier).toFixed(2)
                                        : ing.quantity_required;

                                return (
                                    <div
                                        key={ing.ingredient_id}
                                        className="flex justify-between px-3 py-2 text-sm"
                                    >
                                        <span>{ing.ingredient_name}</span>
                                        <span>
                                            {requiredQty} {ing.unit}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Notes */}
                    <div>
                        <label className="text-sm font-medium">
                            Notes
                        </label>
                        <textarea
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            className="mt-2 w-full border rounded-md px-3 py-2"
                        />
                    </div>

                </div>


                {/* Footer */}
                <div className="px-5 py-4 border-t flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-gray-200 rounded-md"
                    >
                        Cancel
                    </button>

                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="px-4 py-2 bg-green-500 text-white rounded-md"
                    >
                        {loading ? "Producing..." : "Produce Batch"}
                    </button>
                </div>
            </div>
        </div>
    );
}
