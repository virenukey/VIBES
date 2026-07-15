import { useState, useEffect } from "react";
import { FiSidebar, FiBell, FiAlertTriangle, FiPackage } from "react-icons/fi";
import { useSidebar } from "../context/SidebarContext";
import { useNavigate } from "react-router-dom";
import { alertService } from "../services/alertService";

export default function PageHeader({
  title,
  subtitle    = null,   // optional subtitle shown below the title
  tabs        = null,   // [{ key, label }]  — renders tab pills on the right
  activeTab   = "",
  setActiveTab = () => {},
}) {
  const { toggleSidebar } = useSidebar();
  const navigate = useNavigate();

  const [activeCount, setActiveCount]     = useState(0);
  const [statsBreakdown, setStatsBreakdown] = useState([]);

  useEffect(() => {
    const checkAlerts = async () => {
      try {
        const data = await alertService.getAlertStats();
        if (data && Array.isArray(data.statistics)) {
          const activeStats = data.statistics.filter(s => s.status === "ACTIVE");
          setStatsBreakdown(activeStats);
          setActiveCount(activeStats.reduce((sum, s) => sum + s.count, 0));
        }
      } catch (error) {
        console.error("Failed to fetch alert stats", error);
      }
    };

    checkAlerts();
    const interval = setInterval(checkAlerts, 60000);
    window.addEventListener("refreshNotificationDot", checkAlerts);
    return () => {
      clearInterval(interval);
      window.removeEventListener("refreshNotificationDot", checkAlerts);
    };
  }, []);

  return (
    <div className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-[#0b1220]">

      {/* ── Main row: sidebar toggle · title · bell · tabs ── */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-4">

        {/* LEFT: Sidebar toggle + Title */}
        <div className="flex items-center gap-3">
          <button
            onClick={toggleSidebar}
            className="w-8 h-8 flex items-center justify-center rounded-md
              bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 transition"
          >
            <FiSidebar className="text-gray-800 dark:text-gray-200" />
          </button>

          <div>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-white leading-tight">
              {title}
            </h1>
            {/* Subtitle — shown only when provided */}
            {subtitle && (
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
                {subtitle}
              </p>
            )}
          </div>
        </div>

        {/* RIGHT: Bell + Tabs */}
        <div className="flex items-center gap-4">

          {/* Notification Bell */}
          <div className="relative group">
            <button
              onClick={() => navigate("/alerts")}
              className="p-2 text-gray-600 dark:text-gray-400
                hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition"
            >
              <FiBell className="text-xl" />

              {/* Alert count badge */}
              {activeCount > 0 && (
                <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center
                  rounded-full bg-red-500 text-[10px] font-bold text-white
                  border-2 border-white dark:border-gray-900 animate-pulse">
                  {activeCount > 9 ? "9+" : activeCount}
                </span>
              )}
            </button>

            {/* Hover tooltip breakdown */}
            {activeCount > 0 && (
              <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-[#111827]
                border border-gray-200 dark:border-gray-800 rounded-lg shadow-xl
                opacity-0 invisible group-hover:opacity-100 group-hover:visible
                transition-all duration-200 z-50 p-3">
                <p className="text-[10px] font-bold text-gray-400 uppercase mb-2 tracking-wider
                  border-b border-gray-100 dark:border-gray-800 pb-1">
                  Active System Risks
                </p>
                <div className="space-y-2 mt-2">
                  {statsBreakdown.map((stat, idx) => (
                    <div key={idx} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {stat.alert_type === "OUT_OF_STOCK" ? (
                          <FiPackage className="text-red-500" size={12} />
                        ) : (
                          <FiAlertTriangle className="text-yellow-500" size={12} />
                        )}
                        <span className="text-xs text-gray-600 dark:text-gray-300">
                          {stat.alert_type.replace(/_/g, " ")}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-gray-900 dark:text-white">
                        {stat.count}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="text-[9px] text-blue-500 mt-3 text-center italic">
                  Click bell to manage alerts
                </p>
              </div>
            )}
          </div>

          {/* Report toggle buttons — outlined inactive, solid orange active */}
          {tabs && (
            <div className="flex items-center gap-2">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-4 py-2 rounded-lg text-sm font-semibold transition
                    ${activeTab === tab.key
                      ? "bg-orange-500 text-white border border-orange-500"
                      : "bg-white dark:bg-transparent text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 hover:border-orange-400 hover:text-orange-500"
                    }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
