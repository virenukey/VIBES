export const downloadWastageCSV = (data, wastageType) => {
    const itemName =
        data.combo_name ||
        data.dish_name ||
        data.sfp_name ||
        "";

    const csvLines = [
        ["Wastage ID", data.wastage_id],
        ["Type", wastageType],
        ["Name", itemName],
        ["Quantity Wasted", data.quantity_wasted],
        ["Total Cost", data.total_cost ?? data.cost_value ?? ""],
        ["Reason", data.wastage_reason],
        ["Date", data.wastage_date],
        [],
    ];

    // Overall warnings
    if (data.warnings?.length) {
        csvLines.push(["Overall Warnings"]);
        data.warnings.forEach((w) => csvLines.push([w]));
        csvLines.push([]);
    }

    // Combo breakdown
    if (
        data.breakdown?.length &&
        Object.prototype.hasOwnProperty.call(data.breakdown[0], "type")
    ) {
        csvLines.push([
            "Type",
            "ID",
            "Name",
            "Quantity",
            "Cost",
            "Warnings",
        ]);

        data.breakdown.forEach((item) => {
            csvLines.push([
                item.type,
                item.id,
                item.name,
                item.qty,
                item.cost,
                Array.isArray(item.warnings)
                    ? item.warnings.join(" | ")
                    : item.warning || "",
            ]);
        });
    }

    // Dish / Semi-finished breakdown
    else if (data.breakdown?.length) {
        csvLines.push([
            "Ingredient ID",
            "Ingredient Name",
            "Qty Deducted",
            "Unit",
            "Cost",
            "Source",
        ]);

        data.breakdown.forEach((item) => {
            csvLines.push([
                item.ingredient_id,
                item.ingredient_name,
                item.qty_deducted,
                item.unit,
                item.ingredient_cost,
                item.source,
            ]);
        });
    }

    const csvContent = csvLines
        .map((row) =>
            row
                .map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`)
                .join(",")
        )
        .join("\n");

    const blob = new Blob([csvContent], {
        type: "text/csv;charset=utf-8;",
    });

    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = `${wastageType}_wastage_${data.wastage_id}.csv`;

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
};