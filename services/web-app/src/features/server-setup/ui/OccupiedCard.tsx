import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ResultFrame } from "@shared/ui/ResultFrame";
import { StepHeading } from "./parts";

export type OccupiedCardProps = {
  /** Вошёл не администратор: форма входа не нужна, ему остаётся ждать. */
  signedIn?: boolean;
  /** Форма входа администратора: её подставляет страница. */
  signIn?: ReactNode;
};

/**
 * Нейтральный экран для всех, кроме администратора, который ведёт мастер:
 * проигравший гонку за первого админа и тот, у кого админ пришёл из окружения.
 * Ничего не обещает и не раскрывает, кто и что уже настроил.
 */
export const OccupiedCard = ({
  signedIn = false,
  signIn = null,
}: OccupiedCardProps) => {
  const { t } = useTranslation("auth");
  return (
    <section
      data-testid="setup-occupied"
      data-signed-in={signedIn}
      aria-labelledby="setup-title"
    >
      <StepHeading
        id="setup-title"
        title={t("setup.occupied.title")}
        lead={t("setup.occupied.lead")}
      />
      <ResultFrame
        tone="info"
        role="status"
        testId="setup-occupied-frame"
        title={t(
          signedIn ? "setup.occupied.waiting" : "setup.occupied.signInFirst",
        )}
      >
        <p style={{ margin: 0, fontSize: 12.5, color: "var(--fg-2)" }}>
          {t(
            signedIn
              ? "setup.occupied.waitingHint"
              : "setup.occupied.signInFirstHint",
          )}
        </p>
      </ResultFrame>
      {!signedIn && signIn && (
        <div
          style={{
            marginTop: 20,
            paddingTop: 20,
            borderTop: "1px solid var(--border)",
          }}
        >
          {signIn}
        </div>
      )}
    </section>
  );
};
