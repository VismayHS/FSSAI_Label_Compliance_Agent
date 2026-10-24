import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", ".impeccable", "src/components/reactbits"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "no-restricted-syntax": ["error", {
        selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
        message: "Label text is untrusted input (L4): render it as text, never as HTML.",
      }],
    },
  },
  { files: ["scripts/**/*.mjs"], languageOptions: { globals: globals.node } },
  { files: ["public/**/*.js"], languageOptions: { globals: globals.browser } },
);
