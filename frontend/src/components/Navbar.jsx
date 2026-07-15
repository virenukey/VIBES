export default function Navbar({ onMenuClick }) {
  return (
    <div className="h-14 bg-white border-b flex items-center justify-between px-3 sm:px-4">
      <div className="flex items-center gap-3">
        {/* Mobile Menu Button */}
        <button
          className="md:hidden p-2 rounded hover:bg-gray-100"
          onClick={onMenuClick}
        >
          ☰
        </button>

        <h1 className="font-semibold text-base sm:text-lg">
          Inventory Management
        </h1>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <button className="px-3 py-1 bg-yellow-400 rounded-md font-medium text-sm sm:text-base">
          Add Item
        </button>

        <div className="text-xs sm:text-sm text-right">
          <p className="font-semibold">Globus</p>
          <p className="text-gray-500">Admin</p>
        </div>
      </div>
    </div>
  );
}
