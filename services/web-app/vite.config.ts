import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { readFileSync, writeFileSync } from "fs";

const { version } = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
) as { version: string };

const emitVersionJson = (): Plugin => ({
  name: "emit-version-json",
  writeBundle(options) {
    const outDir = options.dir ?? "dist";
    writeFileSync(
      path.join(outDir, "version.json"),
      JSON.stringify({ version }),
    );
  },
});

// Сторонние пакеты по чанкам: редко меняющийся вендор кэшируется отдельно от кода.
const VENDOR_CHUNKS: Record<string, string[]> = {
  vendor: ["react", "react-dom", "react-router"],
  "query-vendor": ["@tanstack/react-query"],
  "table-vendor": ["@tanstack/react-table", "@tanstack/react-virtual"],
  "radix-vendor": [
    "@radix-ui/react-dialog",
    "@radix-ui/react-dropdown-menu",
    "@radix-ui/react-select",
    "@radix-ui/react-tabs",
    "@radix-ui/react-tooltip",
  ],
  "chart-vendor": ["recharts"],
  "icons-vendor": ["lucide-react"],
  "command-palette": ["cmdk"],
  "editor-vendor": [
    "@codemirror/state",
    "@codemirror/view",
    "@codemirror/commands",
    "@codemirror/language",
    "@codemirror/autocomplete",
    "@codemirror/search",
    "@codemirror/lint",
    "@lezer/highlight",
    "@lezer/common",
    "codemirror-lang-latex",
  ],
};

const chunkFor = (id: string): string | undefined => {
  const match =
    /node_modules\/(?:\.pnpm\/[^/]+\/node_modules\/)?((?:@[^/]+\/)?[^/]+)/.exec(
      id.replace(/\\/g, "/"),
    );
  const pkg = match?.[1];
  if (!pkg) return undefined;
  return Object.entries(VENDOR_CHUNKS).find(([, pkgs]) =>
    pkgs.includes(pkg),
  )?.[0];
};

export default defineConfig(({ mode }) => {
  const env = mode === "development" ? loadEnv(mode, process.cwd(), "") : {};
  const rawProxyTarget = env.VITE_DEV_PROXY_TARGET?.trim() ?? "";
  const devProxyTarget =
    rawProxyTarget !== "" ? rawProxyTarget : "http://localhost:17240";

  return {
    define: {
      __APP_VERSION__: JSON.stringify(version),
    },

    plugins: [react(), emitVersionJson()],

    optimizeDeps: {
      entries: ["./index.html"],
    },

    resolve: {
      // @codemirror/state (and view) must resolve to a single copy — duplicates
      // cause silent "Unrecognized extension value" failures.
      dedupe: ["@codemirror/state", "@codemirror/view"],
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

    server: {
      port: 3000,
      host: "0.0.0.0",
      proxy:
        mode === "development"
          ? {
              "/api": {
                target: devProxyTarget,
                changeOrigin: true,
                secure: devProxyTarget.startsWith("https:"),
              },
            }
          : {},
    },

    preview: {
      port: 3000,
      host: "0.0.0.0",
      headers: {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
      },
    },

    build: {
      target: "es2022",
      sourcemap: true,
      rollupOptions: {
        output: {
          // Vite 8 (Rolldown) принимает manualChunks только функцией: пакет из
          // node_modules → имя чанка по таблице ниже, остальное — по умолчанию.
          manualChunks: (id: string) => chunkFor(id),
          // Админка уходит в динамический чанк assets/admin-*.js (по имени его
          // узнаёт scripts/verify-admin-chunk.mjs), её словари в отдельные
          // locale-admin-*: так ни то ни другое не входит в entry.
          chunkFileNames: (chunk: { facadeModuleId?: string | null }) => {
            const id = (chunk.facadeModuleId ?? "").replace(/\\/g, "/");
            if (id.endsWith("/src/pages/AdminPage/index.ts")) {
              return "assets/admin-[hash].js";
            }
            if (/\/locales\/[a-z]{2}\/admin\//.test(id)) {
              return "assets/locale-admin-[hash].js";
            }
            return "assets/[name]-[hash].js";
          },
        },
      },
    },
  };
});
