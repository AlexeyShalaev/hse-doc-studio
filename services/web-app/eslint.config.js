import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import prettier from "eslint-plugin-prettier";
import prettierConfig from "eslint-config-prettier";
import tanstackQuery from "@tanstack/eslint-plugin-query";
import i18next from "eslint-plugin-i18next";

export default tseslint.config(
  {
    ignores: [
      "dist",
      "build",
      "coverage",
      ".storybook",
      "storybook-static",
      "public/mockServiceWorker.js",
    ],
  },
  {
    extends: [
      js.configs.recommended,
      ...tseslint.configs.strictTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
      prettierConfig,
    ],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        project: ["./tsconfig.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      prettier,
      "@tanstack/query": tanstackQuery,
      i18next,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-hooks/exhaustive-deps": "error",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],

      // TypeScript strict rules
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports" },
      ],
      "@typescript-eslint/consistent-type-definitions": ["error", "type"],
      "@typescript-eslint/no-unsafe-assignment": "warn", // Downgrade from error to warning for Zod schemas
      "@typescript-eslint/no-unsafe-call": "warn",
      "@typescript-eslint/no-unsafe-member-access": "warn",
      "@typescript-eslint/no-misused-promises": "warn",
      "@typescript-eslint/require-await": "warn",
      "@typescript-eslint/restrict-template-expressions": "warn",
      "@typescript-eslint/prefer-nullish-coalescing": "warn",
      "@typescript-eslint/no-unsafe-argument": "warn",
      "@typescript-eslint/no-unnecessary-condition": "warn",
      "@typescript-eslint/no-floating-promises": "warn",
      "@typescript-eslint/no-confusing-void-expression": "warn",
      "@typescript-eslint/no-non-null-assertion": "warn",

      "react-hooks/immutability": "off",

      // Code quality
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "prettier/prettier": ["error", { endOfLine: "auto" }],
      "@typescript-eslint/no-deprecated": "off", // Temporarily disable for Zod schema methods

      // TanStack Query rules
      "@tanstack/query/exhaustive-deps": "error",
      "@tanstack/query/no-rest-destructuring": "warn",
      "@tanstack/query/stable-query-client": "error",

      // i18next rules. Kept OFF on purpose: the interface is fully i18n'd
      // (RU+EN), but the codebase legitimately contains many non-translatable
      // string literals (brand/tech names like Docker/LaTeX/PDF, GOST refs,
      // regex patterns, CSS class names, search keywords), so no-literal-string
      // would flood with false positives. The real i18n guard is
      // `pnpm lint:i18n` (scripts/verify-i18n-keys.mjs), which verifies every
      // t() key resolves, plus the Cyrillic-in-source audit.
      "i18next/no-literal-string": "off",
    },
  },
);
