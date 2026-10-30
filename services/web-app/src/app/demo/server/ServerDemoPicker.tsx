import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Server } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { resetServerWorld } from "./routes";
import { useServerDemoScenarioStore } from "./scenarioStore";
import { SERVER_SCENARIOS, type ServerDemoScenarioId } from "./scenarios";

// Переключатель сценариев серверного демо. Виден только в сборке с
// VITE_SERVER_DEMO=1: в обычном приложении его нет вовсе.
export const ServerDemoPicker = () => {
  const { t } = useTranslation("session");
  const queryClient = useQueryClient();
  const scenarioId = useServerDemoScenarioStore((s) => s.scenarioId);
  const setScenarioId = useServerDemoScenarioStore((s) => s.setScenarioId);
  const [open, setOpen] = useState(false);

  const choose = (id: ServerDemoScenarioId) => {
    resetServerWorld(id);
    setScenarioId(id);
    // Сессия и все ответы теперь другие: перечитываем их разом.
    void queryClient.invalidateQueries();
    setOpen(false);
  };

  return (
    // Справа внизу над строкой состояния, ниже окон и выезжающих панелей
    // (z-index 90+): не ложится на меню админки и не спорит с диалогами.
    <div
      className="fixed"
      style={{ right: 16, bottom: 36, zIndex: 80 }}
      data-testid="server-demo-picker"
    >
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="btn sm"
            style={{
              gap: 6,
              boxShadow: "0 2px 10px rgba(0, 0, 0, 0.25)",
              background: "var(--bg-1)",
              border: "1px dashed var(--c-warn)",
              color: "var(--fg-1)",
            }}
            aria-label={t("demo.open")}
          >
            <Server size={14} aria-hidden style={{ color: "var(--c-warn)" }} />
            <span style={{ color: "var(--c-warn)", fontWeight: 600 }}>
              {t("demo.prefix")}
            </span>
            <span>{t(`demo.scenario.${scenarioId}.title`)}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          width={340}
          side="top"
          align="end"
          aria-label={t("demo.title")}
          style={{ maxHeight: 520, overflowY: "auto", padding: 0 }}
        >
          <div
            style={{
              padding: "10px 14px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13 }}>
              {t("demo.title")}
            </div>
            <div style={{ fontSize: 11.5, color: "var(--fg-2)", marginTop: 2 }}>
              {t("demo.subtitle")}
            </div>
          </div>
          <div style={{ padding: 6 }}>
            {SERVER_SCENARIOS.map((scenario) => (
              <button
                key={scenario.id}
                type="button"
                onClick={() => {
                  choose(scenario.id);
                }}
                aria-current={scenario.id === scenarioId ? "true" : undefined}
                className={clsx("w-full text-left")}
                style={{
                  display: "block",
                  padding: "6px 8px",
                  borderRadius: 6,
                  background:
                    scenario.id === scenarioId ? "var(--bg-3)" : "transparent",
                  cursor: "pointer",
                }}
              >
                <div style={{ fontSize: 12.5, color: "var(--fg-0)" }}>
                  {t(`demo.scenario.${scenario.id}.title`)}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--fg-2)" }}>
                  {t(`demo.scenario.${scenario.id}.hint`)}
                </div>
              </button>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
};
