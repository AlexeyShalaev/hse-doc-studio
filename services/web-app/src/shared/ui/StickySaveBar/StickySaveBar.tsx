import { useRef } from "react";
import { CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Spinner } from "../Spinner";

// Одна панель сохранения на страницу вместо кнопки в каждой карточке. Видна,
// пока есть несохранённые правки; прилипает к низу области содержимого
// (PageContainer растягивается на всю высоту, панель стоит последней).

export type StickySaveBarProps = {
  /** Сколько правок не сохранено; 0 прячет панель. */
  dirtyCount: number;
  onSave: () => void;
  onDiscard: () => void;
  /** Идёт сохранение: кнопки неактивны, на «Сохранить» крутилка. */
  busy?: boolean | undefined;
  /** Сохранить нельзя (ошибки в полях). */
  saveDisabled?: boolean | undefined;
  /** Текст ошибки сохранения вместо счётчика. */
  error?: string | null | undefined;
  /**
   * В полях есть ошибки: текст встаёт рядом со счётчиком, а кнопка
   * «Показать» прокручивает к первому неверному полю и ставит в него фокус.
   */
  invalidHint?: string | null | undefined;
  saveLabel?: string | undefined;
  testId?: string | undefined;
};

export const StickySaveBar = ({
  dirtyCount,
  onSave,
  onDiscard,
  busy = false,
  saveDisabled = false,
  error = null,
  invalidHint = null,
  saveLabel,
  testId = "save-bar",
}: StickySaveBarProps) => {
  const { t } = useTranslation("uiPrimitives");
  const slot = useRef<HTMLDivElement>(null);
  if (dirtyCount <= 0 && !busy) return null;

  const reveal = () => {
    // Ищем в той же странице, что и панель: ошибки другой формы не нужны.
    const scope: ParentNode =
      slot.current?.closest(".adm-page, form") ?? document;
    const first = scope.querySelector<HTMLElement>('[aria-invalid="true"]');
    if (!first) return;
    first.scrollIntoView({ block: "center", behavior: "smooth" });
    first.focus({ preventScroll: true });
  };
  return (
    <div className="adm-savebar-slot" ref={slot}>
      <div
        className="adm-savebar"
        role="region"
        aria-label={t("adminKit.saveBar.label")}
        data-testid={testId}
      >
        <span
          className="adm-savebar-text"
          data-error={error ? "true" : undefined}
          role={error ? "alert" : "status"}
        >
          {error ? (
            <CircleAlert size={14} aria-hidden="true" />
          ) : (
            <span className="dot warn" aria-hidden="true" />
          )}
          {error ?? t("adminKit.saveBar.unsaved", { count: dirtyCount })}
          {!error && invalidHint && (
            <span className="adm-savebar-issue" data-testid={`${testId}-issue`}>
              {invalidHint}
              <button
                type="button"
                className="adm-savebar-reveal"
                onClick={reveal}
                data-testid={`${testId}-reveal`}
              >
                {t("adminKit.saveBar.reveal")}
              </button>
            </span>
          )}
        </span>
        <button
          type="button"
          className="btn ghost sm"
          disabled={busy}
          onClick={onDiscard}
          data-testid={`${testId}-discard`}
        >
          {t("adminKit.saveBar.discard")}
        </button>
        <button
          type="button"
          className="btn primary sm"
          disabled={busy || saveDisabled}
          onClick={onSave}
          data-testid={`${testId}-save`}
        >
          {busy && <Spinner size="sm" />}
          {saveLabel ?? t("adminKit.saveBar.save")}
        </button>
      </div>
    </div>
  );
};

StickySaveBar.displayName = "StickySaveBar";
