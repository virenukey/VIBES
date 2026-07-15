import { Outlet } from "react-router-dom";
import Sidebar from "../components/Sidebar";
import { useSidebar } from "../context/SidebarContext";

export default function DashboardLayout() {
  const { open, closeSidebar } = useSidebar();

  return (
    <div className="min-h-screen flex bg-gray-50 dark:bg-[#0b1220] overflow-x-hidden">

      {/* ✅ Desktop Sidebar also depends on open */}
      {open && (
        <div className="hidden md:flex">
          <Sidebar />
        </div>
      )}

      {/* Mobile Sidebar Drawer */}
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={closeSidebar}
          ></div>

          <div className="absolute left-0 top-0 h-full">
            <Sidebar closeSidebar={closeSidebar} />
          </div>
        </div>
      )}

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <main className="flex-1 p-2 overflow-x-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
