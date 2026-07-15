import { useState, useRef } from "react";
import {
  FiColumns,
  FiFilter,
  FiPlus,
  FiFileText,
  FiChevronDown,
  FiChevronLeft,
  FiChevronRight,
  FiChevronRight as RowClosed,
  FiChevronDown as RowOpen,
  FiEdit,
  FiTrash2,
  FiPlusSquare,
  FiExternalLink,
  FiArrowUp,
  FiArrowDown,
  FiMinus,
} from "react-icons/fi";
import { FiSearch } from "react-icons/fi";
import { toast } from "react-toastify";
import PageHeader from "../PageHeader";
import AddItemModal from "./AddItemModal";
import AddBatchModal from "./AddBatchModal";
import { useNavigate } from "react-router-dom";
import StorageTab from "./StorageTab";
import CategoryTab from "./CategoryTab";
import AddExcelModal from "./AddExcelModal";
import { useEffect } from "react";
import api from "../../api/axios";
import { capitalizeWords } from "../../utils/text";

export default function InventoryTab() {
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const [showCustomize, setShowCustomize] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showBatchModal, setShowBatchModal] = useState(false);
  const [selectedItem, setSelectedItem] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [activeTab, setActiveTab] = useState("inventory");
  const [searchText, setSearchText] = useState("");
  const [showExcelModal, setShowExcelModal] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);
  const [showBatchExcelModal, setShowBatchExcelModal] = useState(false);
  const [showDownloadModal, setShowDownloadModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteItemId, setDeleteItemId] = useState(null);
  const [expandedRows, setExpandedRows] = useState({});
  const [itemBatches, setItemBatches] = useState({});
  const customizeRef = useRef(null);
  const [filters, setFilters] = useState({
    category_type: "",
    fromDate: "",
    toDate: "",
  });

  const [sortConfig, setSortConfig] = useState({
    key: null,
    direction: null,
  });

  const [editItemData, setEditItemData] = useState(null);
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [editBatchData, setEditBatchData] = useState(null);
  const [deleteBatchData, setDeleteBatchData] = useState(null);
  const [showBatchDeleteModal, setShowBatchDeleteModal] = useState(false);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        customizeRef.current &&
        !customizeRef.current.contains(event.target)
      ) {
        setShowCustomize(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);
  const toggleRow = async (itemId) => {
    const isOpen = expandedRows[itemId];

    setExpandedRows((prev) => ({
      ...prev,
      [itemId]: !prev[itemId],
    }));

    // only fetch batches first time
    if (!isOpen && !itemBatches[itemId]) {
      try {
        const res = await api.get(`/inventory/items/${itemId}/batches`);

        setItemBatches((prev) => ({
          ...prev,
          [itemId]: res.data.data || [],
        }));
      } catch (err) {
        console.error("Failed to fetch batches", err);
      }
    }
  };

  const getLatestBatchDate = (itemId) => {
  const batches = itemBatches[itemId] || [];

  if (batches.length === 0) return null;

  const latestBatch = [...batches].sort(
    (a, b) => new Date(b.date_added) - new Date(a.date_added)
  );

  return latestBatch[0].date_added;
};

  const fetchInventoryItems = async () => {
    try {
      setLoadingItems(true);

      const params = {
        page: currentPage,
        page_size: rowsPerPage,
      };

      if (typeFilter !== "ALL") {
        params.category_type = typeFilter.toLowerCase();
      }

      if (searchText) params.search = searchText;
      if (filters.category_type) params.category_type = filters.category_type;

      // Backend sorting
      if (sortConfig.key) {
        const sortKeyMap = {
          quantity: "quantity",
          value: "total_cost",
        };

        params.sort_by = sortKeyMap[sortConfig.key];
        params.sort_order = sortConfig.direction || "asc";
      }

      let itemsData = [];

      // STEP 1: Always fetch inventory FIRST
      const res = await api.get("/inventory/", { params });
      console.log("Requested data:",res.data);
      itemsData = res.data.data || [];
     
   // backend pagination
      setTotalPages(res.data.meta?.total_pages || 1);

      //  STEP 2: If NO date filter → normal flow
      if (!filters.fromDate && !filters.toDate) {
        setItems(itemsData);
        fetchBatchesForItems(itemsData);
        return;
      }

      //  STEP 3: Date filter flow
      const batchRes = await api.get("/inventory/filter/get-all-batches", {
        params: {
          date_from: filters.fromDate || undefined,
          date_to: filters.toDate || undefined,
        },
      });

      const batches = batchRes.data.data || [];

      //  Map batches
      const batchMap = {};
      batches.forEach((b) => {
        const itemId = Number(b.inventory_item_id);

        if (!batchMap[itemId]) {
          batchMap[itemId] = [];
        }

        batchMap[itemId].push(b);
      });

      //  Filter items
      const filteredItems = itemsData.filter((item) => batchMap[item.id]);

      setItems(filteredItems);
      setItemBatches(batchMap);
    } catch (err) {
      console.error("Fetch error:", err);

      const error = err.response?.data?.detail;

      if (Array.isArray(error)) {
        toast.error(error[0]?.msg || "Error ❌");
      } else {
        toast.error(error || "Something went wrong ❌");
      }

      setItems([]);
    } finally {
      setLoadingItems(false);
    }
  };
  const fetchBatchesForItems = async (itemsList) => {
    try {
     const batchPromises = itemsList.map((item) => {
  const params = {};

  if (sortConfig.key === "date") {
    params.date_added_order = sortConfig.direction;
  }

  if (sortConfig.key === "expiry") {
    params.expiry_date_order = sortConfig.direction;
  }

  return api.get(`/inventory/items/${item.id}/batches`, { params });
});
      const results = await Promise.all(batchPromises);

      const batchMap = {};
      results.forEach((res, index) => {
        const itemId = itemsList[index].id;
        batchMap[itemId] = res.data.data || [];
      });
    
      if (sortConfig.key === "date") {
  itemsList.sort((a, b) => {
    const dateA = batchMap[a.id]?.[0]?.date_added;
    const dateB = batchMap[b.id]?.[0]?.date_added;

    if (!dateA && !dateB) return 0;
    if (!dateA) return 1;
    if (!dateB) return -1;

    return sortConfig.direction === "asc"
      ? new Date(dateA) - new Date(dateB)
      : new Date(dateB) - new Date(dateA);
  });

  setItems([...itemsList]);
}

if (sortConfig.key === "expiry") {
  itemsList.sort((a, b) => {
    const resultA = getNearestExpiryDate(a.id);
    const resultB = getNearestExpiryDate(b.id);

    const expiryA = resultA?.date;
    const expiryB = resultB?.date;

    if (!expiryA && !expiryB) return 0;
    if (!expiryA) return 1;
    if (!expiryB) return -1;

    return sortConfig.direction === "asc"
      ? new Date(expiryA) - new Date(expiryB)
      : new Date(expiryB) - new Date(expiryA);
  });

  setItems([...itemsList]);
}

      setItemBatches(batchMap);
    } catch (err) {
      console.error("Failed to preload batches", err);
    }
  };

  useEffect(() => {
    fetchInventoryItems();
  }, [
    currentPage,
    rowsPerPage,
    searchText,
    filters.fromDate,
    filters.toDate,
    filters.category_type,
    sortConfig,
    typeFilter,
  ]);

  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setFilters((prev) => ({ ...prev, [name]: value }));
  };

  const handleResetFilters = () => {
    setFilters({
      category_type: "",
      fromDate: "",
      toDate: "",
    });

    setSearchText("");
    setCurrentPage(1);
  };

  const tabs = [
    // { key: "category", label: "Category Addition" },
    { key: "storage", label: "Storage" },
    { key: "inventory", label: "Inventory Management" },
  ];

  const navigate = useNavigate();

  const allColumns = [
    { key: "name", label: "Item Name" },
    { key: "category", label: "Category" },
    { key: "quantity", label: "Quantity" },
    { key: "value", label: "Total Value" },
    { key: "storage", label: "Storage" },
    { key: "date", label: "Stock Added Date" },
    { key: "expiry", label: "Expiry Date" },
    { key: "batch", label: "Batch" },
    { key: "edit", label: "Edit" },
    { key: "delete", label: "Delete" },
  ];

  const [visibleColumns, setVisibleColumns] = useState(
    allColumns.map((c) => c.key),
  );

  const toggleColumn = (key) => {
    setVisibleColumns((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  };

  const getItemValueFromBatches = (item) => {
    const batches = itemBatches[item.id] || [];

    return batches.reduce((total, batch) => {
      if (batch.is_active === false) return total;
      if (batch.expiry_date) {
        const today = new Date();
        const expiry = new Date(batch.expiry_date);

        today.setHours(0, 0, 0, 0);
        expiry.setHours(0, 0, 0, 0);

        if (expiry < today) {
          return total;
        }
      }

      return total + Number(batch.total_cost || 0);
    }, 0);
  };

  const getNearestExpiryDate = (itemId) => {
    const batches = itemBatches[itemId] || [];

    if (batches.length === 0) return null;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const withExpiry = batches.filter((b) => b.expiry_date);

    if (withExpiry.length === 0) return null;

    // ✅ Separate expired and non-expired
    const nonExpired = withExpiry.filter(
      (b) => new Date(b.expiry_date) >= today,
    );

    const expired = withExpiry.filter((b) => new Date(b.expiry_date) < today);

    // ✅ Case 1 → future batches exist → pick nearest upcoming
    if (nonExpired.length > 0) {
      const sorted = nonExpired.sort(
        (a, b) => new Date(a.expiry_date) - new Date(b.expiry_date),
      );
      return { date: sorted[0].expiry_date, isExpired: false };
    }

    // ❌ Case 2 → all expired → show latest expired
    const sortedExpired = expired.sort(
      (a, b) => new Date(b.expiry_date) - new Date(a.expiry_date),
    );

    return { date: sortedExpired[0].expiry_date, isExpired: true };
  };
  const handleSort = (key) => {
    setCurrentPage(1);
    setSortConfig((prev) => {
      if (prev.key !== key) {
        return { key, direction: "asc" }; // first click → asc
      }

      if (prev.direction === "asc") {
        return { key, direction: "desc" }; // second → desc
      }

      return { key: null, direction: null }; // third → reset
    });
  };

  // Apply Perishable / Non-Perishable filter FIRST
  const typeFilteredItems = items;

  // console.log(
  //   "TABLE DATA",
  //   typeFilteredItems.map((i) => ({
  //     name: i.name,
  //     category_type: i.category_type,
  //   })),
  // );

  const handleSearch = (e) => {
    setSearchText(e.target.value);
    setCurrentPage(1);
  };

  const handleDeleteItem = async () => {
    try {
      await api.delete(`/inventory/${deleteItemId}`);
      toast.success("Item deleted successfully 🗑️");

      fetchInventoryItems();

      setShowDeleteModal(false);
      setDeleteItemId(null);
    } catch (err) {
      console.error("Failed to delete item", err);

      const errorMessage =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        "Failed to delete item ❌";

      toast.error(errorMessage);
    }
  };

  const getItemQuantityFromBatches = (item) => {
    const batches = itemBatches[item.id] || [];

    return batches.reduce((total, batch) => {
      if (batch.expiry_date) {
        const today = new Date();
        const expiry = new Date(batch.expiry_date);

        today.setHours(0, 0, 0, 0);
        expiry.setHours(0, 0, 0, 0);

        if (expiry < today) {
          return total;
        }
      }

      return total + Number(batch.quantity_remaining || 0);
    }, 0);
  };

  const handleDeleteBatch = async () => {
    try {
      await api.delete(
        `/inventory/items/${deleteBatchData.itemId}/delete-batch-by-id/${deleteBatchData.batchId}`,
      );
      toast.success("Batch deleted successfully 🗑️");

      fetchInventoryItems();
      setItemBatches({});

      setShowBatchDeleteModal(false);
      setDeleteBatchData(null);
    } catch (err) {
      const error =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        "Failed to delete batch ❌";

      toast.error(error);
    }
  };

  return (
    <div className="w-full max-w-full overflow-x-hidden z-index-full">
      <div
        className="bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm 
overflow-hidden max-h-[100vh] overflow-y-auto"
      >
        {/* Header */}
        <PageHeader
          title="Inventory Management"
          tabs={tabs}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
        />

        {activeTab === "inventory" && (
          <div className="flex flex-wrap justify-between items-center gap-3 px-4 py-3">
            {/* LEFT SIDE */}
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => {
                  setTypeFilter("ALL");
                  setCurrentPage(1);
                }}
                className={`px-4 py-1 rounded-md text-sm font-medium transition ${
                  typeFilter === "ALL"
                    ? "bg-[#9AF288] text-black"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200"
                }`}
              >
                All Items
              </button>

              <button
                onClick={() => {
                  setTypeFilter("PERISHABLE");
                  setCurrentPage(1);
                }}
                className={`px-4 py-1 rounded-md text-sm font-medium transition ${
                  typeFilter === "PERISHABLE"
                    ? "bg-[#9AF288] text-black"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200"
                }`}
              >
                Perishable
              </button>

              <button
                onClick={() => {
                  setTypeFilter("NON_PERISHABLE");
                  setCurrentPage(1);
                }}
                className={`px-4 py-1 rounded-md text-sm font-medium transition ${
                  typeFilter === "NON_PERISHABLE"
                    ? "bg-[#9AF288] text-black"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-200"
                }`}
              >
                Non-Perishable
              </button>
            </div>

            {/* RIGHT SIDE */}
            <button
              onClick={() => setShowDownloadModal(true)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg 
    bg-gradient-to-r from-orange-500 to-orange-600 
    text-white text-sm font-semibold 
    shadow-md hover:shadow-lg hover:scale-[1.02] 
    transition-all duration-200"
            >
              <FiFileText className="text-lg" />
              Download Excel Format
            </button>
          </div>
        )}

        {activeTab === "inventory" && (
          <>
            {/* Toolbar */}
            <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3 px-1 sm:px-2 py-4">
              {/* Left */}
              <div className="flex flex-wrap items-center gap-3">
                {/* Customize Columns */}
                <div className="relative" ref={customizeRef}>
                  <button
                    onClick={() => setShowCustomize(!showCustomize)}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0f172a] text-sm font-medium text-gray-800 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                  >
                    <FiColumns className="text-lg" />
                    Customize Columns
                    <FiChevronDown className="text-lg" />
                  </button>

                  {showCustomize && (
                    <div
                      className="absolute z-[9999] mt-2 w-64 rounded-lg
                                border border-gray-200 dark:border-gray-700
                                bg-white dark:bg-[#0f172a]
                                shadow-xl p-2
                                max-h-[280px] overflow-y-auto"
                    >
                      <p className="text-xs text-gray-500 dark:text-gray-400 px-2 py-1">
                        Select Columns
                      </p>

                      {allColumns.map((col) => (
                        <label
                          key={col.key}
                          className="flex items-center gap-2 px-2 py-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={visibleColumns.includes(col.key)}
                            onChange={() => toggleColumn(col.key)}
                            className="accent-orange-500"
                          />
                          <span className="text-sm text-gray-800 dark:text-gray-200">
                            {col.label}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>

                {/* Filters */}
                <button
                  onClick={() => setShowFilters(!showFilters)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition
    ${
      showFilters
        ? "bg-[#9AF288] text-black border-[#9AF288]"
        : "border-gray-200 dark:border-gray-700 bg-white dark:bg-[#0f172a] text-gray-800 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800"
    }`}
                >
                  <FiFilter className="text-lg" />
                  Filters
                </button>

                <button
                  onClick={() => setShowBatchExcelModal(true)}
                  className=" flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 
              bg-orange-500 dark:bg-orange-500 text-sm font-medium text-white dark:text-gray-200 
              hover:bg-orange-600 dark:hover:bg-orange-600 transition cursor-pointer "
                >
                  <FiFileText className="text-lg" />
                  Add Stock via Excel
                </button>
              </div>
              {/* Right */}
              <div className="flex flex-wrap items-center gap-3 justify-start xl:justify-end">
                {/*  Search Bar */}
                <div className="relative group">
                  <FiSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg" />

                  <input
                    type="text"
                    placeholder="Search item..."
                    value={searchText}
                    onChange={handleSearch}
                    className="w-64 sm:w-72 pl-10 pr-4 py-2 rounded-xl 
    border-[2.5px] border-orange-400
    bg-white dark:bg-[#0f172a] 
    text-sm text-gray-800 dark:text-gray-200
    shadow-sm hover:shadow-md
    outline-none
    transition-all duration-200"
                  />
                </div>

                <button
                  onClick={() => setShowAddModal(true)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition
                  ${
                    showAddModal
                      ? "bg-orange-500 text-white border-orange-500"
                      : "bg-white dark:bg-[#0f172a] text-gray-800 dark:text-gray-200 border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
                  }`}
                >
                  <FiPlus className="text-lg" />
                  Add Item
                </button>

                <button
                  onClick={() => setShowExcelModal(true)}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 
                            bg-white dark:bg-[#0f172a] text-sm font-medium text-gray-800 dark:text-gray-200 
                            hover:bg-gray-50 dark:hover:bg-gray-800 transition"
                >
                  <FiFileText className="text-lg" />
                  Add via excel
                </button>
              </div>
            </div>

            {/* Filter Section */}
            {showFilters && (
              <div className="px-4 sm:px-6 pb-4">
                <div className="w-full bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                  <div className="flex flex-col lg:flex-row gap-4 items-end">
                    {/* Status */}
                    {/* <div className="w-full lg:w-[200px]">
                    <label className="text-xs font-semibold text-gray-600 dark:text-gray-300">
                        Status
                    </label>
                    <select
                        name="status"
                        value={filters.status}
                        onChange={handleFilterChange}
                        className="mt-2 w-full px-4 py-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#0f172a] text-sm text-gray-800 dark:text-gray-200 outline-none"
                    >
                        <option value="">Status</option>
                        <option value="fresh">Fresh</option>
                        <option value="near_expiry">Near Expiry</option>
                        <option value="expired">Expired</option>
                    </select>
                    </div> */}

                    {/* Date Range */}
                    <div className="w-full lg:w-auto">
                      <label className="text-xs font-semibold text-gray-600 dark:text-gray-300">
                        Date Range
                      </label>

                      <div className="mt-2 flex flex-wrap gap-3 items-center">
                        <input
                          type="date"
                          name="fromDate"
                          value={filters.fromDate}
                          onChange={handleFilterChange}
                          className="px-4 py-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#0f172a] text-sm text-gray-800 dark:text-gray-200 outline-none"
                        />

                        <input
                          type="date"
                          name="toDate"
                          value={filters.toDate}
                          onChange={handleFilterChange}
                          className="px-4 py-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-[#0f172a] text-sm text-gray-800 dark:text-gray-200 outline-none"
                        />
                      </div>
                    </div>

                    {/* Apply Button */}
                    <button
                      onClick={handleResetFilters}
                      className="px-8 py-2 rounded-md bg-yellow-400 hover:bg-yellow-500 text-black font-semibold transition"
                    >
                      Reset
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Inventory Table Card */}
            <div className="px-4 sm:px-6 pb-4">
              <div className="bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                  <table className="w-full text-sm">
                    {/* Header */}
                    <thead className="bg-gray-50 dark:bg-[#020617] border-b border-gray-200 dark:border-gray-800 sticky top-0 z-10">
                      {" "}
                      <tr>
                        {visibleColumns.includes("name") && (
                          <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                            Item Name
                          </th>
                        )}

                        {visibleColumns.includes("category") && (
                          <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                            Category
                          </th>
                        )}

                        {visibleColumns.includes("quantity") && (
                          <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                            <div className="flex items-center gap-1">
                              Quantity
                              {/* SINGLE DYNAMIC ARROW */}
                              <span
                                onClick={() => handleSort("quantity")}
                                className="cursor-pointer"
                              >
                                {sortConfig.key === "quantity" ? (
                                  sortConfig.direction === "asc" ? (
                                    <FiArrowUp className="text-orange-500" />
                                  ) : sortConfig.direction === "desc" ? (
                                    <FiArrowDown className="text-orange-500" />
                                  ) : (
                                    <FiMinus className="text-gray-400" />
                                  )
                                ) : (
                                  <FiMinus className="text-gray-400" />
                                )}
                              </span>
                            </div>
                          </th>
                        )}

                        {visibleColumns.includes("value") && (
                          <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                            <div className="flex items-center gap-1">
                              Total Value
                              <span
                                onClick={() => handleSort("value")}
                                className="cursor-pointer"
                              >
                                {sortConfig.key === "value" ? (
                                  sortConfig.direction === "asc" ? (
                                    <FiArrowUp className="text-orange-500" />
                                  ) : sortConfig.direction === "desc" ? (
                                    <FiArrowDown className="text-orange-500" />
                                  ) : (
                                    <FiMinus className="text-gray-400" />
                                  )
                                ) : (
                                  <FiMinus className="text-gray-400" />
                                )}
                              </span>
                            </div>
                          </th>
                        )}

                        {visibleColumns.includes("storage") && (
                          <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                            Storage
                          </th>
                        )}

                        {visibleColumns.includes("date") && (
                          <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                            <div className="flex items-center justify-center gap-1">
                              Recent Stock Added Date
                              <span
                                onClick={() => handleSort("date")}
                                className="cursor-pointer"
                              >
                                {sortConfig.key === "date" ? (
                                  sortConfig.direction === "asc" ? (
                                    <FiArrowUp className="text-orange-500" />
                                  ) : sortConfig.direction === "desc" ? (
                                    <FiArrowDown className="text-orange-500" />
                                  ) : (
                                    <FiMinus className="text-gray-400" />
                                  )
                                ) : (
                                  <FiMinus className="text-gray-400" />
                                )}
                              </span>
                            </div>
                          </th>
                        )}

                        {visibleColumns.includes("expiry") && (
                          <th className="px-6 py-3 text-left font-semibold text-gray-700 dark:text-gray-300">
                            <div className="flex items-center justify-center gap-1">
                              Expiry Date
                              <span
                                onClick={() => handleSort("expiry")}
                                className="cursor-pointer"
                              >
                                {sortConfig.key === "expiry" ? (
                                  sortConfig.direction === "asc" ? (
                                    <FiArrowUp className="text-orange-500" />
                                  ) : sortConfig.direction === "desc" ? (
                                    <FiArrowDown className="text-orange-500" />
                                  ) : (
                                    <FiMinus className="text-gray-400" />
                                  )
                                ) : (
                                  <FiMinus className="text-gray-400" />
                                )}
                              </span>
                            </div>
                          </th>
                        )}

                        {visibleColumns.includes("batch") && (
                          <th className="px-6 py-3 text-center font-semibold text-gray-700 dark:text-gray-300">
                            Add Stock
                          </th>
                        )}

                        {visibleColumns.includes("edit") && (
                          <th className="px-6 py-3 text-center font-semibold text-gray-700 dark:text-gray-300">
                            Edit
                          </th>
                        )}

                        {visibleColumns.includes("delete") && (
                          <th className="px-6 py-3 text-center font-semibold text-gray-700 dark:text-gray-300">
                            Delete
                          </th>
                        )}
                      </tr>
                    </thead>

                    <tbody>
                      {typeFilteredItems.map((item) => (
                        <>
                          <tr
                            key={item.id}
                            className="border-b border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#020617] transition"
                          >
                            {visibleColumns.includes("name") && (
                              <td className="px-6 py-4 font-medium text-gray-900 dark:text-gray-100">
                                <div className="flex items-center gap-2">
                                  <button
                                    onClick={() => toggleRow(item.id)}
                                    className="p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 transition"
                                  >
                                    {expandedRows[item.id] ? (
                                      <RowOpen className="text-gray-600 dark:text-gray-300" />
                                    ) : (
                                      <RowClosed className="text-gray-600 dark:text-gray-300" />
                                    )}
                                  </button>

                                  {/* Item Link */}
                                  <button className="flex items-center gap-2 hover:text-orange-500">
                                    {capitalizeWords(item.name)}
                                  </button>
                                </div>
                              </td>
                            )}

                            {/* Category */}
                            {visibleColumns.includes("category") && (
                              <td className="px-6 py-4">
                                <span
                                  className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium 
      bg-green-100 text-green-700 
      dark:bg-green-900/30 dark:text-green-300 
      whitespace-normal break-words"
                                >
                                  {item.category_type
                                    ? item.category_type === "perishable"
                                      ? "Perishable"
                                      : "Non-Perishable"
                                    : "—"}
                                </span>
                              </td>
                            )}

                            {/* Quantity */}
                            {visibleColumns.includes("quantity") && (
                              <td className="px-6 py-4 text-gray-800 dark:text-gray-200">
                                {`${item.quantity} ${item.unit}`}
                              </td>
                            )}

                            {/* Total Value */}
                            {visibleColumns.includes("value") && (
                              <td className="px-6 py-4 text-gray-800 dark:text-gray-200">
                                ₹{getItemValueFromBatches(item)}
                              </td>
                            )}

                            {/* Storage */}
                            {visibleColumns.includes("storage") && (
                              <td className="px-6 py-4 text-gray-800 dark:text-gray-200">
                                {capitalizeWords(item.storage_location)}
                              </td>
                            )}

                            {/* Date */}
                            {visibleColumns.includes("date") && (
                              <td className="px-6 py-4 text-gray-800 dark:text-gray-200">
                                <div className="w-full text-center">
                                  {(() => {
                                    const latestDate = getLatestBatchDate(
                                      item.id,
                                    );
                                    return latestDate
                                      ? new Date(latestDate).toLocaleDateString(
                                          "en-GB",
                                        )
                                      : "-";
                                  })()}
                                </div>
                              </td>
                            )}

                            {visibleColumns.includes("expiry") && (
                              <td className="px-6 py-4 text-center text-gray-800 dark:text-gray-200">
                                {(() => {
                                  const result = getNearestExpiryDate(item.id);

                                  if (!result || !result.date) return "-";

                                  const formatted = new Date(
                                    result.date,
                                  ).toLocaleDateString("en-GB");

                                  return (
                                    <span
                                      className={
                                        result.isExpired ? "text-red-600" : ""
                                      }
                                    >
                                      {formatted}
                                    </span>
                                  );
                                })()}
                              </td>
                            )}

                            {/* Batch */}
                            {visibleColumns.includes("batch") && (
                              <td className="px-6 py-4 text-center">
                                <button
                                  onClick={() => {
                                    setSelectedItem(item);
                                    setShowBatchModal(true);
                                  }}
                                  className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400 hover:bg-orange-200 dark:hover:bg-orange-900/40 transition text-xs"
                                >
                                  <FiPlus />
                                  Add Stock
                                </button>
                              </td>
                            )}

                            {/* Edit */}
                            {visibleColumns.includes("edit") && (
                              <td className="px-6 py-4 text-center">
                                <button
                                  onClick={() => {
                                    setEditItemData({
                                      ...item,

                                      item_category_id:
                                        item.item_category_id ||
                                        item.category_id,
                                      storage_location_id:
                                        item.storage_location_id ||
                                        item.storage_id,
                                    });

                                    setShowAddModal(true);
                                  }}
                                  className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
                                >
                                  <FiEdit className="text-gray-700 dark:text-gray-300" />
                                </button>
                              </td>
                            )}

                            {/* Delete */}
                            {visibleColumns.includes("delete") && (
                              <td className="px-6 py-4 text-center">
                                <button
                                  onClick={() => {
                                    setDeleteItemId(item.id);
                                    setShowDeleteModal(true);
                                  }}
                                  className="p-2 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition"
                                >
                                  <FiTrash2 className="text-red-600 dark:text-red-400" />
                                </button>
                              </td>
                            )}
                          </tr>

                          {/*  Batch Drawer Row */}
                          {expandedRows[item.id] && (
                            <tr className="bg-gray-50 dark:bg-[#020617]">
                              <td
                                colSpan={visibleColumns.length}
                                className="px-6 py-4"
                              >
                                <div className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                                  Batches
                                </div>

                                {(() => {
                                  const batches = itemBatches[item.id] || [];

                                  const validBatches = batches.filter(
                                    (batch) => {
                                      if (batch.is_active === false)
                                        return false;
                                      return true;
                                    },
                                  );
                                  const sortedBatches = [...validBatches].sort(
                                    (a, b) => {
                                      const aNum = Number(
                                        a.batch_number?.replace(/\D/g, ""),
                                      );
                                      const bNum = Number(
                                        b.batch_number?.replace(/\D/g, ""),
                                      );

                                      return aNum - bNum;
                                    },
                                  );

                                  if (validBatches.length === 0) {
                                    return (
                                      <div className="text-sm text-gray-500 dark:text-gray-400">
                                        No batches exist for this inventory item
                                      </div>
                                    );
                                  }

                                  return (
                                    <div className="flex flex-wrap gap-5">
                                      {sortedBatches.map((batch) => {
                                        const isBatchUsed =
                                          Number(batch.quantity_received) >
                                          Number(batch.quantity_remaining);

                                        return (
                                          <div
                                            key={batch.id}
                                            className={`w-[220px] border rounded-xl shadow-md hover:shadow-lg transition p-4 text-sm

                                             ${(() => {
                                               const today = new Date();
                                               const expiry = new Date(
                                                 batch.expiry_date,
                                               );

                                               today.setHours(0, 0, 0, 0);
                                               expiry.setHours(0, 0, 0, 0);

                                               return expiry < today
                                                 ? "bg-gray-200 text-gray-500 border-gray-300 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700"
                                                 : "bg-white dark:bg-[#0f172a] border-gray-200 dark:border-gray-800 text-gray-900 dark:text-white";
                                             })()}
`}
                                          >
                                            {/*  TOP ROW (NO GAP ISSUE) */}
                                            <div className="flex items-center justify-between">
                                              <div className="font-semibold text-gray-900 dark:text-white">
                                                {batch.batch_number}
                                              </div>

                                              {batch.lifecycle_stage && (
                                                <span
                                                  className={`px-2 py-1 rounded-full text-[10px] font-semibold whitespace-nowrap
                                                    ${
                                                      batch.lifecycle_stage ===
                                                      "fresh"
                                                        ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300"
                                                        : batch.lifecycle_stage ===
                                                            "near_expiry"
                                                          ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300"
                                                          : batch.lifecycle_stage ===
                                                              "expired"
                                                            ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
                                                            : "bg-gray-100 text-gray-700"
                                                    }`}
                                                >
                                                  {capitalizeWords(
                                                    batch.lifecycle_stage?.replace(
                                                      "_",
                                                      " ",
                                                    ),
                                                  )}
                                                </span>
                                              )}
                                            </div>

                                            {/* CONTENT + ACTIONS ROW */}
                                            <div className="flex justify-between mt-1">
                                              {/* LEFT CONTENT */}
                                              <div className="space-y-1 text-xs text-gray-600 dark:text-gray-400">
                                                <div>
                                                  Received:{" "}
                                                  {batch.quantity_received}{" "}
                                                  {batch.unit}
                                                </div>
                                                <div>
                                                  Remaining:{" "}
                                                  {batch.quantity_remaining}{" "}
                                                  {batch.unit}
                                                </div>
                                                <div>
                                                  Packets: {batch.packets}
                                                </div>
                                                <div>
                                                  Pieces: {batch.pieces}
                                                </div>
                                                {batch.pieces > 0 && (
                                                  <div>
                                                    Pieces Remaining:{" "}
                                                    {batch.pieces_remaining}
                                                  </div>
                                                )}
                                                <div>
                                                  Unit Cost: ₹{batch.unit_cost}/
                                                  {batch.unit}
                                                </div>

                                                {(batch.pieces > 0 ||
                                                  batch.unit === "packet") && (
                                                  <div>
                                                    Price / Piece: ₹
                                                    {batch.price_per_piece
                                                      ? batch.price_per_piece
                                                      : batch.total_cost &&
                                                          batch.total_pieces
                                                        ? (
                                                            batch.total_cost /
                                                            batch.total_pieces
                                                          ).toFixed(2)
                                                        : "-"}
                                                  </div>
                                                )}

                                                {batch.date_added && (
                                                  <div>
                                                    Added:{" "}
                                                    {new Date(
                                                      batch.date_added,
                                                    ).toLocaleDateString(
                                                      "en-GB",
                                                    )}
                                                  </div>
                                                )}

                                                {batch.expiry_date && (
                                                  <div className="text-orange-500">
                                                    Exp:{" "}
                                                    {new Date(
                                                      batch.expiry_date,
                                                    ).toLocaleDateString(
                                                      "en-GB",
                                                    )}
                                                  </div>
                                                )}
                                              </div>

                                              {/*  RIGHT ACTIONS*/}
                                              <div className="flex flex-col gap-2 ml-3">
                                                {/* EDIT */}
                                                <div className="relative group w-fit">
                                                  <button
                                                    onClick={() => {
                                                      if (isBatchUsed) return;

                                                      setSelectedItem(item);
                                                      setEditBatchData(batch);
                                                      setShowBatchModal(true);
                                                    }}
                                                    className={`p-1.5 rounded-md
                                                    ${
                                                      isBatchUsed
                                                        ? "bg-gray-200 opacity-50 cursor-not-allowed"
                                                        : "bg-gray-100 hover:bg-gray-200"
                                                    }`}
                                                  >
                                                    <FiEdit />
                                                  </button>

                                                  {/*  RIGHT SIDE TOOLTIP */}
                                                  {isBatchUsed && (
                                                    <div
                                                      className="absolute left-full ml-2 top-1/2 -translate-y-1/2
                                                        bg-black text-white text-xs px-2 py-1 rounded
                                                          opacity-0 group-hover:opacity-100 transition whitespace-nowrap z-50"
                                                    >
                                                      Cannot edit, stock has
                                                      been used
                                                    </div>
                                                  )}
                                                </div>
                                                {/* DELETE */}
                                                <div className="relative group w-fit">
                                                  <button
                                                    onClick={() => {
                                                      if (isBatchUsed) return;

                                                      setDeleteBatchData({
                                                        itemId: item.id,
                                                        batchId: batch.id,
                                                      });
                                                      setShowBatchDeleteModal(
                                                        true,
                                                      );
                                                    }}
                                                    className={`p-1.5 rounded-md
                                                    ${
                                                      isBatchUsed
                                                        ? "bg-red-100 opacity-50 cursor-not-allowed"
                                                        : "bg-red-100 hover:bg-red-200"
                                                    }`}
                                                  >
                                                    <FiTrash2 className="text-red-600" />
                                                  </button>

                                                  {isBatchUsed && (
                                                    <div
                                                      className="absolute left-full ml-2 top-1/2 -translate-y-1/2
                                                      bg-black text-white text-xs px-2 py-1 rounded
                                                      opacity-0 group-hover:opacity-100 transition whitespace-nowrap z-50"
                                                    >
                                                      Cannot delete, stock has
                                                      been used
                                                    </div>
                                                  )}
                                                </div>
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  );
                                })()}
                              </td>
                            </tr>
                          )}
                        </>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div
                  className="flex items-center justify-end gap-6 flex-wrap
px-4 sm:px-6 py-5 border-t border-gray-200 dark:border-gray-800"
                >
                  {/* Rows Per Page */}
                  <div className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <span className="font-medium">Rows per page</span>

                    <select
                      value={rowsPerPage}
                      onChange={(e) => {
                        setRowsPerPage(Number(e.target.value));
                        setCurrentPage(1);
                      }}
                      className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-700
      bg-white dark:bg-[#020617]
      text-sm outline-none"
                    >
                      <option value={5}>5</option>
                      <option value={10}>10</option>
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                    </select>
                  </div>

                  {/* Pagination */}
                  <div className="flex items-center gap-1 flex-wrap">
                    {/* First Page */}
                    <button
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage(1)}
                      className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
                    >
                      «
                    </button>

                    {/* Previous */}
                    <button
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
                    >
                      <FiChevronLeft />
                    </button>

                    {/* Dynamic Page Numbers */}
                    {(() => {
                      let pages = [];

                      // 1,2,3 → SHOW ALL
                      if (totalPages <= 3) {
                        pages = Array.from(
                          { length: totalPages },
                          (_, i) => i + 1,
                        );
                      }

                      // EXACTLY 4 PAGES
                      else if (totalPages === 4) {
                        pages = [1, 2, 3, 4];
                      }

                      // EXACTLY 5 PAGES
                      else if (totalPages === 5) {
                        if (currentPage <= 2) {
                          pages = [1, 2, 3, "...", 5];
                        } else if (currentPage >= 4) {
                          pages = [1, "...", 3, 4, 5];
                        } else {
                          pages = [1, 2, 3, 4, 5];
                        }
                      }

                      // MORE THAN 5 PAGES
                      else {
                        // START
                        if (currentPage <= 2) {
                          pages = [1, 2, 3, "...", totalPages];
                        }

                        // END
                        else if (currentPage >= totalPages - 1) {
                          pages = [
                            1,
                            "...",
                            totalPages - 2,
                            totalPages - 1,
                            totalPages,
                          ];
                        }

                        // MIDDLE
                        else {
                          pages = [
                            1,
                            "...",
                            currentPage - 1,
                            currentPage,
                            currentPage + 1,
                            "...",
                            totalPages,
                          ];
                        }
                      }

                      return pages.map((page, index) => {
                        // DOTS
                        if (page === "...") {
                          return (
                            <span
                              key={`dots-${index}`}
                              className="w-9 h-9 flex items-center justify-center text-gray-500"
                            >
                              ...
                            </span>
                          );
                        }

                        return (
                          <button
                            key={`page-${page}`}
                            onClick={() => setCurrentPage(page)}
                            className={`w-9 h-9 rounded-md text-sm transition
        ${
          currentPage === page
            ? "font-semibold text-black dark:text-white"
            : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
        }`}
                          >
                            {page}
                          </button>
                        );
                      });
                    })()}
                    {/* Next */}
                    <button
                      disabled={currentPage === totalPages}
                      onClick={() =>
                        setCurrentPage((p) => Math.min(totalPages, p + 1))
                      }
                      className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
                    >
                      <FiChevronRight />
                    </button>

                    {/* Last Page */}
                    <button
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage(totalPages)}
                      className="w-9 h-9 flex items-center justify-center rounded-md
      text-gray-600 dark:text-gray-300
      hover:bg-gray-100 dark:hover:bg-gray-800
      disabled:opacity-40 disabled:cursor-not-allowed transition"
                    >
                      »
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
        {activeTab === "storage" && <StorageTab />}
        {activeTab === "category" && <CategoryTab />}
      </div>

      {/* Modal */}
      <AddItemModal
        isOpen={showAddModal}
        onClose={() => {
          setShowAddModal(false);
          setEditItemData(null);
        }}
        editData={editItemData}
        onSuccess={fetchInventoryItems}
      />

      <AddBatchModal
        isOpen={showBatchModal}
        onClose={() => {
          setShowBatchModal(false);
          setEditBatchData(null);
        }}
        item={selectedItem}
        editData={editBatchData}
        onSuccess={() => {
          fetchInventoryItems();
        }}
      />

      <AddExcelModal
        isOpen={showExcelModal}
        onClose={() => setShowExcelModal(false)}
        onSuccess={fetchInventoryItems}
        uploadUrl="/inventory/add_items_via_excel"
      />

      <AddExcelModal
        isOpen={showBatchExcelModal}
        onClose={() => setShowBatchExcelModal(false)}
        onSuccess={() => {
          fetchInventoryItems();
          setItemBatches({});
        }}
        uploadUrl="/inventory/items/batches/bulk-via-excel"
      />

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>

          <div className="relative w-full max-w-sm bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-xl p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Delete Item
            </h3>

            <p className="text-sm text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to delete this inventory item?
            </p>

            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteItemId(null);
                }}
                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700 
          bg-white dark:bg-[#020617] text-gray-700 dark:text-gray-200 
          hover:bg-gray-100 dark:hover:bg-gray-800 transition text-sm"
              >
                Cancel
              </button>

              <button
                onClick={handleDeleteItem}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm transition"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {showDownloadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          {/* Overlay */}
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>

          {/* Modal */}
          <div
            className="relative w-full max-w-2xl bg-white dark:bg-[#0f172a] 
    border border-gray-200 dark:border-gray-800 rounded-xl shadow-xl p-6"
          >
            {/* Header */}
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                Download Excel Templates
              </h2>

              <button
                onClick={() => setShowDownloadModal(false)}
                className=" text-gray-500 hover:text-gray-800 dark:text-white dark:hover:text-gray-300 transition"
              >
                ✕
              </button>
            </div>

            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
              Download these templates to upload data in correct format
            </p>

            {/* Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Inventory Excel */}
              <div className="border rounded-xl p-4 shadow hover:shadow-md transition">
                <h3 className="font-semibold text-gray-800 dark:text-white mb-1">
                  Add Inventory Excel
                </h3>
                <p className="text-xs dark:text-gray-300 text-gray-500 mb-4">
                  Template for adding new items
                </p>

                <a
                  href="/inventory_upload_sample.xlsx"
                  download
                  className="block text-center px-4 py-2 rounded-md 
            bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium"
                >
                  Download
                </a>
              </div>

              {/* Stock Excel */}
              <div className="border rounded-xl p-4 shadow hover:shadow-md transition">
                <h3 className="font-semibold text-gray-800 dark:text-white mb-1">
                  Add Stock Excel
                </h3>
                <p className="text-xs dark:text-gray-300 text-gray-500 mb-4">
                  Template for adding stock batches
                </p>

                <a
                  href="/final_stock_upload_sample.xlsx"
                  download
                  className="block text-center px-4 py-2 rounded-md 
            bg-orange-500 hover:bg-orange-600 text-white text-sm font-medium"
                >
                  Download
                </a>
              </div>
            </div>

            {/* Footer */}
            <div className="flex justify-end mt-6">
              <button
                onClick={() => setShowDownloadModal(false)}
                className=" dark:text-white px-4 py-2 border rounded-md text-sm"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {showBatchDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm"></div>

          <div className="relative w-full max-w-sm bg-white dark:bg-[#0f172a] border border-gray-200 dark:border-gray-800 rounded-xl shadow-xl p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Delete Stock
            </h3>

            <p className="text-sm text-gray-600 dark:text-gray-300 mb-6">
              Are you sure you want to delete this stock?
            </p>

            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowBatchDeleteModal(false);
                  setDeleteBatchData(null);
                }}
                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-700"
              >
                Cancel
              </button>

              <button
                onClick={handleDeleteBatch}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
