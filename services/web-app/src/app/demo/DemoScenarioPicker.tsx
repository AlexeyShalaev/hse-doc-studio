import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { FlaskConical } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { resetWorld } from "./routes";
import { useDemoScenarioStore } from "./scenarioStore";
import { SCENARIOS, type DemoScenario } from "./scenarios";

const GROUPS: DemoScenario["group"][] = [
  "connect",
  "state",
  "problem",
  "provider",
];

// Переключатель демо-сценариев синхронизации. Виден только в сборке с
// VITE_GIT_DEMO=1: в обычном приложении его нет вовсе.
export const DemoScenarioPicker = () => {
  const { t } = useTranslation("gitSync");
  const queryClient = useQueryClient();
  const scenarioId = useDemoScenarioStore((s) => s.scenarioId);
  const setScenarioId = useDemoScenarioStore((s) => s.setScenarioId);
  const [open, setOpen] = useState(false);

  const choose = (id: DemoScenario["id"]) => {
    resetWorld(id);
    setScenarioId(id);
    // Все ответы сервера теперь другие: перечитываем их разом.
    void queryClient.invalidateQueries();
    setOpen(false);
  };

  return (
    <div
      className="fixed"
      style={{ left: "0.75rem", bottom: "2.5rem", zIndex: 110 }}
      data-testid="git-demo-picker"
    >
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="btn sm"
            style={{
              gap: "0.375rem",
              boxShadow: "0 2px 10px rgba(0, 0, 0, 0.25)",
              background: "var(--bg-1)",
            }}
            aria-label={t("demo.open")}
          >
            <FlaskConical size="0.875rem" aria-hidden />
            <span>{t(`demo.scenario.${scenarioId}.title`)}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          width={340}
          side="top"
          align="start"
          aria-label={t("demo.title")}
          style={{ maxHeight: "32.5rem", overflowY: "auto", padding: 0 }}
        >
          <div
            style={{
              padding: "0.625rem 0.875rem",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <div style={{ fontWeight: 600, fontSize: "0.8125rem" }}>
              {t("demo.title")}
            </div>
            <div
              style={{
                fontSize: "0.71875rem",
                color: "var(--fg-2)",
                marginTop: "0.125rem",
              }}
            >
              {t("demo.subtitle")}
            </div>
          </div>
          {GROUPS.map((group) => (
            <div key={group} style={{ padding: "0.375rem 0.375rem 0.125rem" }}>
              <div
                style={{
                  fontSize: "0.65625rem",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "var(--fg-3)",
                  padding: "0.375rem 0.5rem 0.25rem",
                }}
              >
                {t(`demo.group.${group}`)}
              </div>
              {SCENARIOS.filter((s) => s.group === group).map((scenario) => (
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
                    padding: "0.375rem 0.5rem",
                    borderRadius: "0.375rem",
                    background:
                      scenario.id === scenarioId
                        ? "var(--bg-3)"
                        : "transparent",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ fontSize: "0.78125rem", color: "var(--fg-0)" }}>
                    {t(`demo.scenario.${scenario.id}.title`)}
                  </div>
                  <div style={{ fontSize: "0.71875rem", color: "var(--fg-2)" }}>
                    {t(`demo.scenario.${scenario.id}.hint`)}
                  </div>
                </button>
              ))}
            </div>
          ))}
          <div
            style={{
              margin: "0.375rem 0 0",
              padding: "0.625rem 0.875rem",
              borderTop: "1px solid var(--border)",
              fontSize: "0.71875rem",
              color: "var(--fg-2)",
              lineHeight: 1.5,
            }}
          >
            <div style={{ fontWeight: 600, color: "var(--fg-1)" }}>
              {t("demo.urlTitle")}
            </div>
            {t("demo.urlHelp")}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
};
