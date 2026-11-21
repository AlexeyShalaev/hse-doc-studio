import { Send } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button, Spinner } from "@shared/ui";
import { PRIMARY_BUTTON_ID } from "./focus";
import type { SubmitController } from "./useSubmit";

/**
 * Главная кнопка подвала панели «Изменения» (pack-studio-ux.md, 5.6): одна кнопка подтверждения
 * отправки. Пока что-то мешает, она выключена, а причина написана рядом (`blockerText`): ошибки
 * проверки, заметки, согласие. После обрыва она зовёт «Повторить» и начинает с упавшего шага.
 */
export const SubmitPrimary = ({
  c,
  errors,
}: {
  c: SubmitController;
  errors: number;
}) => {
  const { t } = useTranslation("packSpace");
  if (!c.available) return null;
  const label = c.running
    ? t("submit.primary.running")
    : c.failure
      ? t("submit.primary.retry")
      : c.blocker === "errors"
        ? t("submit.primary.errors", { count: errors })
        : c.blocker === "notes"
          ? t("submit.primary.notes")
          : c.fork
            ? t("submit.primary.fork")
            : c.update
              ? t("submit.primary.update")
              : t("submit.primary.send");
  const why = c.running ? null : c.blocker;
  return (
    <Button
      id={PRIMARY_BUTTON_ID}
      disabled={c.running || why !== null}
      title={why ? t(`submit.blocker.${why}`) : undefined}
      aria-describedby={why ? "sp-sb-blocker" : undefined}
      onClick={c.run}
      data-testid="sp-sb-primary"
      data-blocker={why ?? undefined}
    >
      {c.running ? (
        <Spinner size="sm" />
      ) : (
        <Send size="0.875rem" aria-hidden="true" />
      )}
      {label}
    </Button>
  );
};

/** Почему отправка выключена, одной строкой под разделом: доступно и без наведения мыши. */
export const BlockerText = ({ c }: { c: SubmitController }) => {
  const { t } = useTranslation("packSpace");
  if (!c.available || c.running || c.blocker === null) return null;
  return (
    <p className="sp-sb-blocker" id="sp-sb-blocker" data-testid="sp-sb-blocker">
      {t(`submit.blocker.${c.blocker}`)}
    </p>
  );
};
