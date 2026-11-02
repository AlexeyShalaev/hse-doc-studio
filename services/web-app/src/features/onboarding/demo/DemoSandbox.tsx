import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useState,
  useSyncExternalStore,
} from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { FlaskConical, LogOut, RotateCcw } from "lucide-react";
import { useBootstrap } from "@entities/session";
import { usePacks } from "@entities/template-catalog";
import { TourOverlay } from "@shared/ui/Tour";
import { suggestTemplate } from "../lib/templateSuggestion";
import { useOnboardingStore } from "../model/onboardingStore";
import { buildSteps, type DemoAction } from "../model/scenario";
import {
  currentStep,
  isBlocked,
  startTour,
  tourReducer,
} from "../model/tourMachine";
import { useOnboardingProgress } from "../model/useOnboardingProgress";
import {
  ACTION_LABEL,
  useSkipOnboarding,
  useStepText,
  useTourLabels,
} from "../ui/tourText";
import { demoContentFor } from "./content";
import {
  CreatePanel,
  EditorPanel,
  FilesPanel,
  PreviewPanel,
  SidePanel,
  type SideTab,
} from "./DemoPanels";
import { createDemoWorld, type DemoWorld } from "./world";

const AUTOPLAY_DELAY_MS = 2200;

const TAB_FOR_STEP: Record<string, SideTab> = {
  "demo.agent": "agent",
  "demo.review": "review",
  "demo.git": "git",
};

const runAction = (
  world: DemoWorld,
  action: DemoAction,
  templateLabel: string,
): void => {
  switch (action) {
    case "create":
      world.createProject(templateLabel);
      return;
    case "edit":
      world.insertTopic();
      return;
    case "build":
      void world.build();
      return;
    case "ask-agent":
      void world.askAgent("check");
      return;
    case "resolve-comment":
      world.resolveComment();
      return;
    case "git-sync":
      void world.sync();
      return;
  }
};

