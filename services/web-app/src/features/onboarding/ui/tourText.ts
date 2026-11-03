import { useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import type { OnboardingAnswers } from "@entities/onboarding";
import { toast } from "@shared/lib";
import type { TourOverlayLabels } from "@shared/ui/Tour";
import { textVariant, type DemoAction, type TourStep } from "../model/scenario";
import { useOnboardingStore } from "../model/onboardingStore";
import { useOnboardingProgress } from "../model/useOnboardingProgress";

export const useTourLabels = (
  index: number,
  total: number,
): TourOverlayLabels => {
  const { t } = useTranslation("onboarding");
  return {
    next: t("tour.next"),
    back: t("tour.back"),
    skip: t("tour.skip"),
    finish: t("tour.finish"),
    close: t("tour.close"),
    progress: t("tour.progress", { current: index + 1, total }),
  };
};

export const useStepText = () => {
  const { t } = useTranslation("onboarding");
  return useCallback(
    (step: TourStep, answers: OnboardingAnswers) => {
      const variant = textVariant(step, answers);
      const base = `steps.${step.textKey}`;
      return {
        title: t(`${base}.title`),
        body: variant
          ? t(`${base}.body_${variant}`, { defaultValue: t(`${base}.body`) })
          : t(`${base}.body`),
      };
    },
    [t],
  );
};

export const ACTION_LABEL: Record<DemoAction, string> = {
  create: "actions.create",
  edit: "actions.edit",
  build: "actions.build",
  "ask-agent": "actions.askAgent",
  "resolve-comment": "actions.resolve",
  "git-sync": "actions.sync",
};

/** Пропуск тура в любом месте: статус skipped, подсказка где найти тур снова. */
export const useSkipOnboarding = () => {
  const { t } = useTranslation("onboarding");
  const close = useOnboardingStore((s) => s.close);
  const save = useOnboardingProgress();
  const navigate = useNavigate();
  return useCallback(
    (options?: { leaveDemo?: boolean }) => {
      save({ status: "skipped", step: "" });
      close();
      toast.info(t("tour.skippedToast"));
      if (options?.leaveDemo) void navigate("/");
    },
    [save, close, t, navigate],
  );
};
