import { useState, type ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Modal } from "@shared/ui";
import { useSheetHistory } from "../../lib/useSheetHistory";
import { Notice } from "../Notice";
import { ScenarioPicker } from "../scenarios/ScenarioPicker";

type PhoneBarProps = {
  /** Название шаблона и версия: одна строка с многоточием. */
  title: string;
  version: string;
  /** Замок выпущенной версии. */
  lock: ReactNode;
  /** Статус сохранения и пересчёта: показывается, только если есть что сказать. */
  status: ReactNode;
  studentMode: boolean;
  /** В «Параметрах» выбрано не умолчание: у кнопки точка. */
  optionsActive: boolean;
  /** Текст плашки «Версия выпущена»: на телефоне он внутри листа, а не над результатом. */
  notice: string | null;
  /** Всё остальное: пак, шаблон, версия, режим, «Результат из», «Файлы», статус. */
  controls: ReactNode;
};

/**
 * Верхняя панель телефона: две строки (название с «Параметры» и выбор сценария). Остальные
 * элементы в листе «Параметры», чтобы результат получил почти всю высоту экрана
 * (template-studio-outcome.md, 3.12).
 */
export const PhoneBar = ({
  title,
  version,
  lock,
  status,
  studentMode,
  optionsActive,
  notice,
  controls,
}: PhoneBarProps) => {
  const { t } = useTranslation("packOutcome");
  const [open, setOpen] = useState(false);
  useSheetHistory("options", open, () => {
    setOpen(false);
  });
  return (
    <div
      className="po-pbar"
      role="group"
      aria-label={t("bar.label")}
      data-testid="outcome-phone-bar"
    >
      <div className="po-pbar-row">
        <div className="po-pbar-title" data-testid="outcome-phone-title">
          <span className="po-pbar-name">{title}</span>
          <span className="po-pbar-version po-mono">{version}</span>
          {lock}
          {studentMode && (
            <Badge variant="accent" data-testid="outcome-phone-student">
              {t("bar.modeStudent")}
            </Badge>
          )}
        </div>
        <button
          type="button"
          className="btn po-pbar-options"
          aria-haspopup="dialog"
          aria-expanded={open}
          data-testid="outcome-options-open"
          onClick={() => {
            setOpen(true);
          }}
        >
          <SlidersHorizontal size="0.875rem" aria-hidden="true" />
          {t("phone.options")}
          {optionsActive && (
            <span
              className="po-pbar-dot"
              aria-hidden="true"
              data-testid="outcome-options-dot"
            />
          )}
        </button>
      </div>
      {status}
      <div className="po-pbar-row">
        <ScenarioPicker withActions={false} />
      </div>
      <Modal
        isOpen={open}
        onClose={() => {
          setOpen(false);
        }}
        title={t("phone.options")}
        className="po-sheet"
      >
        <div className="po-options" data-testid="outcome-options">
          {notice !== null && (
            <Notice tone="info" title={notice} testId="outcome-released" />
          )}
          {controls}
        </div>
      </Modal>
    </div>
  );
};
