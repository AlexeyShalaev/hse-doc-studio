import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import { Setting, SettingHead } from "./Setting";

const ENGINES = ["xelatex", "lualatex", "pdflatex"] as const;
type Engine = (typeof ENGINES)[number];

// 1–2 практически не работают для документов с hyperref/TOC — latexmk
// упрётся в потолок до сходимости ссылок и упадёт. Минимум 3.
const PASSES = [3, 4, 5, 6, 8] as const;
type Passes = (typeof PASSES)[number];

// Каждая сборка — отдельный texlive-контейнер; лимит защищает машину при
// «Собрать всё» (командный проект = 15+ документов). Лишние сборки ждут
// в очереди, а не падают.
const CONCURRENCY = [1, 2, 3, 4, 6, 8] as const;
type Concurrency = (typeof CONCURRENCY)[number];

export const CompilerSection = () => {
  const { t } = useTranslation("settings");
  const { data, isLoading } = useAppSettings();
  const { mutate: updateSettings, isPending } = useUpdateAppSettings();

  const currentEngine = (data?.default_engine ?? "xelatex") as Engine;
  const currentPasses = (data?.latex_passes ?? 3) as Passes;
  const currentConcurrency = (data?.max_concurrent_compiles ??
    2) as Concurrency;

  const handleEngine = (engine: Engine) => {
    if (engine === currentEngine) return;
    updateSettings(
      { default_engine: engine },
      {
        onSuccess: () => {
          toast.success(t("compiler.engineToast", { engine }));
        },
      },
    );
  };

  const handlePasses = (passes: Passes) => {
    if (passes === currentPasses) return;
    updateSettings(
      { latex_passes: passes },
      {
        onSuccess: () => {
          toast.success(t("compiler.passesToast", { passes }));
        },
      },
    );
  };

  const handleConcurrency = (count: Concurrency) => {
    if (count === currentConcurrency) return;
    updateSettings(
      { max_concurrent_compiles: count },
      {
        onSuccess: () => {
          toast.success(t("compiler.concurrencyToast", { count }));
        },
      },
    );
  };

  return (
    <>
      <SettingHead
        anchorId="compiler"
        title={t("compiler.title")}
        sub={t("compiler.subtitle")}
      />
      <Setting anchorId="compiler-engine" label={t("compiler.engineLabel")}>
        {isLoading ? (
          <Spinner size="sm" />
        ) : (
          <div className="seg">
            {ENGINES.map((e) => (
              <button
                key={e}
                type="button"
                className={clsx(currentEngine === e && "active")}
                onClick={() => {
                  handleEngine(e);
                }}
                disabled={isPending}
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {e}
              </button>
            ))}
          </div>
        )}
      </Setting>
      <Setting
        anchorId="compiler-passes"
        label={t("compiler.passesLabel")}
        hint={t("compiler.passesHint")}
      >
        {isLoading ? (
          <Spinner size="sm" />
        ) : (
          <div className="seg">
            {PASSES.map((p) => (
              <button
                key={p}
                type="button"
                className={clsx(currentPasses === p && "active")}
                onClick={() => {
                  handlePasses(p);
                }}
                disabled={isPending}
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {p}
              </button>
            ))}
          </div>
        )}
      </Setting>
      <Setting
        anchorId="compiler-concurrency"
        label={t("compiler.concurrencyLabel")}
        hint={t("compiler.concurrencyHint")}
      >
        {isLoading ? (
          <Spinner size="sm" />
        ) : (
          <div className="seg">
            {CONCURRENCY.map((c) => (
              <button
                key={c}
                type="button"
                className={clsx(currentConcurrency === c && "active")}
                onClick={() => {
                  handleConcurrency(c);
                }}
                disabled={isPending}
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {c}
              </button>
            ))}
          </div>
        )}
      </Setting>
    </>
  );
};
