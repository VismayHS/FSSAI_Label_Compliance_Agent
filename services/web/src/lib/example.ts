import type { LabelCheckRequest } from "../api/types";

/** The spec §4.1 case: a "source of protein" claim, protein declared on the panel. The category is the one
 * the corpus covers (decision 001, CORPUS_CATEGORIES). While the API runs on the contracts' fakes the
 * condition is a PLACEHOLDER (10 g per 100 g), so 8 g routes to revise-and-recheck. */
export const SECTION_41_EXAMPLE: LabelCheckRequest = {
  schema_version: "1.0",
  declared_category: "breakfast-cereals",
  package: { net_quantity: 500, net_quantity_unit: "g", principal_display_panel_cm2: 180 },
  label: {
    product_name: "Multigrain flakes",
    brand_name: "Kheti Foods",
    front_of_pack_text: "Source of protein. Made with 5 grains.",
    claims: ["Source of protein"],
    ingredients: "Wheat (40%), oats (25%), rice, maize, barley, sugar, iodised salt",
    allergen_statement: "Contains: wheat, oats, barley (gluten)",
    veg_status: "veg",
  },
  nutrition: {
    basis: "per_100g",
    energy_kcal: 371,
    protein_g: 8,
    carbohydrate_g: 78,
    total_sugars_g: 12,
    total_fat_g: 3,
  },
};

export const EMPTY_REQUEST: LabelCheckRequest = {
  schema_version: "1.0",
  declared_category: "",
  package: { net_quantity: 0, net_quantity_unit: "g", principal_display_panel_cm2: 0 },
  label: { product_name: "", claims: [], veg_status: "not_declared" },
  nutrition: { basis: "per_100g", energy_kcal: 0, protein_g: 0, carbohydrate_g: 0, total_sugars_g: 0, total_fat_g: 0 },
};
