import { FiTool } from "react-icons/fi";

export default function UnderDevelopment({ title = "Page" }) {
  return (
    <div className="w-full flex items-center justify-center min-h-[70vh] px-4">
      <div className="w-full max-w-md bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm p-6 text-center">
        <div className="w-14 h-14 mx-auto flex items-center justify-center rounded-full bg-orange-100 dark:bg-orange-500/20">
          <FiTool className="text-2xl text-orange-600 dark:text-orange-300" />
        </div>

        <h2 className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">
          {title} is Under Development 🚧
        </h2>

        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
          We are working on this module. It will be available soon.
        </p>
      </div>
    </div>
  );
}
