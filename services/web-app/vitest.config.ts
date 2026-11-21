import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

const TEST_EXCLUDE = [
  "**/node_modules/**",
  "**/dist/**",
  "**/cypress/**",
  "**/.{idea,git,cache,output,temp}/**",
  "**/tests/e2e/**",
];

// Тяжёлые экраны Студии шаблонов («Результат», новое пространство и их страницы): каждый тест
// рисует целое дерево с несколькими запросами, а на медленном раннере CI это не укладывается
// в 5 с по умолчанию. Предел для этих папок общий и явный, сами проверки не меняются.
const HEAVY_STUDIO_DIRS = [
  "src/features/pack-outcome/**",
  "src/features/pack-space/**",
  "src/pages/PackStudioPage/**",
];

export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify("0.0.0-test"),
    __BUILD_ID__: JSON.stringify("test-build"),
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
    css: true,
    projects: [
      {
        extends: true,
        test: {
          name: "default",
          include: ["src/**/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}"],
          exclude: [...TEST_EXCLUDE, ...HEAVY_STUDIO_DIRS],
        },
      },
      {
        extends: true,
        test: {
          name: "studio-heavy",
          include: HEAVY_STUDIO_DIRS.map(
            (dir) => `${dir}/*.{test,spec}.{js,mjs,cjs,ts,mts,cts,jsx,tsx}`,
          ),
          exclude: TEST_EXCLUDE,
          testTimeout: 60_000,
          hookTimeout: 60_000,
          setupFiles: ["./vitest.setup.ts", "./vitest.heavy.setup.ts"],
        },
      },
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html", "lcov", "json-summary", "cobertura"],
      reportsDirectory: process.env.VITEST_REPORTS_DIR ?? "coverage",
      clean: true,
      exclude: [
        "node_modules/",
        "dist/",
        "storybook-static/",
        "build/",
        "coverage/",
        "public/",
        "**/*.config.*",
        "**/*.test.*",
        "**/*.spec.*",
        "**/*.stories.*",
        "**/types.ts",
        "**/*.d.ts",
        "src/main.tsx",
      ],
      thresholds: {
        lines: 0,
        functions: 0,
        branches: 0,
        statements: 0,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
      "@app": path.resolve(import.meta.dirname, "./src/app"),
      "@pages": path.resolve(import.meta.dirname, "./src/pages"),
      "@widgets": path.resolve(import.meta.dirname, "./src/widgets"),
      "@features": path.resolve(import.meta.dirname, "./src/features"),
      "@entities": path.resolve(import.meta.dirname, "./src/entities"),
      "@shared": path.resolve(import.meta.dirname, "./src/shared"),
    },
  },
});
