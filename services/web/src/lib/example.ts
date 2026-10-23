import type { LabelCheckRequest } from "../api/types";

/** The spec §4.1 case: a "source of protein" claim, protein declared on the panel. While the API runs on
 * the contracts' fakes the condition is a PLACEHOLDER (10 g per 100 g), so 8 g routes to revise-and-recheck. */
export const SECTION_41_EXAMPLE: LabelCheckRequest = {
  schema_version: "1.0",
  declared_category: "demo-category",
  package: { net_quantity: 200, net_quantity_unit: "g", principal_display_panel_cm2: 120 },
  label: {
    product_name: "Roasted chana",
    brand_name: "Kheti Foods",
    front_of_pack_text: "Source of protein. Roasted, not fried.",
    claims: ["Source of protein"],
    ingredients: "Bengal gram (98%), iodised salt",
    allergen_statement: "Contains: chickpea",
    veg_status: "veg",
  },
  nutrition: {
    basis: "per_100g",
    energy_kcal: 380,
    protein_g: 8,
    carbohydrate_g: 55,
    total_sugars_g: 3,
    total_fat_g: 6,
  },
};

export const EMPTY_REQUEST: LabelCheckRequest = {
  schema_version: "1.0",
  declared_category: "",
  package: { net_quantity: 0, net_quantity_unit: "g", principal_display_panel_cm2: 0 },
  label: { product_name: "", claims: [], veg_status: "not_declared" },
  nutrition: { basis: "per_100g", energy_kcal: 0, protein_g: 0, carbohydrate_g: 0, total_sugars_g: 0, total_fat_g: 0 },
};
