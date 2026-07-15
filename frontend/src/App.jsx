import { Routes, Route, Navigate } from "react-router-dom";
import DashboardLayout from "./layouts/DashboardLayout";

import Login from "./pages/Login";
import ProtectedRoute from "./pages/ProtectedRoute";
import ItemDetails from "./pages/ItemDetails";
import UnderDevelopment from "./pages/UnderDevelopment";

import InventoryTab from "./components/Inventory Management/InventoryTab";
import DishTab from "./components/Dish Management/DishTab";
import OrderTab from "./components/NewOrderManagement/OrderTab";
import RemainingInventoryTab from "./components/RemainingInventory/RemainingInventoryTab";

import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";

import WastageTab from "./components/WastageManagement/WastageTab";
import AlertNotifications from "./pages/AlertNotifications";

import ReportAndAnalysisTab from "./components/ReportAndAnalysis/ReportAndAnalysisTab";

export default function App() {
  return (
    <>
      <Routes>
        {/* Login Page */}
        <Route path="/login" element={<Login />} />

        {/* Dashboard Layout */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DashboardLayout />
            </ProtectedRoute>
          }
        >
          {/* Default Page */}
          <Route index element={<Navigate to="inventory" />} />

          {/* Sidebar Pages */}
          <Route
            path="quick-dish"
            element={<UnderDevelopment title="Quick Dish" />}
          />
          <Route path="inventory" element={<InventoryTab />} />
          <Route path="dish-preparation" element={<DishTab />} />
          <Route path="orders" element={<OrderTab />} />
          <Route path="wastage" element={<WastageTab />} />
          <Route path="remaining-inventory" element={<RemainingInventoryTab />} />
          <Route path="reports-analysis" element={<ReportAndAnalysisTab/>} />
        
          <Route path="alerts" element={<AlertNotifications />} />

          {/* Item Details Page */}
          <Route path="item-details" element={<ItemDetails />} />
        </Route>
      </Routes>

      {/* Toast Container */}
      <ToastContainer
        position="top-center"
        autoClose={5000}
        hideProgressBar={false}
        newestOnTop
        closeOnClick
        pauseOnHover
        theme="colored"
      />
    </>
  );
}