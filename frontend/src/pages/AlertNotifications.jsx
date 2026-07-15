import { useState, useEffect, useCallback } from "react";
import PageHeader from "../components/PageHeader";
import {
  FiClock,
  FiCheckCircle,
  FiBell,
  FiRefreshCw,
  FiFilter,
  FiLoader,
  FiChevronRight,
  FiChevronLeft,
} from "react-icons/fi";
import { toast } from "react-toastify";
import { alertService } from "../services/alertService"; // Import the service

export default function AlertNotifications() {
  const [alerts, setAlerts] = useState([]);
  const [groupedAlerts, setGroupedAlerts] = useState({});
  const [showActiveOnly, setShowActiveOnly] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // PAGINATION
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [currentPage, setCurrentPage] = useState(1);

  // 1. Fetch data from Backend
  const fetchAlerts = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await alertService.getAlerts();
      setAlerts(data);
    } catch (error) {
      toast.error("Failed to fetch alerts. Please try again.");
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  // 2. Process and Group Data
  useEffect(() => {
    const groups = { Today: [], Yesterday: [], Earlier: [] };
    const now = new Date();

    const dataToDisplay = showActiveOnly
      ? alerts.filter((alert) => alert.status === "ACTIVE")
      : alerts;

    // 🔥 PAGINATION LOGIC
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;
    const paginated = dataToDisplay.slice(start, end);

    paginated.forEach((alert) => {
      const alertDate = new Date(alert.alert_date);
      const diffDays = Math.floor((now - alertDate) / (1000 * 60 * 60 * 24));

      if (diffDays === 0) groups.Today.push(alert);
      else if (diffDays === 1) groups.Yesterday.push(alert);
      else groups.Earlier.push(alert);
    });

    setGroupedAlerts(groups);
  }, [alerts, showActiveOnly, currentPage, rowsPerPage]);

  // 3. Handle Backend Actions
  const handleResolve = async (id) => {
    try {
      await alertService.resolveAlert(id);
      toast.success("Alert resolved successfully");
      fetchAlerts(); // Refresh list
    } catch (error) {
      toast.error("Failed to resolve alert");
    }
  };

  const handleSnooze = async (id) => {
    try {
      await alertService.snoozeAlert(id);
      toast.info("Alert snoozed");
      fetchAlerts(); // Refresh list
    } catch (error) {
      toast.error("Failed to snooze alert");
    }
  };

  const filteredAlerts = showActiveOnly
    ? alerts.filter((a) => a.status === "ACTIVE")
    : alerts;

  const totalPages = Math.ceil(filteredAlerts.length / rowsPerPage) || 1;
  return (
    <div className="flex flex-col h-full bg-[#f8fafc] dark:bg-[#0b1220]">
      <PageHeader title="Alert Notification" />

      {/* HEADER */}
      <div className="px-6 py-4 bg-white dark:bg-[#111827] border-b border-gray-100 dark:border-gray-800 flex justify-between items-center">
        <div>
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white">
            System Health
          </h2>
          <p className="text-xs text-gray-500">
            Monitor and manage inventory risks
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowActiveOnly(!showActiveOnly)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
              showActiveOnly
                ? "bg-orange-50 border-orange-200 text-orange-600"
                : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            <FiFilter size={14} />
            {showActiveOnly ? "Active Only" : "Showing All"}
          </button>

          <button
            onClick={fetchAlerts}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-1.5 bg-orange-500 hover:bg-orange-600 text-white rounded-lg text-xs font-medium disabled:opacity-50"
          >
            <FiRefreshCw className={isLoading ? "animate-spin" : ""} size={14} />
            {isLoading ? "Checking..." : "Run Check"}
          </button>
        </div>
      </div>

      {/* BODY */}
      <div className="p-4 md:p-6">
        <div className="max-h-[500px] overflow-y-auto pr-2">
        <div className="max-w-6xl mx-auto space-y-6">
          {isLoading && alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-gray-400">
              <FiLoader size={40} className="animate-spin mb-4" />
              <p>Fetching latest alerts...</p>
            </div>
          ) : alerts.length === 0 ? (
            <div className="text-center py-20 text-gray-500">
              <FiCheckCircle size={40} className="mx-auto mb-4 text-green-500 opacity-20" />
              <p>All clear! No alerts found.</p>
            </div>
          ) : (
            Object.entries(groupedAlerts).map(
              ([groupName, items]) =>
                items.length > 0 && (
                  <section key={groupName}>
                    <div className="flex items-center gap-3 mb-3">
                      <h3 className="text-xs font-semibold text-gray-400 uppercase">
                        {groupName}
                      </h3>
                      <div className="h-px bg-gray-200 dark:bg-gray-800 flex-1"></div>
                    </div>

                    <div className="space-y-3">
                      {items.map((alert) => (
                        <div
                          key={alert.id}
                          className={`bg-white dark:bg-[#111827] border border-gray-100 dark:border-gray-800 rounded-xl p-4 flex items-center gap-4 transition hover:shadow-md
                          ${alert.status === "RESOLVED" ? "opacity-60 grayscale-[0.5]" : ""}`}
                        >
                          {/* PRIORITY BAR */}
                          <div
                            className={`w-1 h-12 rounded-full ${
                              alert.priority === "critical"
                                ? "bg-red-500"
                                : alert.alert_type === "EXPIRY_WARNING"
                                ? "bg-yellow-400"
                                : "bg-blue-400"
                            }`}
                          />

                          {/* CONTENT */}
                          <div className="flex-1 grid md:grid-cols-3 gap-x-10 gap-y-3 items-center">
                            <div>
                              <p className="text-[10px] text-gray-400 uppercase">Item</p>
                              <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
                                {alert.inventory_item_name || "System Item"}
                              </h4>
                            </div>

                            <div>
                              <div className={`rounded-lg px-3 py-2 text-xs flex items-start gap-2
                                ${alert.priority === "critical" ? "bg-red-50 text-red-700 border border-red-200" : 
                                  alert.alert_type === "EXPIRY_WARNING" ? "bg-yellow-50 text-yellow-700 border border-yellow-200" : 
                                  "bg-blue-50 text-blue-700 border border-blue-200"}`}
                              >
                                <FiBell className="mt-[2px] shrink-0" size={14} />
                                <div>
                                  <p className="font-semibold leading-snug">{alert.message}</p>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span className="text-[10px] text-gray-500 flex items-center gap-1">
                                      <FiClock size={12} />
                                      {new Date(alert.alert_date).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            </div>

                            <div>
                              <p className="text-[10px] text-gray-400 uppercase">Stock</p>
                              <p className="text-sm font-bold text-gray-900 dark:text-white">
                                {parseFloat(alert.current_quantity).toFixed(2)} Units
                              </p>
                              <p className="text-[11px] text-blue-500">{alert.suggested_action}</p>
                            </div>
                          </div>

                          {/* ACTIONS */}
                          <div className="flex items-center gap-1">
                            {alert.status === "ACTIVE" && (
                              <>
                                <button
                                  onClick={() => handleSnooze(alert.id)}
                                  title="Snooze"
                                  className="p-2 rounded-md bg-yellow-50 text-yellow-600 hover:bg-yellow-600 hover:text-white transition"
                                >
                                  <FiClock size={14} />
                                </button>
                                <button
                                  onClick={() => handleResolve(alert.id)}
                                  title="Resolve"
                                  className="p-2 rounded-md bg-green-50 text-green-600 hover:bg-green-600 hover:text-white transition"
                                >
                                  <FiCheckCircle size={14} />
                                </button>
                              </>
                            )}
                            {alert.status === "RESOLVED" && (
                              <span className="text-xs text-green-600 font-medium px-2 flex items-center gap-1">
                                <FiCheckCircle size={12} /> Resolved
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                    
                  </section>

                )
            )
          )}
          </div>
          
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 px-4 py-4 border-t border-gray-200 dark:border-gray-800">

          <div className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
            <span className="font-medium">Rows per page</span>

            <select
              value={rowsPerPage}
              onChange={(e) => {
                setRowsPerPage(Number(e.target.value));
                setCurrentPage(1);
              }}
              className="px-3 py-1 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
            >
              <option value={5}>5</option>
              <option value={10}>10</option>
              <option value={25}>25</option>
            </select>
          </div>

          <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
            Page {currentPage} of {totalPages}
          </div>

          <div className="flex items-center gap-2">
            <button
              disabled={currentPage === 1}
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              className="p-2 rounded-md border border-gray-200 dark:border-gray-700 disabled:opacity-40 dark:text-white"
            >
               <FiChevronLeft />
            </button>

            <button
              disabled={currentPage === totalPages}
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              className="p-2 rounded-md border border-gray-200 dark:border-gray-700 disabled:opacity-40 dark:text-white"
            >
              <FiChevronRight />
            </button>
          </div>

        </div>
      </div>
      
    </div>
    
  );
}