import { useTranslation } from "react-i18next";
import "./styles";

type ModeSkeletonProps = {
  /** Сколько строк рисовать; по умолчанию шесть. */
  rows?: number;
  testId?: string;
};

/** Серый скелет режима, пока грузится его код или ответ сервера. */
export const ModeSkeleton = ({
  rows = 6,
  testId = "outcome-mode-skeleton",
}: ModeSkeletonProps) => {
  const { t } = useTranslation("packOutcome");
  return (
    <div
      className="po-skeleton"
      role="status"
      aria-busy="true"
      aria-label={t("modes.loading")}
      data-testid={testId}
    >
      {Array.from({ length: rows }, (_, n) => (
        <span
          key={n}
          className="po-skeleton-row shimmer"
          data-short={n % 3 === 2 ? "true" : undefined}
        />
      ))}
    </div>
  );
};
