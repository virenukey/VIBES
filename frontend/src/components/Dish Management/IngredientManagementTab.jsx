import { useState, useEffect } from "react";
import {
  FiSearch,
  FiEye,
  FiEdit,
  FiPlus,
  FiChevronLeft,
  FiChevronRight,
} from "react-icons/fi";
import api from "../../api/axios";
import ViewDishModal from "./ViewDishModal";
import ManageDishIngredientsModal from "./ManageDishIngredientsModal";

export default function IngredientManagementTab() {
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);

  const [dishes, setDishes] = useState([]);
  const [searchText, setSearchText] = useState("");

  const [viewDish, setViewDish] = useState(null);
  const [editDish, setEditDish] = useState(null);
  const [createDish, setCreateDish] = useState(null);

  const [dishIngredientStatus, setDishIngredientStatus] = useState({});

  useEffect(() => {
    fetchDishes();
  }, []);

  const fetchDishes = async () => {
    try {
      const res = await api.get("/dish/dishes");
      const dishList = res.data.data || [];
      setDishes(dishList);

     
      const statusMap = {};

      await Promise.all(
        dishList.map(async (dish) => {
          try {
            const ingRes = await api.get(
              `/dish/dishes/${dish.id}/ingredients`
            );

            const data = ingRes.data;

            const hasIngredients =
              (data.raw_ingredients?.length || 0) > 0 ||
              (data.semi_finished_ingredients?.length || 0) > 0;

            statusMap[dish.id] = hasIngredients;
          } catch {
            statusMap[dish.id] = false;
          }
        })
      );

      setDishIngredientStatus(statusMap);

    } catch (err) {
      console.error("Failed to fetch dishes", err);
      toast.error("Failed to fetch dishes");
    }
  };

  /* ================= FILTER + PAGINATION ================= */
  const filteredData = dishes.filter(
    (d) =>
      d.name.toLowerCase().includes(searchText.toLowerCase()) ||
      d.type?.name?.toLowerCase().includes(searchText.toLowerCase())
  );

  const totalPages = Math.ceil(filteredData.length / rowsPerPage) || 1;
  const startIndex = (currentPage - 1) * rowsPerPage;

  const paginatedData = filteredData.slice(
    startIndex,
    startIndex + rowsPerPage
  );

  return (
    <div className="w-full">
      
      <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-3 px-4 sm:px-6 py-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-200">
         Dish Ingredient Management
        </h2>

        <div className="relative">
          <FiSearch className="absolute left-3 top-3 text-gray-400 dark:text-gray-500" />
          <input
            type="text"
            placeholder="Search dish..."
            value={searchText}
            onChange={(e) => {
              setSearchText(e.target.value);
              setCurrentPage(1);
            }}
            className="w-64 pl-10 pr-4 py-2 rounded-lg
                       border border-gray-200 dark:border-gray-700
                       bg-white dark:bg-[#0f172a]
                       text-sm text-gray-800 dark:text-gray-200
                       placeholder-gray-400 dark:placeholder-gray-500
                       outline-none focus:ring-2 focus:ring-orange-400"
          />
        </div>
      </div>

      {/* 🔹 Table */}
      <div className="w-full overflow-x-auto">
        <table className="w-full border-t border-gray-200 dark:border-gray-800">
          <thead className="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                Dish Name
              </th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-gray-800 dark:text-gray-200">
                Category
              </th>
              
              <th className="px-4 py-3 text-center w-20 text-sm font-semibold text-gray-800 dark:text-gray-200">
                Create
              </th>
              <th className="px-4 py-3 text-center w-20 text-sm font-semibold text-gray-800 dark:text-gray-200">
                View
              </th>
              <th className="px-4 py-3 text-center w-20 text-sm font-semibold text-gray-800 dark:text-gray-200">
                Edit
              </th>
            </tr>
          </thead>

          <tbody>
            {paginatedData.length === 0 ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-4 py-6 text-center text-sm text-gray-500 dark:text-gray-400"
                >
                  No dishes found
                </td>
              </tr>
            ) : (
              paginatedData.map((dish) => (
                <tr
                  key={dish.id}
                  className="border-t border-gray-200 dark:border-gray-800"
                >
                  <td className="px-4 py-2 text-sm text-gray-800 dark:text-gray-200">
                    {dish.name}
                  </td>

                  <td className="px-4 py-2 text-sm text-gray-800 dark:text-gray-200">
                    {dish.type?.name}
                  </td>

                  <td className="px-4 py-2 text-center">
                    <button
                      disabled={dishIngredientStatus[dish.id]}
                      onClick={() => setCreateDish(dish)}
                      className={`p-2 rounded 
      ${dishIngredientStatus[dish.id]
                          ? "opacity-40 cursor-not-allowed"
                          : "hover:bg-green-100 dark:hover:bg-green-800"}`}
                    >
                      <FiPlus className="text-green-600 dark:text-green-400" />
                    </button>
                  </td>
                  {/* View */}
                  <td className="px-4 py-2 text-center">
                    <button
                      onClick={() => setViewDish(dish)}
                      className="p-2 rounded hover:bg-gray-100 dark:hover:bg-gray-800"
                    >
                      <FiEye className="text-gray-700 dark:text-gray-200" />
                    </button>
                  </td>

               

                  {/* Edit (Ingredient Management Modal) */}
                  <td className="px-4 py-2 text-center">
                    <button
                      disabled={!dishIngredientStatus[dish.id]}
                      onClick={() => setEditDish(dish)}
                      className={`p-2 rounded 
      ${!dishIngredientStatus[dish.id]
                          ? "opacity-40 cursor-not-allowed"
                          : "hover:bg-gray-100 dark:hover:bg-gray-800"}`}
                    >
                      <FiEdit className="text-gray-700 dark:text-gray-200" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 🔹 Pagination (MATCHES PreparedStuffTab) */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end gap-3 px-4 sm:px-6 py-4">
        <div className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200">
          <span className="font-medium">Rows per page</span>

          <select
            value={rowsPerPage}
            onChange={(e) => {
              setRowsPerPage(Number(e.target.value));
              setCurrentPage(1);
            }}
            className="px-3 py-1 rounded-md border border-gray-200 dark:border-gray-700
                       bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-200"
          >
            <option value={10}>10</option>
            <option value={25}>25</option>
            <option value={50}>50</option>
          </select>
        </div>

        <div className="text-sm font-medium text-gray-800 dark:text-gray-200">
          Page {currentPage} of {totalPages}
        </div>

        <div className="flex items-center gap-2">
          <button
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
            className="p-2 rounded-md 
                 border border-gray-200 dark:border-gray-700 
                 text-gray-700 dark:text-gray-200
                 hover:bg-gray-100 dark:hover:bg-gray-800
                 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FiChevronLeft />
          </button>

          <button
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
            className="p-2 rounded-md 
                 border border-gray-200 dark:border-gray-700 
                 text-gray-700 dark:text-gray-200
                 hover:bg-gray-100 dark:hover:bg-gray-800
                 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <FiChevronRight />
          </button>
        </div>
      </div>

      {/* 🔹 Modals */}
      {viewDish && (
        <ViewDishModal
          isOpen={!!viewDish}
          data={viewDish}
          onClose={() => setViewDish(null)}
        />
      )}

    
      {createDish && (
        <ManageDishIngredientsModal
          mode="create"
          isOpen={!!createDish}
          dish={createDish}
          onClose={() => setCreateDish(null)}
          onSuccess={fetchDishes}
        />
      )}

      
      {editDish && (
        <ManageDishIngredientsModal
          mode="edit"
          isOpen={!!editDish}
          dish={editDish}
          onClose={() => setEditDish(null)}
          onSuccess={fetchDishes}
        />
      )}
    </div>
  );
}
