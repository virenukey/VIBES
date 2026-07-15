import { FiX } from "react-icons/fi";

export default function ViewPreparedStuffModal({ isOpen, onClose, data }) {
  if (!isOpen || !data) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md bg-white dark:bg-[#0f172a]
                      rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-200">
            Details
          </h2>

          <button
            onClick={onClose}
            className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <FiX className="text-xl text-gray-700 dark:text-gray-200" />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-5 space-y-4">
            <div className="flex justify-between mb-6">
            {/* Name */}
            <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                Item Name
                </p>
                <p className="text-base font-semibold text-gray-900 dark:text-gray-100">
                {data.name}
                </p>
            </div>

            {/* Quantity */}
            <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                Total Quantity Available
                </p>
                <p className="text-base font-medium text-gray-900 dark:text-gray-100">
                {data.yield_quantity} {data.unit}

                </p>
            </div>
          </div>

          {/* Ingredients */}
          <div>
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">
              Ingredients
            </p>

            <div className="max-h-52 overflow-y-auto border border-gray-200 dark:border-gray-700
                  rounded-lg divide-y divide-gray-200 dark:divide-gray-700">
              {(data.ingredients || []).length === 0 ? (
                <div className="p-3 text-sm text-gray-500 dark:text-gray-400">
                  No ingredients added
                </div>
              ) : (
                (data.ingredients || []).map((ing, index) => (
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
                ))
              )}
            </div>
          </div>

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
