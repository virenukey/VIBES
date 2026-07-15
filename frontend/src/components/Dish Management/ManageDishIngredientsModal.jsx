import { useEffect, useState } from "react";
import {
  FiX,
  FiPlus,
  FiCheck,
  FiTrash2,
} from "react-icons/fi";
import api from "../../api/axios";
import { toast } from "react-toastify";

export default function ManageDishIngredientModal({
  isOpen,
  onClose,
  dish,
  onSuccess,
  mode,
}) {
  /* ================= COMMON ================= */
  const [items, setItems] = useState([]);
  const [preparedList, setPreparedList] = useState([]);

  const [rawIngredients, setRawIngredients] = useState([]);

  const [preparedIngredients, setPreparedIngredients] = useState([]);
  const [originalIds, setOriginalIds] = useState([]);

  const [activeForm, setActiveForm] = useState(null); 
  const [error, setError] = useState("");

  /* ================= TEMP STATES ================= */
  const [rawTemp, setRawTemp] = useState({});
  const [prepTemp, setPrepTemp] = useState({});

  /* ================= FETCH ================= */
  useEffect(() => {
    if (!isOpen || !dish) return;

    // fetch inventory
    api.get("/inventory/")
      .then(res => setItems(res.data.data || []));

    api.get("/dish/get-all-semi-finished")
      .then(res => {
        // console.log("PREPARED RESPONSE:", res.data);
        setPreparedList(res.data.data || res.data || []);
      });


    api.get(`/dish/dishes/${dish.id}/ingredients`)
      .then(res => {
        console.log("DISH INGREDIENT RESPONSE:", res.data);

        const data = res.data;


        //  Map RAW ingredients 
        const mappedRaw = data.raw_ingredients.map(item => ({
          dish_ingredient_id: item.id,          
          ingredient_id: item.ingredient_id,
          name: item.ingredient_name,
          quantity_required: item.quantity_required,
          unit: item.unit,
        }));
        //  Map SEMI_FINISHED ingredients 
        const mappedPrepared = data.semi_finished_ingredients.map(item => ({
          dish_ingredient_id: item.id,
          preprepred_material_id: item.preprepred_material_id,
          semi_finished_id: item.preprepred_material_id,
          name: item.ingredient_name,
          quantity_required: item.quantity_required,
          unit: item.unit,
        }));

        const allIds = [
          ...data.raw_ingredients.map(item => item.id),
          ...data.semi_finished_ingredients.map(item => item.id),
        ];

        setOriginalIds(allIds);

        setRawIngredients(mappedRaw);
        setPreparedIngredients(mappedPrepared);
      })
      .catch(err => {
        console.error("Failed to fetch dish ingredients", err);
      });

  }, [isOpen, dish]);

  useEffect(() => {
    if (!isOpen) {
      setRawIngredients([]);
      setPreparedIngredients([]);
      setRawTemp({});
      setPrepTemp({});
      setActiveForm(null);
      setError("");
    }
  }, [isOpen]);

  if (!isOpen || !dish) return null;

  /* ================= SAVE HANDLERS ================= */
  const saveRaw = () => {
    if (!rawTemp.ingredient_id || !rawTemp.quantity_required || error) return;

    setRawIngredients(prev => [...prev, rawTemp]);
    setRawTemp({});
    setError("");


  };
  const savePrepared = () => {
    if (!prepTemp.semi_finished_id || error) return;

    setPreparedIngredients(prev => [
      ...prev,
      {
        ...prepTemp,
        dish_ingredient_id: null,  
        preprepred_material_id: null 
      }
    ]);

    resetForms();
  };

  const resetForms = () => {
    setRawTemp({});
    setPrepTemp({});
    setError("");
  };

  /* ================= FINAL SAVE ================= */
  const handleSave = async () => {
    try {
      if (rawIngredients.length === 0 && preparedIngredients.length === 0) {
        toast.error("Please add at least one ingredient");
        return;
      }

      /* ================= CREATE MODE ================= */
      if (mode === "create") {
        const payload = {
          ingredients: [
            ...rawIngredients.map((r) => ({
              ingredient_type: "RAW",
              ingredient_id: Number(r.ingredient_id),
              ingredient_data: null,
              preprepred_material_id: null,
              quantity_required: Number(r.quantity_required),
              unit: r.unit,
              preferred_batch_id: 0,
            })),
            ...preparedIngredients.map((p) => ({
              ingredient_type: "SEMI_FINISHED",
              ingredient_id: null,
              ingredient_data: null,
              preprepred_material_id: p.semi_finished_id,
              quantity_required: Number(p.quantity_required),
              unit: p.unit || "gm",
              preferred_batch_id: 0,
            })),
          ],
        };

        await api.post(
          `/dish/dishes/${dish.id}/ingredients/bulk`,
          payload
        );

        toast.success("Ingredients created successfully!");
      }

      /* ================= EDIT MODE ================= */
      if (mode === "edit") {

        const currentIds = [
          ...rawIngredients
            .filter(r => r.dish_ingredient_id)
            .map(r => r.dish_ingredient_id),

          ...preparedIngredients
            .filter(p => p.dish_ingredient_id)
            .map(p => p.dish_ingredient_id),
        ];

        const deletedIds = originalIds.filter(
          id => !currentIds.includes(id)
        );

        if (deletedIds.length > 0) {
          console.log("DELETING IDS:", deletedIds);

          await api.delete(
            `/dish/dishes/${dish.id}/ingredients/bulk`,
            {
              data: {
                dish_ingredient_ids: deletedIds
              }
            }
          );
        }


        const existingRaw = rawIngredients.filter(r => r.dish_ingredient_id);
        const existingPrep = preparedIngredients.filter(p => p.dish_ingredient_id);

        if (existingRaw.length > 0 || existingPrep.length > 0) {

          const patchPayload = {
            ingredients: [
              ...existingRaw.map((r) => ({
                dish_ingredient_id: r.dish_ingredient_id,
                quantity_required: Number(r.quantity_required),
                unit: r.unit,
                ingredient_id: r.ingredient_id,
                preprepred_material_id: null,
              })),

              ...existingPrep.map((p) => ({
                dish_ingredient_id: p.dish_ingredient_id,
                quantity_required: Number(p.quantity_required),
                unit: p.unit,
                ingredient_id: null,
                preprepred_material_id:
                  typeof p.preprepred_material_id === "number"
                    ? p.preprepred_material_id
                    : null
              })),
            ],
          };

          await api.patch(
            `/dish/dishes/${dish.id}/ingredients/bulk`,
            patchPayload
          );
        }

        const newRaw = rawIngredients.filter(r => !r.dish_ingredient_id);
        const newPrep = preparedIngredients.filter(p => !p.dish_ingredient_id);

        if (newRaw.length > 0 || newPrep.length > 0) {

          const postPayload = {
            ingredients: [
              ...newRaw.map((r) => ({
                ingredient_type: "RAW",
                ingredient_id: Number(r.ingredient_id),
                ingredient_data: null,
                preprepred_material_id: null,
                quantity_required: Number(r.quantity_required),
                unit: r.unit,
                preferred_batch_id: 0,
              })),

              ...newPrep.map((p) => ({
                ingredient_type: "SEMI_FINISHED",
                ingredient_id: null,
                ingredient_data: null,
                preprepred_material_id: p.semi_finished_id,
                quantity_required: Number(p.quantity_required),
                unit: p.unit || "gm",
                preferred_batch_id: 0,
              })),
            ],
          };

          await api.post(
            `/dish/dishes/${dish.id}/ingredients/bulk`,
            postPayload
          );
        }

        toast.success("Ingredients updated successfully!");
      }
      if (onSuccess) {
        await onSuccess();
      }

      onClose();

    } catch (err) {
      console.error("Bulk save failed", err.response?.data);
      toast.error(
        err.response?.data?.detail ||
        "Failed to save ingredients"
      );
    }
  };

  /* ================= UI ================= */
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative w-full max-w-2xl bg-white dark:bg-[#0f172a] rounded-xl border border-gray-200 dark:border-gray-800">

        {/* HEADER */}
        <div className="flex justify-between px-6 py-4 border-b">
          <div>
            <h2 className="text-lg font-semibold">{dish.name}</h2>
            <p className="text-sm text-gray-500">{dish.type?.name}</p>
          </div>
          <button onClick={onClose}><FiX /></button>
        </div>

        {/* BODY */}
        <div className="px-6 py-6 space-y-6">


          <div className="flex items-center gap-3 mb-4">
            <button
              onClick={() => {
                setActiveForm("RAW");
                setPrepTemp({});
              }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md
                        bg-yellow-400 hover:bg-yellow-500 text-sm font-medium"
            >
              <FiPlus />
              Add Ingredient
            </button>

            <button
              onClick={() => {
                setActiveForm("PREP");
                setRawTemp({});
              }}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md
                        bg-yellow-400 hover:bg-yellow-500 text-sm font-medium"
            >
              <FiPlus />
              Add Prepared Stuff
            </button>
          </div>

          {/* ================= RAW INGREDIENT FORM ================= */}
          {activeForm === "RAW" && (
            <div className="mb-3 flex items-center gap-3">
              <select
                value={rawTemp.ingredient_id || ""}
                onChange={(e) => {
                  const selected = items.find(
                    (it) => it.id === Number(e.target.value)
                  );

                  setRawTemp({
                    ingredient_id: selected.id,
                    name: selected.name,
                    unit: selected.unit,
                    available_quantity: selected.quantity,
                  });

                  setError("");
                }}
                className="mt-2 w-full border border-gray-300 dark:border-gray-700
                            rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
                            text-gray-800 dark:text-gray-200 outline-none"
              >
                <option value="">Select Item</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>

              <div className="flex flex-col">
                <input
                  type="number"
                  placeholder="Quantity"
                  value={rawTemp.quantity_required || ""}
                  onChange={(e) => {
                    const value = Number(e.target.value);

                    if (value > rawTemp.available_quantity) {
                      setError(
                        `Available: ${rawTemp.available_quantity} ${rawTemp.unit}`
                      );
                    } else {
                      setError("");
                      setRawTemp((p) => ({
                        ...p,
                        quantity_required: value,
                      }));
                    }
                  }}
                  className="mt-2 w-40 border border-gray-300 dark:border-gray-700
                            rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
                            text-gray-800 dark:text-gray-200 outline-none"
                />

                {error && (
                  <span className="text-xs text-red-500 mt-1">
                    {error}
                  </span>
                )}
              </div>

              <button
                onClick={saveRaw}
                className="p-2 rounded bg-green-500 hover:bg-green-600 text-white"
              >
                <FiCheck />
              </button>

              <button
                onClick={resetForms}
                className="p-2 rounded bg-red-400 hover:bg-red-500 text-white"
              >
                <FiX />
              </button>
            </div>
          )}


          {/* ================= PREPARED STUFF FORM ================= */}
          {activeForm === "PREP" && (
            <div className="mb-3 flex items-center gap-3">
              <select
                value={prepTemp.semi_finished_id || ""}
                onChange={(e) => {
                  const value = e.target.value;

                  if (!value) return;

                  const selected = preparedList.find(
                    (p) => p.product_id === value
                  );

                  if (!selected) return;

                  setPrepTemp({
                    semi_finished_id: selected.product_id,
                    name: selected.name,
                    available_quantity: selected.yield_quantity,
                    unit: selected.unit,
                  });

                  setError("");
                }}
                className="mt-2 w-full border border-gray-300 dark:border-gray-700
                            rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
                            text-gray-800 dark:text-gray-200 outline-none"
              >
                <option value="">Select Prepared Stuff</option>
                {preparedList.map((p) => (
                  <option
                    key={p.product_id}
                    value={p.product_id}
                  >
                    {p.name}
                  </option>
                ))}
              </select>

              <div className="flex flex-col">
                <input
                  type="number"
                  placeholder="Quantity"
                  value={prepTemp.quantity_required || ""}
                  onChange={(e) => {
                    const value = Number(e.target.value);

                    if (value > prepTemp.available_quantity) {
                      setError(
                        `Available: ${prepTemp.available_quantity}`
                      );
                    } else {
                      setError("");
                      setPrepTemp((p) => ({
                        ...p,
                        quantity_required: value,
                      }));
                    }
                  }}
                  className="mt-2 w-40 border border-gray-300 dark:border-gray-700
                            rounded-md px-3 py-2 bg-white dark:bg-[#0b1220]
                            text-gray-800 dark:text-gray-200 outline-none"
                />

                {error && (
                  <span className="text-xs text-red-500 mt-1">
                    {error}
                  </span>
                )}
              </div>

              <button
                onClick={savePrepared}
                className="p-2 rounded bg-green-500 hover:bg-green-600 text-white"
              >
                <FiCheck />
              </button>

              <button
                onClick={resetForms}
                className="p-2 rounded bg-red-400 hover:bg-red-500 text-white"
              >
                <FiX />
              </button>
            </div>
          )}


          {error && <p className="text-xs text-red-500">{error}</p>}

          {/* ================= ADDED RAW INGREDIENTS LIST ================= */}
          {activeForm === "RAW" && rawIngredients.length > 0 && (
            <div className="mt-4 space-y-2">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Added Ingredients
              </h4>

              {rawIngredients.map((item, index) => (
                <div
                  key={index}
                  className="flex justify-between items-center
                   bg-gray-100 dark:bg-gray-800
                   px-3 py-2 rounded-md"
                >
                  <div className="text-sm">
                    {item.name} — {item.quantity_required} {item.unit}
                  </div>

                  <button
                    onClick={() =>
                      setRawIngredients(prev =>
                        prev.filter((_, i) => i !== index)
                      )
                    }
                    className="text-red-500 hover:text-red-700"
                  >
                    <FiTrash2 />
                  </button>
                </div>
              ))}
            </div>
          )}
          {/* ================= EXISTING INGREDIENTS ================= */}
          {/* {existingIngredients.length > 0 && (
            <div className="mt-4 space-y-2">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Existing Ingredients
              </h4>

              {existingIngredients.map((item, index) => (
                <div
                  key={index}
                  className="flex justify-between items-center
                   bg-blue-50 dark:bg-blue-900/30
                   px-3 py-2 rounded-md"
                >
                  <div className="text-sm">
                    {item.name} — {item.quantity_required} {item.unit}
                  </div>
                </div>
              ))}
            </div>
          )} */}

          {/* ================= ADDED PREPARED STUFF LIST ================= */}
          {activeForm === "PREP" && preparedIngredients.length > 0 && (
            <div className="mt-4 space-y-2">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Added Prepared Stuff
              </h4>

              {preparedIngredients.map((item, index) => (
                <div
                  key={index}
                  className="flex justify-between items-center
                   bg-gray-100 dark:bg-gray-800
                   px-3 py-2 rounded-md"
                >
                  <div className="text-sm">
                    {item.name} — {item.quantity_required}
                  </div>

                  <button
                    onClick={() =>
                      setPreparedIngredients(prev =>
                        prev.filter((_, i) => i !== index)
                      )
                    }
                    className="text-red-500 hover:text-red-700"
                  >
                    <FiTrash2 />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* FOOTER */}
        <div className="flex justify-end gap-4 px-6 py-4 border-t">
          <button onClick={handleSave} className="px-6 py-2 bg-green-400 rounded-md text-white">
            Save
          </button>
          <button onClick={onClose} className="px-6 py-2 bg-yellow-400 rounded-md">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
