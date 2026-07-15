import { useState, useRef } from "react";
import { FiX } from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";

import * as XLSX from "xlsx";

export default function AddExcelModal({
  isOpen,
  onClose,
  onSuccess,
  uploadUrl,
  downloadReport = false,
}) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);
  const [uploadSummary, setUploadSummary] = useState(null);
  const [errorRows, setErrorRows] = useState([]);

  const resetModal = () => {
    setFile(null);
    setLoading(false);
    setUploadSummary(null);
    setErrorRows([]);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const droppedFile = e.dataTransfer.files[0];

    if (!droppedFile) return;

    const allowedTypes = [
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-excel",
      "text/csv",
    ];

    if (!allowedTypes.includes(droppedFile.type)) {
      toast.warning("Only .xlsx, .xls and .csv files are allowed");
      return;
    }

    setFile(droppedFile);
  };
  const handleClose = () => {
    resetModal();
    onClose();
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
    }
  };

  const handleRemoveFile = () => {
    setFile(null);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const downloadUploadReport = (responseData) => {
    const workbook = XLSX.utils.book_new();

    // =========================
    // SUMMARY SHEET
    // =========================
    const summaryData = [
      ["Metric", "Value"],
      ["Status", responseData.success ? "SUCCESS" : "FAILED"],
      ["File Format", responseData.file_format_detected || "-"],
      ["Total Rows", responseData.total_rows_in_excel || 0],
      ["Unique Dishes", responseData.total_unique_dishes || 0],
      ["Unique Combos", responseData.total_unique_combos || 0],
      ["Dishes Sold", responseData.total_dishes_sold || 0],
      ["Combos Sold", responseData.total_combos_sold || 0],
      ["Inventory Deductions", responseData.total_inventory_deductions || 0],
    ];

    const summarySheet = XLSX.utils.aoa_to_sheet(summaryData);

    XLSX.utils.book_append_sheet(workbook, summarySheet, "Summary");

    // =========================
    // WARNINGS SHEET
    // =========================
    const warnings =
      responseData.warnings?.length > 0
        ? responseData.warnings.map((warning, index) => ({
            Sr_No: index + 1,
            Warning: warning,
          }))
        : [{ Sr_No: "-", Warning: "No warnings found" }];

    const warningSheet = XLSX.utils.json_to_sheet(warnings);

    XLSX.utils.book_append_sheet(workbook, warningSheet, "Warnings");

    // =========================
    // SALES SHEET
    // =========================
    const sales =
      responseData.sales?.length > 0
        ? responseData.sales.map((sale) => ({
            Type: sale.type || "-",
            Dish_Name: sale.dish_name || "-",
            Combo_Name: sale.combo_name || "-",
            Qty_Sold: sale.qty_sold || 0,
            Sale_Date: sale.sale_date || "-",
            Sale_Recorded: sale.sale_recorded ? "Yes" : "No",
            Inventory_Deducted: sale.inventory_deducted ? "Yes" : "No",
          }))
        : [];

    const salesSheet = XLSX.utils.json_to_sheet(sales);

    XLSX.utils.book_append_sheet(workbook, salesSheet, "Sales");

    // =========================
    // DOWNLOAD FILE
    // =========================
    const timestamp = new Date().toISOString().slice(0, 19).replace(/:/g, "-");

    XLSX.writeFile(workbook, `upload_status_report_${timestamp}.xlsx`);
  };

  const handleUpload = async (e) => {
    e.preventDefault();

    if (!file) {
      toast.warning("Please select an Excel file");
      return;
    }

    const allowedTypes = [
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-excel",
    ];

    if (!allowedTypes.includes(file.type)) {
      toast.warning("Only .xlsx, .xls and .csv files are allowed");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);
      const res = await api.post(uploadUrl, formData);

      if (downloadReport) {
        downloadUploadReport(res.data);
      }
      console.log("FULL RESPONSE:", res.data);

      setUploadSummary({
        succeeded:
          (res.data.total_dishes_sold ?? 0) +
            (res.data.total_combos_sold ?? 0) >
          0
            ? (res.data.total_dishes_sold ?? 0) +
              (res.data.total_combos_sold ?? 0)
            : (res.data.summary?.saved_count ??
              res.data.total_products ??
              res.data.total_dishes_created ??
              res.data.succeeded ??
              res.data.success_count ??
              res.data.inserted ??
              0),

        failed:
          res.data.summary?.skipped_count ??
          res.data.total_products_skipped ??
          res.data.failed ??
          res.data.failed_count ??
          0,

        total:
          res.data.total_rows_in_excel ??
          res.data.summary?.total_rows ??
          res.data.total_rows ??
          res.data.total ??
          res.data.results?.length ??
          res.data.total_products ??
          0,
      });

      setErrorRows(
        res?.data?.warnings && Array.isArray(res.data.warnings)
          ? res.data.warnings
          : [],
      );
      const successCount =
        (res.data.total_dishes_sold ?? 0) + (res.data.total_combos_sold ?? 0) >
        0
          ? (res.data.total_dishes_sold ?? 0) +
            (res.data.total_combos_sold ?? 0)
          : (res.data.summary?.saved_count ??
            res.data.total_products ??
            res.data.total_dishes_created ??
            res.data.succeeded ??
            res.data.success_count ??
            res.data.inserted ??
            0);
      toast.success(`${successCount} items uploaded`);
      onSuccess?.();
    } catch (err) {
      console.error("Excel upload failed", err);
      console.log("Backend response:", err?.response?.data);

      //  Extract meaningful error message from backend
      let errorMessage = "Failed to upload Excel file";

      if (err?.response?.data) {
        const data = err.response.data;

        // Case 1: FastAPI / validation errors
        if (Array.isArray(data.detail)) {
          errorMessage = data.detail.map((e) => e.msg).join(", ");
        }

        // Case 2: Simple string error
        else if (typeof data.detail === "string") {
          errorMessage = data.detail;
        }

        // Case 3: message field
        else if (data.message) {
          errorMessage = data.message;
        }

        // Case 4: fallback full JSON
        else {
          errorMessage = JSON.stringify(data);
        }
      }
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />

      {/* Modal */}
      <div
        className="relative w-full max-w-md bg-white dark:bg-[#0f172a] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 className="text-2xl font-semibold text-gray-900 dark:text-white">
            Upload Excel
          </h2>

          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition"
          >
            <FiX className="text-2xl text-gray-700 dark:text-gray-200" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleUpload} className="px-6 py-6">
          {!uploadSummary && (
            <>
              <p className="text-sm font-medium text-gray-800 dark:text-gray-200 mb-3">
                Select Excel file
              </p>

              {/* Upload Box */}
              <label
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`flex flex-col items-center justify-center gap-3 border-2 border-dashed rounded-xl p-8 transition
      ${
        dragActive
          ? "border-blue-500 bg-blue-50 dark:bg-blue-900/10"
          : file
            ? "border-green-400 bg-green-50 dark:bg-green-900/10"
            : "border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-[#020617] hover:bg-gray-100 dark:hover:bg-gray-800"
      }`}
              >
                <img
                  src="https://cdn-icons-png.flaticon.com/512/732/732220.png"
                  alt="excel"
                  className="w-12 h-12"
                />

                <p className="text-gray-700 dark:text-gray-200 font-medium">
                  Drag & Drop Excel File Here
                </p>

                <div className="flex items-center gap-3 text-gray-400 text-sm">
                  <span className="w-16 h-px bg-gray-300 dark:bg-gray-700"></span>
                  OR
                  <span className="w-16 h-px bg-gray-300 dark:bg-gray-700"></span>
                </div>

                {/* Choose file button */}
                <span
                  className={`px-6 py-2 rounded-lg text-white font-medium transition
                  ${
                    file
                      ? "bg-gray-400 cursor-not-allowed"
                      : "bg-orange-500 hover:bg-orange-600 cursor-pointer"
                  }
                `}
                >
                  Choose file
                </span>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  onChange={handleFileChange}
                  disabled={file !== null}
                  className="hidden"
                />

                <p className="text-xs text-gray-500">
                  Accepted formats: .xlsx, .xls, .csv
                </p>

                {!file && (
                  <p className="text-sm text-gray-400">No Chosen File</p>
                )}

                {file && (
                  <div className="flex items-center gap-2 text-sm text-green-600 font-medium">
                    <span className="truncate max-w-[200px]">{file.name}</span>

                    <button
                      type="button"
                      onClick={handleRemoveFile}
                      className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition"
                    >
                      <FiX className="text-red-500 text-sm" />
                    </button>
                  </div>
                )}
              </label>
            </>
          )}

          {uploadSummary && (
            <div className="mt-6 p-4 rounded-xl bg-gray-50 dark:bg-gray-800 border">
              <p className="text-green-600 font-semibold">
                ✅ {uploadSummary.succeeded} items added successfully
              </p>

              <p className="text-red-500 font-semibold">
                ❌ {uploadSummary.failed} failed
              </p>

              <p className="text-blue-500 font-semibold">
                📊 Total Rows: {uploadSummary.total}
              </p>
            </div>
          )}

          {errorRows.length > 0 && (
            <div className="mt-6 max-h-60 overflow-auto border rounded-xl">
              <table className="w-full text-sm">
                <thead className="bg-gray-100 dark:bg-gray-700">
                  <tr>
                    <th className="p-2 text-left">Row</th>
                    <th className="p-2 text-left">Item</th>
                    <th className="p-2 text-left">Issue</th>
                  </tr>
                </thead>

                <tbody>
                  {errorRows.map((err, index) => (
                    <tr key={index} className="border-t">
                      <td className="p-2">{err.row}</td>
                      <td className="p-2">{err.item_name}</td>
                      <td className="p-2 text-red-500">{err.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Buttons */}
          <div className="flex items-center justify-center gap-28 mt-8">
            {!uploadSummary ? (
              <button
                type="submit"
                disabled={loading}
                className="px-8 py-2 rounded-xl border border-gray-300 dark:border-gray-700
      text-black dark:text-white font-semibold hover:bg-green-50 dark:hover:bg-green-900/20 transition"
              >
                {loading ? "Uploading..." : "Upload"}
              </button>
            ) : (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  resetModal();
                }}
                className="px-8 py-2 rounded-xl border border-gray-300 dark:border-gray-700
    text-black dark:text-white font-semibold hover:bg-blue-50 dark:hover:bg-blue-900/20 transition"
              >
                Upload Another File
              </button>
            )}

            <button
              type="button"
              onClick={handleClose}
              className="px-8 py-2 rounded-xl border border-gray-300 dark:border-gray-700
                text-black dark:text-white font-semibold hover:bg-red-50 dark:hover:bg-red-900/20 transition"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
