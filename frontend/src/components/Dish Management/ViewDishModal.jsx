import { FiX } from "react-icons/fi";

export default function ViewDishModal({ isOpen, onClose, data }) {
  console.log("Dish data for modal:", data);
  if (!isOpen || !data) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className="relative w-full max-w-md bg-white dark:bg-[#0f172a]
                   rounded-xl shadow-lg border border-gray-200 dark:border-gray-700"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-200">
            Dish Details
          </h2>

          <button
            onClick={onClose}
            className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <FiX className="text-xl text-gray-700 dark:text-gray-200" />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-5 space-y-5">
          {/* Top Info */}
          <div className="flex justify-between gap-6">
            {/* Dish Name */}
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Dish Name
              </p>
              <p className="text-base font-semibold text-gray-900 dark:text-gray-100">
                {data.name}
              </p>
            </div>

            {/* Category */}
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Category
              </p>
              <p className="text-base font-medium text-gray-900 dark:text-gray-100">
                {data.type?.name}
              </p>
            </div>
          </div>

          {/* Secondary Info */}
          <div className="flex justify-between gap-4 text-sm">
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Portion Size
              </p>
              <p className="font-medium text-gray-800 dark:text-gray-200">
                {data.standard_portion_size || "-"}
              </p>
            </div>

            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Yield Quantity
              </p>
              <p className="font-medium text-gray-800 dark:text-gray-200">
                {data.yield_quantity || "-"}
              </p>
            </div>

            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Preparation Time
              </p>
              <p className="font-medium text-gray-800 dark:text-gray-200">
                {data.preparation_time_minutes} min
              </p>
            </div>

            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Selling Price
              </p>
              <p className="font-medium text-gray-800 dark:text-gray-200">
                ₹{data.selling_price}
              </p>
            </div>
          </div>

          {/* Ingredients */}
          {Array.isArray(data.ingredients) && data.ingredients.length > 0 && (
            <div>
                <p className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">
                Ingredients
                </p>

                <div
                className="max-h-52 overflow-y-auto border border-gray-200 dark:border-gray-700
                            rounded-lg divide-y divide-gray-200 dark:divide-gray-700"
                >
                {data.ingredients.map((ing, index) => (
                    <div
                    key={index}
                    className="flex items-center justify-between px-3 py-2 text-sm"
                    >
                    <span className="text-gray-800 dark:text-gray-200">
                        {ing.ingredient_name}
                    </span>

                    <span className="font-medium text-gray-700 dark:text-gray-300">
                        {ing.quantity_required} {ing.unit}
                    </span>
                  </div>
              
                ))}
              
                </div>
            </div>
            )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2 rounded-md bg-yellow-400 hover:bg-yellow-500
                       text-black font-medium transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
