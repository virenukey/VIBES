import { useEffect, useState } from "react";
import { FiX } from "react-icons/fi";
import { toast } from "react-toastify";

export default function AddDishCategoryModal({
  isOpen,
  onClose,
  onSave,
  editData,
}) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (editData) {
      setName(editData.name || "");
    } else {
      setName("");
    }
  }, [editData]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (loading) return;

    setLoading(true);

    try {
      const formattedName = name
        .trim()                   
        .replace(/\s+/g, " ")      
        .toLowerCase()              
        .replace(/\b\w/g, (c) => c.toUpperCase()); 

      await onSave({ name: formattedName });

      toast.success(
        editData
          ? "Dish category updated successfully"
          : "Dish category added successfully"
      );

      setName("");
      onClose();

    } catch (err) {

      toast.error(
        err?.message || "Dish type with this name already exists"
      );
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-3 sm:px-6">

      {/* Overlay */}
      <div className="absolute inset-0 bg-black/40"></div>

      {/* Modal */}
      <div className="relative w-full max-w-md bg-white dark:bg-[#0f172a] rounded-xl shadow-lg border border-gray-200 dark:border-gray-800">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {editData ? "Edit Dish Category" : "Add Dish Category"}
          </h2>

          <button
            onClick={onClose}
            className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            <FiX className="text-xl text-gray-700 dark:text-gray-200" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="px-5 py-5 space-y-6">

          {/* Category Name */}
          <div>
            <label className="text-sm font-medium text-gray-800 dark:text-gray-200">
              Dish Category
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Enter dish category name"
              className="mt-2 w-full border border-gray-300 dark:border-gray-700 
                         rounded-md px-3 py-2 bg-white dark:bg-[#0b1220] 
                         text-gray-800 dark:text-gray-200 outline-none"
              required
            />
          </div>

          {/* Buttons */}
          <div className="mt-5 flex items-center gap-4">
            <button
              type="submit"
              disabled={loading}
              className="px-8 py-2 rounded-md bg-orange-500 hover:bg-orange-600 
                         text-white font-medium transition disabled:opacity-50"
            >
              {loading ? "Saving..." : "Save"}
            </button>

            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-8 py-2 rounded-md bg-gray-500 hover:bg-gray-600 
                         text-white font-medium transition disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}