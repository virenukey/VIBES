import React, { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { ShoppingCart, IndianRupee, TrendingUp, Package } from "lucide-react";
import api from "../../api/axios";
import PageHeader from "../PageHeader";
import WastageReportView from "./WastageReport";
import { capitalizeWords } from "../../utils/text";

/* ================= STAT CARD ================= */

const StatCard = ({ icon: Icon, iconBg, label, value, prefix = "" }) => (
  <div
    className="flex-1 min-w-[150px] 
  bg-white dark:bg-[#020617] 
  border border-gray-200 dark:border-gray-800 
  rounded-[10px] px-[18px] py-[14px] 
  flex flex-col gap-2"
  >
    <div className="flex justify-between items-center">
      <span className="text-[13px] text-gray-600 dark:text-gray-400 font-medium">
        {label}
      </span>

      <div
        className="rounded-lg p-[6px] flex items-center justify-center"
        style={{ background: iconBg }} // ✅ keep dynamic
      >
        <Icon size={16} className="text-white" />
      </div>
    </div>

    <span className="text-[22px] font-bold text-gray-800 dark:text-white">
      {prefix}
      {typeof value === "number" ? value.toLocaleString("en-IN") : value}
    </span>
  </div>
);

/* ================= TOOLTIP ================= */

const BarTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload || {};

  return (
    <div className="bg-gray-800 text-white px-3 py-2 rounded-md text-xs min-w-[130px]">
      <p className="font-semibold mb-1">{label}</p>
      <p>
        Orders: <strong>{d.order_count ?? payload[0].value}</strong>
      </p>
      <p>
        Revenue: <strong>₹{(d.revenue ?? 0).toLocaleString("en-IN")}</strong>
      </p>
    </div>
  );
};

/* ================= PIE LABEL ================= */

const RADIAN = Math.PI / 180;

const PieLabel = ({ cx, cy, midAngle, innerRadius, outerRadius, percent }) => {
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);

  return (
    <text
      x={x}
      y={y}
      fill="white"
      textAnchor="middle"
      dominantBaseline="central"
      className="text-[11px] font-semibold"
    >
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
};

// ================= API FUNCTIONS =================

// Summary
const fetchSummaryStats = async (period, startDate = null, endDate = null) => {
  const params = { filter_type: period };

  // Daily filter
  if (period === "daily" && startDate) {
    params.date = startDate;
  }

  // Custom filter
  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/oders/sales-dashboard", { params });

  return {
    totalOrders: res.data.total_orders,
    totalRevenue: res.data.total_revenue,
    profit: res.data.profit,
    netProfit: res.data.net_profit,
    totalCost: res.data.total_cogs,
  };
};

// Trends
const fetchOrderVolumeTrends = async (
  period,
  startDate = null,
  endDate = null,
) => {
  const params = { period };
  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/oders/reports/order-volume-trends", { params });
  return res.data.trends || [];
};

// Category
const CATEGORY_COLORS = [
  "#f97316",
  "#6366f1",
  "#22c55e",
  "#3b82f6",
  "#ef4444",
  "#eab308",
  "#14b8a6",
  "#ec4899",
];

const fetchSalesByCategory = async (
  period,
  startDate = null,
  endDate = null,
) => {
  const params = { period };

  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/oders/reports/sales-by-category", { params });

  return (res.data.categories || []).map((cat, i) => ({
    name: capitalizeWords(cat.category),
    value: cat.percentage,
    revenue: cat.revenue,
    order_count: cat.order_count,
    color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
  }));
};

// Top dishes
const fetchTopDishes = async (
  period,
  startDate = null,
  endDate = null,
  limit = 10,
) => {
  const params = { period, limit };

  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/oders/reports/top-dishes", { params });

  return (res.data.top_dishes || []).map((dish) => ({
    rank: dish.rank,
    dish_id: dish.dish_id,
    name: dish.dish_name,
    subtitle: dish.category,
    unitsSold: dish.units_sold,
    revenue: dish.total_revenue,
  }));
};

/* ================= MAIN ================= */

const ReportAndAnalysisTab = () => {
  const [period, setPeriod] = useState("daily");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [summary, setSummary] = useState(null);
  const [trends, setTrends] = useState([]);
  const [categories, setCategories] = useState([]);
  const [topDishes, setTopDishes] = useState([]);
  const [topDishesLoading, setTopDishesLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [topDishesError, setTopDishesError] = useState(null);
  const [activeReport, setActiveReport] = useState("Sales and Order Report");

  const periods = ["daily", "weekly", "monthly", "custom"];

  const periodLabel = (p) => p.charAt(0).toUpperCase() + p.slice(1);

  /* ================= FETCH ================= */

  const loadData = async () => {
    setLoading(true);
    setTopDishesError(null);

    try {
      const [summaryData, trendsData, categoryData] = await Promise.all([
        fetchSummaryStats(period, startDate, endDate),
        fetchOrderVolumeTrends(period, startDate, endDate),
        fetchSalesByCategory(period, startDate, endDate),
      ]);

      // ✅ Set main dashboard data
      setSummary(summaryData);
      setTrends(trendsData);
      setCategories(categoryData);

      // ✅ Load top dishes separately (kept same as your original logic)
      await loadTopDishes(period, startDate, endDate);
    } catch (err) {
      console.error("Failed to load report data:", err);
    } finally {
      setLoading(false);
    }
  };

  const loadTopDishes = async (p, sd, ed) => {
    setTopDishesLoading(true);
    setTopDishesError(null);

    try {
      const dishes = await fetchTopDishes(p, sd || null, ed || null, 10);
      setTopDishes(dishes);
    } catch (err) {
      setTopDishesError(
        err?.response?.data?.detail ||
          err.message ||
          "Failed to load top dishes.",
      );
    } finally {
      setTopDishesLoading(false);
    }
  };

  useEffect(() => {
    if (activeReport !== "Sales and Order Report") return;

    // For normal periods
    if (period !== "custom") {
      loadData();
      return;
    }

    // For custom period
    if (period === "custom" && startDate && endDate) {
      loadData();
    }
  }, [period, startDate, endDate, activeReport]);

  useEffect(() => {
    if (
      period === "custom" &&
      startDate &&
      endDate &&
      activeReport === "Sales and Order Report"
    ) {
      loadData();
    }
  }, [startDate, endDate]);
  /* ================= UI ================= */

  return (
    <div className="w-full bg-white dark:bg-[#020617] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm">
      <PageHeader
        title="Reports and Analysis"
        tabs={[
          { key: "Sales and Order Report", label: "Sales and Order Report" },
          { key: "Wastage Reports", label: "Wastage Reports" },
        ]}
        activeTab={activeReport}
        setActiveTab={setActiveReport}
      />

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 px-6 py-4">
        <div className="flex items-center gap-1 bg-gray-100 dark:bg-[#020617] p-1 rounded-full">
          {periods.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-4 py-1.5 text-sm rounded-full font-medium transition
                ${
                  period === p
                    ? "bg-orange-500 text-white"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-800"
                }`}
            >
              {periodLabel(p)}
            </button>
          ))}
        </div>

        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          disabled={period !== "custom"}
          className={`px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200
  ${period !== "custom" ? "opacity-40 cursor-not-allowed" : ""}`}
        />

        <span className="text-gray-400">–</span>

        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          disabled={period !== "custom"}
          className={`px-3 py-1.5 rounded-lg
  border-2 border-orange-400
  bg-white dark:bg-[#020617]
  text-sm text-gray-700 dark:text-gray-200
  outline-none
  hover:border-orange-500 focus:border-orange-500
  transition-all duration-200
  ${period !== "custom" ? "opacity-40 cursor-not-allowed" : ""}`}
        />
      </div>

      {/* Content */}
      <div className="px-6 pb-6">
        {/* ✅ WASTAGE TAB */}
        {activeReport === "Wastage Reports" ? (
          <WastageReportView
            period={period}
            startDate={startDate}
            endDate={endDate}
          />
        ) : loading ? (
          /* ✅ LOADING ONLY FOR SALES TAB */
          <div className="text-center py-[60px] text-gray-400 text-base">
            Loading...
          </div>
        ) : (
          /* ✅ SALES DASHBOARD */
          <>
            {/* Stat Cards */}
            <div className="flex flex-wrap gap-4 mb-5">
              <StatCard
                icon={ShoppingCart}
                iconBg="#f97316"
                label="Total Orders"
                value={summary?.totalOrders || 0}
              />
              <StatCard
                icon={IndianRupee}
                iconBg="#22c55e"
                label="Revenue"
                value={summary?.totalRevenue || 0}
                prefix="₹"
              />
              <StatCard
                icon={TrendingUp}
                iconBg="#3b82f6"
                label="Profit"
                value={summary?.profit || 0}
                prefix="₹"
              />
              <StatCard
                icon={Package}
                iconBg="#ef4444"
                label="Cost"
                value={summary?.totalCost || 0}
                prefix="₹"
              />
              {/* <StatCard icon={TrendingUp} iconBg="#8b5cf6" label="Net Profit" value={summary?.netProfit || 0} prefix="₹" /> */}
            </div>

            {/* Charts */}
            <div className="flex flex-wrap gap-4 mb-5">
              {/* Bar Chart */}
              <div className="flex-1 min-w-[320px] bg-white dark:bg-[#020617] rounded-xl p-5 border border-gray-200 dark:border-gray-800">
                <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-10">
                  Order Volume Trends
                </h3>

                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={trends}>
                    <XAxis
                      dataKey="label"
                      interval={
                        trends.length > 30 ? 4 : trends.length > 15 ? 2 : 0
                      }
                      angle={-45}
                      textAnchor="end"
                      height={60}
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis />
                    <Tooltip content={<BarTooltip />} />
                    <Bar dataKey="order_count" fill="#f97316" />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Pie Chart */}
              <div className="flex-1 min-w-[300px] bg-white dark:bg-[#020617] rounded-xl p-5 border border-gray-200 dark:border-gray-800">
                <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-10">
                  Sales By Category
                </h3>

                <ResponsiveContainer width="100%" height={320}>
                  <PieChart>
                    <Pie
                      data={categories}
                      dataKey="value"
                      outerRadius={80}
                      label={PieLabel}
                      labelLine={false}
                    >
                      {categories.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend
                      verticalAlign="bottom"
                      wrapperStyle={{
                        maxHeight: "80px",
                        overflowY: "auto",
                        paddingTop: "10px",
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div
              className="bg-white dark:bg-[#020617] 
  rounded-xl p-5 
  border border-gray-200 dark:border-gray-800"
            >
              {/* Header */}
              <div className="flex justify-between items-center mb-1">
                <h3 className="text-sm font-bold text-gray-900 dark:text-white">
                  Top Performing Dishes
                </h3>

                {topDishesLoading && (
                  <span className="text-xs text-gray-400">Refreshing…</span>
                )}
              </div>

              <p className="text-xs text-gray-400 mb-4">
                Best selling items and performance metrics
              </p>

              {/* Column Headers */}
              <div className="flex items-center px-4 pb-2 border-b border-gray-200 dark:border-gray-800 mb-2">
                <span className="w-10 text-[11px] text-gray-400 font-semibold">
                  #
                </span>
                <span className="flex-1 text-[11px] text-gray-400 font-semibold">
                  DISH
                </span>
                <span className="w-[100px] text-[11px] text-gray-400 font-semibold text-right">
                  UNITS SOLD
                </span>
                <span className="w-[120px] text-[11px] text-gray-400 font-semibold text-right">
                  REVENUE
                </span>
              </div>

              {/* ERROR */}
              {topDishesError && (
                <div className="flex justify-between items-center bg-red-50 border border-red-200 text-red-600 px-4 py-3 rounded-md text-sm">
                  <span>⚠️ {topDishesError}</span>

                  <button
                    onClick={() => loadTopDishes(period, startDate, endDate)}
                    className="bg-red-600 text-white px-3 py-1 rounded text-xs font-semibold"
                  >
                    Retry
                  </button>
                </div>
              )}

              {/* LOADING SHIMMER */}
              {topDishesLoading &&
                !topDishesError &&
                topDishes.length === 0 && (
                  <div className="flex flex-col gap-3">
                    {[1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className="h-12 rounded-md bg-gradient-to-r from-gray-200 via-gray-300 to-gray-200 animate-pulse"
                      />
                    ))}
                  </div>
                )}

              {/* DATA */}
              {/* DATA */}
              {!topDishesError && (
                <div className="max-h-[260px] overflow-y-auto pr-1 flex flex-col gap-2">
                  {topDishes.map((dish) => (
                    <div
                      key={dish.dish_id ?? dish.rank}
                      className={`flex items-center px-4 py-2 rounded-md border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#0f172a]
        hover:bg-gray-100 dark:hover:bg-[#1e293b] transition
        ${topDishesLoading ? "opacity-50" : ""}`}
                    >
                      {/* Rank Circle */}
                      <div
                        className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white mr-3
            ${
              dish.rank === 1
                ? "bg-orange-500"
                : dish.rank === 2
                  ? "bg-indigo-500"
                  : dish.rank === 3
                    ? "bg-green-500"
                    : "bg-gray-400"
            }`}
                      >
                        {dish.rank}
                      </div>

                      {/* Name */}
                      <div className="flex-1">
                        <div className="text-gray-900 dark:text-white">
                          {capitalizeWords(dish.name)}
                        </div>
                        <div className="text-gray-400 dark:text-gray-500">
                          {capitalizeWords(dish.subtitle)}
                        </div>
                      </div>

                      {/* Units */}
                      <div className="w-[100px] text-right text-sm text-gray-900 dark:text-white">
                        {(dish.unitsSold || 0).toLocaleString("en-IN")} units
                      </div>

                      {/* Revenue */}
                      <div className="w-[120px] text-right text-sm font-bold text-gray-900 dark:text-white">
                        ₹{(dish.revenue || 0).toLocaleString("en-IN")}
                      </div>
                    </div>
                  ))}

                  {/* Empty */}
                  {!topDishesLoading && topDishes.length === 0 && (
                    <div className="text-center py-6 text-gray-400 text-sm">
                      No dish data available for this period.
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ReportAndAnalysisTab;
