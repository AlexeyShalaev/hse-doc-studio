import { useEffect, useMemo, useReducer } from "react";
import { useLocation, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { LocalStudioLink } from "@entities/local-studio";
import { useGeneralBuildAvailability } from "@entities/runner";
import { useBootstrap } from "@entities/session";
import { usePacks } from "@entities/template-catalog";
import { Modal } from "@shared/ui/Modal";
import { TourOverlay } from "@shared/ui/Tour";
import { resolveBuildAvailability } from "../../lib/buildAvailability";
import { DEMO_PATH } from "../../lib/paths";
import { suggestTemplate } from "../../lib/templateSuggestion";
import { useOnboardingStore } from "../../model/onboardingStore";
import { buildSteps, roleOf } from "../../model/scenario";
import { currentStep, startTour, tourReducer } from "../../model/tourMachine";
import { useOnboardingProgress } from "../../model/useOnboardingProgress";
import { useSkipOnboarding, useStepText, useTourLabels } from "../tourText";
import { Questionnaire } from "./Questionnaire";

const useScenarioContext = () => {
  const { data } = useBootstrap();
  return {
    mode: data?.mode ?? "local",
    isAdmin: data?.user?.is_instance_admin === true,
  } as const;
};

const IntroDialog = () => {
  const answers = useOnboardingStore((s) => s.answers);
  const setAnswers = useOnboardingStore((s) => s.setAnswers);
  const goTo = useOnboardingStore((s) => s.goTo);
  const save = useOnboardingProgress();
  const skip = useSkipOnboarding();
  const navigate = useNavigate();

  useEffect(() => {
    save({ status: "in_progress", step: "intro" });
  }, [save]);

  return (
    <Modal
      isOpen
      onClose={() => {
        skip();
      }}
      width={520}
    >
      <div data-testid="onboarding-intro">
        <Questionnaire
          initial={answers}
          onSkipAll={() => {
            skip();
          }}
          onDone={(next, where) => {
            setAnswers(next);
            save({ answers: next });
            if (where === "demo") {
              goTo("demo");
              void navigate(DEMO_PATH);
            } else {
              goTo("interface");
              void navigate("/");
            }
          }}
        />
      </div>
    </Modal>
  );
};

const InterfaceTour = () => {
  const answers = useOnboardingStore((s) => s.answers);
  const goTo = useOnboardingStore((s) => s.goTo);
  const ctx = useScenarioContext();
  const steps = useMemo(
    () => buildSteps(answers, ctx, ["interface"]),
    [answers, ctx],
  );
  const [state, dispatch] = useReducer(tourReducer, steps, startTour);
  const save = useOnboardingProgress();
  const skip = useSkipOnboarding();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const stepText = useStepText();
  const labels = useTourLabels(state.index, state.steps.length);
  const step = currentStep(state);

  useEffect(() => {
    if (step) save({ step: step.id });
  }, [step, save]);

  useEffect(() => {
    if (state.status === "finished") {
      goTo("demo");
      void navigate(DEMO_PATH);
    } else if (state.status === "skipped") {
      skip();
    }
  }, [state.status, goTo, navigate, skip]);

  // Экскурсия идёт по главной: ушли с неё — тур подождёт, а не подсветит пустоту.
  if (!step || pathname !== "/") return null;
  const text = stepText(step, answers);
  return (
    <TourOverlay
      stepId={step.id}
      target={step.target ? `[data-tour="${step.target}"]` : undefined}
      title={text.title}
      body={text.body}
      index={state.index}
      total={state.steps.length}
      labels={labels}
      onNext={() => {
        dispatch({ type: "next" });
      }}
      onBack={() => {
        dispatch({ type: "back" });
      }}
      onSkip={() => {
        dispatch({ type: "skip" });
      }}
    />
  );
};

const FinishDialog = () => {
  const { t, i18n } = useTranslation("onboarding");
  const answers = useOnboardingStore((s) => s.answers);
  const close = useOnboardingStore((s) => s.close);
  const save = useOnboardingProgress();
  const navigate = useNavigate();
  const { data: bootstrap } = useBootstrap();
  const packs = usePacks();
  const role = roleOf(answers);
  const template = suggestTemplate(packs.data ?? [], answers, i18n.language);
  const mode = bootstrap?.mode ?? "local";
  const runners = useGeneralBuildAvailability(mode === "server");
  const build = resolveBuildAvailability(mode, runners.data);

  useEffect(() => {
    save({ step: "finish" });
  }, [save]);

  const complete = () => {
    save({ status: "completed", step: "" });
    close();
  };

  return (
    <Modal
      isOpen
      onClose={complete}
      width={520}
      title={t("finish.title")}
      footer={
        <div
          className="flex justify-end"
          style={{ gap: "0.5rem", flexWrap: "wrap" }}
        >
          <button
            type="button"
            className="btn ghost"
            onClick={complete}
            data-testid="onboarding-finish-later"
          >
            {t("finish.later")}
          </button>
          <button
            type="button"
            className="btn primary"
            autoFocus
            data-testid="onboarding-finish-create"
            onClick={() => {
              complete();
              const query = template
                ? `?pack=${encodeURIComponent(template.packId)}&template=${encodeURIComponent(template.templateId)}`
                : "";
              void navigate(`/wizard${query}`);
            }}
          >
            {t("finish.createGeneric")}
          </button>
        </div>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.625rem", fontSize: "0.84375rem", lineHeight: 1.5 }}
        data-testid="onboarding-finish"
      >
        <p style={{ margin: 0 }}>{t("finish.body")}</p>
        {template && (
          <p style={{ margin: 0 }} data-testid="onboarding-template">
            {t("finish.suggested", { template: template.label })}
          </p>
        )}
        {role === "admin" && <p style={{ margin: 0 }}>{t("finish.admin")}</p>}
        {role === "supervisor" && (
          <p style={{ margin: 0 }}>{t("finish.supervisor")}</p>
        )}
        <p
          className="dim"
          style={{ margin: 0, fontSize: "0.78125rem" }}
          data-testid="onboarding-build-note"
          data-availability={build}
        >
          {t(`finish.build.${build}`)}
        </p>
        {build === "unavailable" && (
          // Переход на «Локальную версию» закрывает итог как пройденный тур.
          <span
            style={{ alignSelf: "flex-start" }}
            onClick={complete}
            data-testid="onboarding-local-version"
          >
            <LocalStudioLink variant="button" className="sm" />
          </span>
        )}
      </div>
    </Modal>
  );
};

/** Анкета, экскурсия по главной и итог: ленивый чанк, пока тур идёт. */
export const OnboardingFlow = () => {
  const phase = useOnboardingStore((s) => s.phase);
  if (phase === "intro") return <IntroDialog />;
  if (phase === "interface") return <InterfaceTour />;
  if (phase === "finish") return <FinishDialog />;
  return null;
};
