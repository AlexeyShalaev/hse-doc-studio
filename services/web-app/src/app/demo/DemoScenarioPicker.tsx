import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { FlaskConical } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { resetWorld } from "./routes";
import { useDemoScenarioStore } from "./scenarioStore";
import { SCENARIOS, type DemoScenario } from "./scenarios";

const GROUPS: DemoScenario["group"][] = ["connect", "state", "problem"];

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
      style={{ left: 12, bottom: 40, zIndex: 110 }}
      data-testid="git-demo-picker"
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
            }}
            aria-label={t("demo.open")}
          >
            <FlaskConical size={14} aria-hidden />
            <span>{t(`demo.scenario.${scenarioId}.title`)}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent
          width={340}
          side="top"
          align="start"
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
          {GROUPS.map((group) => (
            <div key={group} style={{ padding: "6px 6px 2px" }}>
              <div
                style={{
                  fontSize: 10.5,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "var(--fg-3)",
                  padding: "6px 8px 4px",
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
                    padding: "6px 8px",
                    borderRadius: 6,
                    background:
                      scenario.id === scenarioId
                        ? "var(--bg-3)"
                        : "transparent",
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
          ))}
          <div
            style={{
              margin: "6px 0 0",
              padding: "10px 14px",
              borderTop: "1px solid var(--border)",
              fontSize: 11.5,
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
