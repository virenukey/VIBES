import { useEffect, useState } from "react";
import { FiX } from "react-icons/fi";

export default function AddCategoryModal({ isOpen, onClose, onSave, editData }) {
  const [formData, setFormData] = useState({
    name: "",
    type: "perishable",
  });

  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (editData) {
      setFormData({
        name: editData.name || "",
        type: editData.category_type || "perishable",
      });
    } else {
      setFormData({
        name: "",
        type: "perishable",
      });
    }
  }, [editData]);

  const resetForm = () => {
    setFormData({
      name: "",
      type: "perishable",
    });
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (isSubmitting) return;

    setIsSubmitting(true);

    try {
      // Capitalize first letter
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
        onClick={() => {
          resetForm();
          onClose();
        }}
      ></div>

      {/* Modal */}
      <div className="relative w-full max-w-md bg-white dark:bg-[#0f172a] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800 p-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-black dark:text-white">
            {editData ? "Edit Category" : "Add Category"}
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
        <form onSubmit={handleSubmit} className="space-y-6">

          {/* Two column layout */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

            {/* Category Name */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Category Name
              </label>

              <input
                type="text"
                name="name"
                placeholder="eg-Vegetables"
                value={formData.name}
                onChange={handleChange}
                className="w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none transition"
                required
              />
            </div>

            {/* Type */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Type
              </label>

              <select
                name="type"
                value={formData.type}
                onChange={handleChange}
                className="w-full px-3 py-2.5 rounded-xl border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#020617] text-gray-800 dark:text-gray-200 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 outline-none transition"
              >
                <option value="perishable">Perishable</option>
                <option value="non_perishable">Non Perishable</option>
              </select>
            </div>

          </div>

          {/* Submit Button */}
          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-2.5 rounded-xl bg-orange-500 hover:bg-orange-600 text-white text-lg font-semibold transition disabled:opacity-60 disabled:cursor-not-allowed shadow-sm"
            >
              {isSubmitting
                ? (editData ? "Updating Category..." : "Adding Category...")
                : (editData ? "Update Category" : "Add Category")}
            </button>
          </div>

        </form>
      </div>
    </div>
  );
}