import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@app";
import "./index.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root element not found");
}

// Демо серверного режима (VITE_SERVER_DEMO=1) и синхронизации по git (VITE_GIT_DEMO=1): подменяем транспорт до первого
// запроса. Условие вычисляется при сборке, поэтому в обычный бандл демо не входит.
const prepare = async (): Promise<void> => {
  if (import.meta.env.VITE_SERVER_DEMO === "1") {
    const { installServerDemo } = await import("@app/demo");
    installServerDemo();
  } else if (import.meta.env.VITE_GIT_DEMO === "1") {
    const { installGitDemo } = await import("@app/demo");
    installGitDemo();
  }
};

void prepare().then(() => {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
