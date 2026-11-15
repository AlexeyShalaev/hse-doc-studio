import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import {
  catalogErrorText,
  isRevisionMoved,
  isSourceBusy,
  planBlockers,
} from "../lib/errorText";

/** Проверка идёт: ревизия скачивается и разбирается в отдельном процессе. */
export const CatalogCheckPending = () => {
  const { t } = useTranslation("packCatalog");
  return (
    <div
      className="flex items-center"
      style={{ gap: "0.5rem", fontSize: "0.75rem" }}
      role="status"
      data-testid="catalog-check-pending"
    >
      <Spinner size="sm" />
      <span className="dim">{t("flow.running")}</span>
    </div>
  );
};

/**
 * Отказ проверки или применения словами: источник изменился после проверки и занят
 * предлагают проверить снова, препятствия плана перечислены.
 */
export const CatalogFlowError = ({
  error,
  onRecheck,
  rechecking = false,
}: {
  error: unknown;
  onRecheck?: (() => void) | undefined;
  rechecking?: boolean;
}) => {
  const { t } = useTranslation("packCatalog");
  const moved = isRevisionMoved(error);
  const busy = isSourceBusy(error);
  const blockers = planBlockers(error);
  const text = moved
    ? t("flow.moved")
    : busy
      ? t("flow.busy")
      : catalogErrorText(error);
  return (
    <Notice
      tone="err"
      role="alert"
      text={
        blockers && blockers.length > 0 ? (
          <>
            {text}
            <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1rem" }}>
              {blockers.map((blocker) => (
                <li key={blocker}>{t(`blocker.${blocker}`)}</li>
              ))}
            </ul>
          </>
        ) : (
          text
        )
      }
      action={
        (moved || busy) && onRecheck ? (
          <Button
            size="xs"
            variant="secondary"
            onClick={onRecheck}
            disabled={rechecking}
            data-testid="catalog-recheck"
          >
            <RefreshCw size="0.75rem" />
            {t("flow.again")}
          </Button>
        ) : undefined
      }
    />
  );
};
