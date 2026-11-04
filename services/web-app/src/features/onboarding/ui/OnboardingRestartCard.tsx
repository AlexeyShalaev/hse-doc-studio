import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { Compass } from "lucide-react";
import {
  useOnboardingState,
  useResetOnboarding,
  type OnboardingStatus,
} from "@entities/onboarding";
import { useOnboardingStore } from "../model/onboardingStore";
import { useOnboardingAvailable } from "../model/useOnboardingProgress";

const STATUS_KEY: Record<OnboardingStatus, string> = {
  pending: "restart.statusPending",
  suggested: "restart.statusPending",
  in_progress: "restart.statusInProgress",
  completed: "restart.statusCompleted",
  skipped: "restart.statusSkipped",
};

/** Карточка «Знакомство со Студией» в профиле: статус и «Пройти заново». */
export const OnboardingRestartCard = () => {
  const { t } = useTranslation("onboarding");
  const navigate = useNavigate();
  const available = useOnboardingAvailable();
  const { data } = useOnboardingState({ enabled: available });
  const reset = useResetOnboarding();
  const start = useOnboardingStore((s) => s.start);
  if (!available) return null;

  return (
    <section
      className="card"
      data-testid="onboarding-restart"
      style={{
        padding: "1rem",
        marginTop: "1rem",
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        flexWrap: "wrap",
      }}
    >
      <Compass
        size="1.125rem"
        style={{ color: "var(--accent)", flexShrink: 0 }}
      />
      <div
        className="flex flex-col flex-1"
        style={{ gap: "0.25rem", minWidth: "12.5rem" }}
      >
        <strong style={{ fontSize: "0.84375rem", color: "var(--fg-0)" }}>
          {t("restart.title")}
          {data && (
            <span
              className="chip"
              style={{ marginLeft: "0.5rem", fontWeight: 400 }}
            >
              {t(STATUS_KEY[data.status])}
            </span>
          )}
        </strong>
        <span className="dim" style={{ fontSize: "0.78125rem" }}>
          {t("restart.body")}
        </span>
      </div>
      <button
        type="button"
        className="btn"
        disabled={reset.isPending}
        data-testid="onboarding-restart-button"
        onClick={() => {
          reset.mutate(undefined, {
            onSettled: () => {
              start("manual", data?.answers);
              void navigate("/");
            },
          });
        }}
      >
        {t("restart.button")}
      </button>
    </section>
  );
};
