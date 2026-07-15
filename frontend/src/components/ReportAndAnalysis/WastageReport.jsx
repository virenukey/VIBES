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

/* ================= SAME API FUNCTIONS (UNCHANGED) ================= */
// (KEEP YOUR API FUNCTIONS EXACTLY SAME — NO CHANGE)

/* ================= HELPERS ================= */

const ErrorBanner = ({ message, onRetry, small = false }) => (
  <div
    className={`flex justify-between items-center border rounded-md
    ${small ? "px-3 py-2 text-xs" : "px-4 py-3 text-sm"}
    bg-red-50 border-red-200 text-red-600`}
  >
    <span>⚠️ {message}</span>

    <button
      onClick={onRetry}
      className={`bg-red-600 text-white rounded font-semibold
        ${small ? "px-2 py-1 text-xs" : "px-3 py-1 text-sm"}`}
    >
      Retry
    </button>
  </div>
);

const RADIAN = Math.PI / 180;

const WastagePieLabel = ({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  percent,
}) => {
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
const fetchWastageSummary = async (
  period,
  startDate = null,
  endDate = null,
) => {
  const params = { period };
  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/wastage/reports/wastage-summary", { params });
  const s = res.data.summary;

  return {
    totalWastageCost: s.total_wastage_cost,
    totalRecords: s.total_records,
    avgDailyLoss: s.avg_daily_loss,
    totalInventoryLoss: s.total_inventory_loss,
    costChangePct: s.vs_last_period?.total_cost_change_pct ?? null,
    recordsChangePct: s.vs_last_period?.total_records_change_pct ?? null,
  };
};

// Trend
const fetchWastageTrend = async (period, startDate = null, endDate = null) => {
  const params = { period };
  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/wastage/reports/wastage-trend", { params });
  return res.data.trends || [];
};

// Reason
const REASON_COLORS = [
  "#f97316",
  "#ef4444",
  "#6366f1",
  "#eab308",
  "#22c55e",
  "#14b8a6",
  "#ec4899",
  "#3b82f6",
];

const fetchWastageByReason = async (
  period,
  startDate = null,
  endDate = null,
) => {
  const params = { period };
  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/wastage/reports/wastage-by-reason", { params });

  return (res.data.by_reason || []).map((r, i) => ({
    name: r.reason,
    value: r.percentage,
    count: r.count,
    total_cost: r.total_cost,
    color: REASON_COLORS[i % REASON_COLORS.length],
  }));
};

// Top Items
const fetchTopWastageItems = async (
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

  const res = await api.get("/wastage/reports/top-wastage-items", { params });

  return (res.data.top_wastage_items || []).map((item) => ({
    rank: item.rank,
    name: item.item_name,
    type: item.wastage_type,
    qty: `${item.total_qty} ${item.unit}`,
    price: item.total_cost,
  }));
};

// Perishable
const fetchWastagePerishable = async (
  period,
  startDate = null,
  endDate = null,
) => {
  const params = { period };

  if (period === "custom") {
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
  }

  const res = await api.get("/wastage/reports/wastage-by-item-type", {
    params,
  });

  return (res.data.trends || []).map((row) => ({
    label: row.label,
    perishable: row.perishable,
    nonPerishable: row.non_perishable,
  }));
};

/* ================= MAIN ================= */

const WastageReportView = ({ period, startDate, endDate }) => {
  const [summary, setSummary] = useState(null);
  const [trendData, setTrendData] = useState([]);
  const [reasonData, setReasonData] = useState([]);
  const [topItems, setTopItems] = useState([]);
  const [perishableData, setPerishableData] = useState([]);

  const [loading, setLoading] = useState(true);

  const [summaryError, setSummaryError] = useState(null);
  const [trendError, setTrendError] = useState(null);
  const [reasonError, setReasonError] = useState(null);
  const [topItemsError, setTopItemsError] = useState(null);
  const [perishableError, setPerishableError] = useState(null);

  const load = async () => {
    // ❌ STOP if custom but no dates
    if (period === "custom" && (!startDate || !endDate)) {
      return;
    }

    setLoading(true);

    try {
      const [summaryRes, trendRes, reasonRes, topItemsRes, perishableRes] =
        await Promise.allSettled([
          fetchWastageSummary(period, startDate, endDate),
          fetchWastageTrend(period, startDate, endDate),
          fetchWastageByReason(period, startDate, endDate),
          fetchTopWastageItems(period, startDate, endDate, 10),
          fetchWastagePerishable(period, startDate, endDate),
        ]);

      if (summaryRes.status === "fulfilled") setSummary(summaryRes.value);
      if (trendRes.status === "fulfilled") setTrendData(trendRes.value);
      if (reasonRes.status === "fulfilled") setReasonData(reasonRes.value);
      if (topItemsRes.status === "fulfilled") setTopItems(topItemsRes.value);
      if (perishableRes.status === "fulfilled")
        setPerishableData(perishableRes.value);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (period !== "custom") {
      load();
    }
  }, [period]);

  useEffect(() => {
    if (period === "custom" && startDate && endDate) {
      load();
    }
  }, [startDate, endDate]);

  /* ================= LOADING ================= */

  if (loading) {
    return (
      <div className="text-center py-16 text-gray-400 text-base">
        Loading...
      </div>
    );
  }

  if (summaryError) {
    return <ErrorBanner message={summaryError} onRetry={load} />;
  }

  /* ================= STAT CARDS ================= */

  const statCards = [
    {
      label: "Total Wastage Cost",
      value: `₹${(summary?.totalWastageCost || 0).toLocaleString("en-IN")}`,
      icon: IndianRupee,
      bg: "bg-green-500",
    },
    {
      label: "Total Dish Loss",
      value: summary?.totalRecords || 0,
      icon: ShoppingCart,
      bg: "bg-orange-500",
    },
    {
      label: "Avg. Daily Loss",
      value: `₹${(summary?.avgDailyLoss || 0).toLocaleString("en-IN")}`,
      icon: TrendingUp,
      bg: "bg-blue-500",
    },
    {
      label: "Total Inventory Loss",
      value: `₹${(summary?.totalInventoryLoss || 0).toLocaleString("en-IN")}`,
      icon: Package,
      bg: "bg-red-500",
    },
  ];

  if (!summary) {
    return <div className="text-center py-16 text-gray-400">Loading...</div>;
  }

  return (
    <div className="space-y-5">
      {/* Stat Cards */}
      <div className="flex flex-wrap gap-4">
        {statCards.map((card, i) => {
          const Icon = card.icon;
          return (
            <div
              key={i}
              className="flex-1 min-w-[160px] bg-white dark:bg-[#020617]
              border border-gray-200 dark:border-gray-800 rounded-xl px-5 py-4 flex flex-col gap-2"
            >
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  {card.label}
                </span>

                <div className={`${card.bg} p-2 rounded-lg`}>
                  <Icon size={16} className="text-white" />
                </div>
              </div>

              <span className="text-xl font-bold text-gray-900 dark:text-white">
                {card.value}
              </span>
            </div>
          );
        })}
      </div>

      {/* Charts Row */}
      <div className="flex flex-wrap gap-4">
        {/* Trend Chart */}
        <div
          className="flex-1 min-w-[320px] bg-white dark:bg-[#020617]
          border border-gray-200 dark:border-gray-800 rounded-xl p-5"
        >
          <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-10 ">
            Wastage Trend
          </h3>

          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={trendData}>
              <XAxis
                dataKey="label"
                interval={
                  trendData.length > 60
                    ? 6
                    : trendData.length > 30
                      ? 4
                      : trendData.length > 15
                        ? 2
                        : 0
                }
                angle={-45}
                textAnchor="end"
                height={70}
                tick={{ fontSize: 11 }}
              />
              <YAxis />
              <Tooltip />
              <Bar dataKey="wastage_count" fill="#f97316" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Reason Pie */}
        <div
          className="flex-1 min-w-[300px] bg-white dark:bg-[#020617]
          border border-gray-200 dark:border-gray-800 rounded-xl p-5"
        >
          <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-2 ">
            Wastage by Reason
          </h3>

          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={reasonData}
                dataKey="value"
                outerRadius={80}
                label={WastagePieLabel}
                labelLine={false}
              >
                {reasonData.map((e, i) => (
                  <Cell key={i} fill={e.color} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bottom Row */}
      <div className="flex flex-wrap gap-4">
        {/* Top Items */}
        <div
          className="flex-1 min-w-[300px] bg-white dark:bg-[#020617]
          border border-gray-200 dark:border-gray-800 rounded-xl p-5"
        >
          <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-5">
            Top Wastage Items
          </h3>

          {/* Header Row */}
          <div className="flex items-center px-4 pb-2 border-b border-gray-200 dark:border-gray-800 mb-2">
            <span className="w-10 text-xs text-gray-400 dark:text-gray-500 font-semibold">
              #
            </span>
            <span className="flex-1 text-xs text-gray-400 dark:text-gray-500 font-semibold">
              ITEM
            </span>
            <span className="w-[100px] text-xs text-gray-400 dark:text-gray-500 font-semibold text-right">
              QTY
            </span>
            <span className="w-[120px] text-xs text-gray-400 dark:text-gray-500 font-semibold text-right">
              COST
            </span>
          </div>

          {/* Scrollable Container */}
          <div className="max-h-[260px] overflow-y-auto pr-1">
            {topItems.map((item) => (
              <div
                key={item.rank}
                className="flex items-center px-4 py-3 rounded-lg border border-gray-200 dark:border-gray-800
      bg-gray-50 dark:bg-[#0f172a] mb-2
      hover:bg-gray-100 dark:hover:bg-[#1e293b] transition"
              >
                {/* Rank Circle */}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white mr-3
          ${
            item.rank === 1
              ? "bg-orange-500"
              : item.rank === 2
                ? "bg-indigo-500"
                : item.rank === 3
                  ? "bg-green-500"
                  : "bg-gray-400"
          }`}
                >
                  {item.rank}
                </div>

                {/* Name */}
                <div className="flex-1">
                  <div className="text-sm font-semibold text-gray-900 dark:text-white">
                    {item.name}
                  </div>
                  <div className="text-xs text-gray-400 dark:text-gray-500 capitalize">
                    {item.type}
                  </div>
                </div>

                {/* Qty */}
                <div className="w-[100px] text-right text-sm text-gray-600 dark:text-gray-300">
                  {item.qty}
                </div>

                {/* Cost */}
                <div className="w-[120px] text-right text-sm font-bold text-gray-900 dark:text-white">
                  ₹{(item.price || 0).toLocaleString("en-IN")}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Perishable Chart */}
        <div
          className="flex-1 min-w-[300px] bg-white dark:bg-[#020617]
          border border-gray-200 dark:border-gray-800 rounded-xl p-5"
        >
          <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-10 ">
            Perishable vs Non-Perishable
          </h3>

          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={perishableData}>
              <XAxis
                dataKey="label"
                interval={
                  perishableData.length > 60
                    ? 6
                    : perishableData.length > 30
                      ? 4
                      : perishableData.length > 15
                        ? 2
                        : 0
                }
                angle={-45}
                textAnchor="end"
                height={70}
                tick={{ fontSize: 11 }}
              />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="perishable" fill="#f97316" barSize={12} />

              <Bar dataKey="nonPerishable" fill="#fbbf24" barSize={12} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
};

export default WastageReportView;
