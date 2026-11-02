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
        padding: 16,
        marginTop: 16,
        display: "flex",
        alignItems: "center",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <Compass size={18} style={{ color: "var(--accent)", flexShrink: 0 }} />
      <div className="flex flex-col flex-1" style={{ gap: 4, minWidth: 200 }}>
        <strong style={{ fontSize: 13.5, color: "var(--fg-0)" }}>
          {t("restart.title")}
          {data && (
            <span className="chip" style={{ marginLeft: 8, fontWeight: 400 }}>
              {t(STATUS_KEY[data.status])}
            </span>
          )}
        </strong>
        <span className="dim" style={{ fontSize: 12.5 }}>
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