/** Демо-проект в песочнице с туром поверх: весь сценарий от шаблона до git. */
export const DemoSandbox = () => {
  const [params] = useSearchParams();
  const phase = useOnboardingStore((s) => s.phase);
  const openDemo = useOnboardingStore((s) => s.openDemo);
  const [generation, setGeneration] = useState(0);

  // Пришли прямой ссылкой или из меню справки: демо идёт само по себе.
  useEffect(() => {
    if (phase !== "demo")
      openDemo({ autoplay: params.get("autoplay") === "1" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <DemoSession
      key={generation}
      onRestart={() => {
        setGeneration((g) => g + 1);
      }}
    />
  );
};

const DemoSession = ({ onRestart }: { onRestart: () => void }) => {
  const { t, i18n } = useTranslation("onboarding");
  const navigate = useNavigate();
  const answers = useOnboardingStore((s) => s.answers);
  const autoplay = useOnboardingStore((s) => s.autoplay);
  const goTo = useOnboardingStore((s) => s.goTo);
  const save = useOnboardingProgress();
  const skip = useSkipOnboarding();
  const stepText = useStepText();
  const { data: bootstrap } = useBootstrap();
  const packs = usePacks();
  const content = demoContentFor(i18n.language);
  const templateLabel =
    suggestTemplate(packs.data ?? [], answers, i18n.language)?.label ??
    content.templateFallback;

  const [world] = useState<DemoWorld>(() =>
    createDemoWorld({ content, speed: autoplay ? 1.5 : 1 }),
  );
  const state = useSyncExternalStore(world.subscribe, world.getState);

  const mode = bootstrap?.mode ?? "local";
  const isAdmin = bootstrap?.user?.is_instance_admin === true;
  const steps = useMemo(
    () => buildSteps(answers, { mode, isAdmin }, ["demo"]),
    [answers, mode, isAdmin],
  );
  const [tour, dispatch] = useReducer(tourReducer, steps, startTour);
  const step = currentStep(tour);
  const blocked = isBlocked(tour);
  // Вкладка боковой панели следует за шагом тура, пока человек не выбрал другую сам.
  const [picked, setPicked] = useState<{
    stepId: string | undefined;
    tab: SideTab;
  }>({ stepId: undefined, tab: "agent" });

  useEffect(
    () =>
      world.onEvent((event) => {
        dispatch({ type: "event", event });
      }),
    [world],
  );

  useEffect(() => {
    if (!step) return;
    save({ status: "in_progress", step: step.id });
  }, [step, save]);

  useEffect(() => {
    if (tour.status === "finished") {
      goTo("finish");
      void navigate("/");
    } else if (tour.status === "skipped") {
      skip();
    }
  }, [tour.status, goTo, navigate, skip]);

  const tab =
    picked.stepId === step?.id
      ? picked.tab
      : ((step && TAB_FOR_STEP[step.id]) ?? picked.tab);

  const busy =
    state.build.status === "running" || state.agentBusy || state.git.busy;

  const primary = useCallback(() => {
    if (!step) return;
    if (blocked && step.action) {
      if (!busy) runAction(world, step.action, templateLabel);
      return;
    }
    dispatch({ type: "next" });
  }, [step, blocked, busy, world, templateLabel]);

  // Автопоказ для записи роликов: сам выполняет действие шага и идёт дальше.
  useEffect(() => {
    if (!autoplay || !step || busy) return;
    const timer = setTimeout(primary, AUTOPLAY_DELAY_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [autoplay, step, busy, primary, tour.done]);

  const labels = useTourLabels(tour.index, tour.steps.length);
  const text = step ? stepText(step, answers) : null;

  return (
    <div
      className="flex flex-col flex-1 bg-bg-0"
      style={{ minHeight: 0 }}
      data-testid="demo-sandbox"
    >
      <div
        className="flex items-center"
        style={{
          gap: 10,
          padding: "8px 16px",
          borderBottom: "1px solid var(--border)",
          background: "color-mix(in oklch, var(--accent) 10%, var(--bg-1))",
          flexWrap: "wrap",
        }}
      >
        <span className="chip" style={{ color: "var(--accent)" }}>
          <FlaskConical size={11} />
          {t("tour.demoBadge")}
        </span>
        <strong style={{ fontSize: 13 }}>
          {state.project?.name ?? content.projectName}
        </strong>
        <span className="dim flex-1" style={{ fontSize: 12, minWidth: 200 }}>
          {t("demo.banner")}
        </span>
        <button type="button" className="btn ghost sm" onClick={onRestart}>
          <RotateCcw size={12} />
          {t("demo.restart")}
        </button>
        <button
          type="button"
          className="btn sm"
          data-testid="demo-exit"
          onClick={() => {
            if (tour.status === "running") skip({ leaveDemo: true });
            else void navigate("/");
          }}
        >
          <LogOut size={12} />
          {t("demo.exit")}
        </button>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
          padding: 12,
          display: "grid",
          gap: 12,
          gridTemplateColumns:
            "repeat(auto-fit, minmax(min(240px, 100%), 1fr))",
          alignItems: "stretch",
        }}
      >
        {state.project ? (
          <FilesPanel state={state} world={world} />
        ) : (
          <CreatePanel
            templateLabel={templateLabel}
            onCreate={() => {
              world.createProject(templateLabel);
            }}
          />
        )}
        <EditorPanel state={state} world={world} />
        <PreviewPanel state={state} world={world} />
        <SidePanel
          tab={tab}
          onTab={(next) => {
            setPicked({ stepId: step?.id, tab: next });
          }}
          state={state}
          world={world}
          content={content}
        />
      </div>

      {step && text && (
        <TourOverlay
          stepId={step.id}
          target={step.target ? `[data-tour="${step.target}"]` : undefined}
          badge={t("tour.demoBadge")}
          title={text.title}
          body={text.body}
          index={tour.index}
          total={tour.steps.length}
          labels={labels}
          interactive={step.interactive}
          primaryLabel={
            blocked && step.action ? t(ACTION_LABEL[step.action]) : undefined
          }
          primaryBusy={blocked && busy}
          onNext={primary}
          onBack={() => {
            dispatch({ type: "back" });
          }}
          onSkip={() => {
            dispatch({ type: "skip" });
          }}
        />
      )}
    </div>
  );
};
