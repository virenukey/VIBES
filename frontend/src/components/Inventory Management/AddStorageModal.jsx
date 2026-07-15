import { useEffect, useState } from "react";
import { FiX } from "react-icons/fi";

export default function AddStorageModal({ isOpen, onClose, onSave, editData }) {

  const [formData, setFormData] = useState({
    name: "",
    minTemp: "",
    maxTemp: "",
    instruction: "",
    is_active: true,
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  const resetForm = () => {
    setFormData({
      name: "",
      minTemp: "",
      maxTemp: "",
      instruction: "",
      is_active: true,
    });
  };

  useEffect(() => {
    if (editData) {
      setFormData({
        name: editData.name || "",
        minTemp: editData.minTemp ?? "",
        maxTemp: editData.maxTemp ?? "",
        instruction: editData.instruction || "",
        is_active: editData.is_active ?? true,
      });
    } else {
      resetForm();
    }
  }, [editData]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (isSubmitting) return;

    setIsSubmitting(true);

    try {
      //  Capitalize first letter
      const formattedName =
        formData.name.charAt(0).toUpperCase() +
        formData.name.slice(1).toLowerCase();

      await onSave({
        ...formData,
        name: formattedName,
      });

      resetForm();
    } finally {
      setIsSubmitting(false);
    }
  };
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">

      {/* Overlay */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
      
      />

      {/* Modal */}
      <div
        className="relative w-full max-w-md bg-white dark:bg-[#0f172a] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-black dark:text-white">
            {editData ? "Edit Storage" : "Add Storage"}
          </h2>

          <button
            onClick={() => {
              resetForm();
              onClose();
            }}
            className="text-2xl text-gray-700 dark:text-gray-300 hover:text-black dark:hover:text-white transition"
          >
            <FiX />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">

          {/* Storage Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Storage Name
            </label>

            <input
              type="text"
              name="name"
              placeholder="Enter storage name"
              value={formData.name}
              onChange={handleChange}
              required
              className="w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none transition"
            />
          </div>

          {/* Temperature */}
          <div className="grid grid-cols-2 gap-4">

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Min Temp (°C)
              </label>

              <input
                type="number"
                name="minTemp"
                value={formData.minTemp}
                onChange={handleChange}
                placeholder="Min"
                className="w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none transition"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Max Temp (°C)
              </label>

              <input
                type="number"
                name="maxTemp"
                value={formData.maxTemp}
                onChange={handleChange}
                placeholder="Max"
                className="w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none transition"
              />
            </div>

          </div>

          {/* Instructions */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Instructions
            </label>

            <textarea
              name="instruction"
              rows={3}
              value={formData.instruction}
              onChange={handleChange}
              placeholder="Enter instructions"
              className="w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none resize-none transition"
            />
          </div>

          {/* Active checkbox (edit only) */}
          {/* {editData && (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    is_active: e.target.checked,
                  }))
                }
                className="accent-orange-500"
              />

              <label className="text-sm text-gray-700 dark:text-gray-300">
                Is Active
              </label>
            </div>
          )} */}

          {/* Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-lg font-semibold transition disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
            >
              {isSubmitting
                ? editData
                  ? "Updating Storage..."
                  : "Adding Storage..."
                : editData
                  ? "Update Storage"
                  : "Add Storage"}
            </button>
          </div>

        </form>
      </div>
    </div>
  );
}