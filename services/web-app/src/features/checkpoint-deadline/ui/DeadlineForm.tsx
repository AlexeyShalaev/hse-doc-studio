import { useState } from "react";
import { useTranslation } from "react-i18next";
import { deadlineFromInput, deadlineToInput } from "@entities/submission";
import { useIsPhoneWidth } from "@shared/lib";
import { Spinner } from "@shared/ui";

export type DeadlineFormProps = {
  /** Нынешний срок: поля заполняются им; без срока пустая дата и 23:59. */
  initial: string | null;
  /** Подпись главной кнопки: «Указать срок» у нового, «Сохранить» у правки. */
  submitLabel: string;
  /** Вторая кнопка: «Не сейчас» у мягкого запроса, «Отмена» у правки. */
  dismissLabel: string;
  busy?: boolean;
  onSubmit: (deadline: string) => void;
  onDismiss: () => void;
  /** Префикс data-testid полей и кнопок. */
  testId?: string;
};

/**
 * Дата и время срока точки по Москве (16.2): время по умолчанию 23:59. Ввод переводится в момент
 * с поясом `+03:00`, так его хранит сервер.
 */
export const DeadlineForm = ({
  initial,
  submitLabel,
  dismissLabel,
  busy = false,
  onSubmit,
  onDismiss,
  testId = "deadline",
}: DeadlineFormProps) => {
  const { t } = useTranslation("checkpointDeadline");
  const isPhone = useIsPhoneWidth();
  const start = deadlineToInput(initial);
  const [date, setDate] = useState(start.date);
  const [time, setTime] = useState(start.time);
  const [invalid, setInvalid] = useState(false);

  const submit = () => {
    const deadline = deadlineFromInput(date, time);
    if (deadline === null) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    onSubmit(deadline);
  };

  const field = { gap: "0.25rem", fontSize: "0.71875rem" } as const;

  return (
    <form
      className="flex flex-col"
      style={{ gap: "0.5rem" }}
      aria-label={t("form.label")}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      data-testid={`${testId}-form`}
    >
      <div
        className="flex"
        style={{
          gap: "0.5rem",
          flexDirection: isPhone ? "column" : "row",
          alignItems: isPhone ? "stretch" : "flex-end",
          flexWrap: "wrap",
        }}
      >
        <label className="flex flex-col" style={field}>
          {t("form.date")}
          <input
            type="date"
            className="input"
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              setInvalid(false);
            }}
            data-testid={`${testId}-date`}
          />
        </label>
        <label className="flex flex-col" style={field}>
          {t("form.time")}
          <input
            type="time"
            className="input"
            value={time}
            onChange={(e) => {
              setTime(e.target.value);
              setInvalid(false);
            }}
            data-testid={`${testId}-time`}
          />
        </label>
        <div
          className="flex"
          style={{ gap: "0.375rem", flexWrap: "wrap", alignItems: "center" }}
        >
          <button
            type="submit"
            className="btn sm primary"
            disabled={busy}
            data-testid={`${testId}-submit`}
          >
            {busy && <Spinner size="sm" />}
            {submitLabel}
          </button>
          <button
            type="button"
            className="btn sm ghost"
            disabled={busy}
            onClick={onDismiss}
            data-testid={`${testId}-dismiss`}
          >
            {dismissLabel}
          </button>
        </div>
      </div>
      {invalid && (
        <span
          role="alert"
          style={{ fontSize: "0.71875rem", color: "var(--c-err)" }}
        >
          {t("form.invalid")}
        </span>
      )}
    </form>
  );
};
