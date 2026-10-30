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
  saveLabel,
  testId = "save-bar",
}: StickySaveBarProps) => {
  const { t } = useTranslation("uiPrimitives");
  if (dirtyCount <= 0 && !busy) return null;
  return (
    <div className="adm-savebar-slot">
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
