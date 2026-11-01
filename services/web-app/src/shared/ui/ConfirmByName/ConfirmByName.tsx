import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Modal } from "../Modal";
import { Spinner } from "../Spinner";

// Подтверждение опасного действия вводом названия объекта. Кнопка активна
// только при точном совпадении (регистр и пробелы важны).

export type ConfirmByNameProps = {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  /** Название, которое нужно ввести. */
  name: string;
  title: string;
  description?: React.ReactNode;
  confirmLabel: string;
  pending?: boolean;
  /** Ошибка последней попытки. */
  error?: string | null;
};

export const ConfirmByName = (props: ConfirmByNameProps) => (
  // Новый ключ при каждом открытии сбрасывает введённый текст.
  <ConfirmByNameInner
    key={`${String(props.isOpen)}:${props.name}`}
    {...props}
  />
);

const ConfirmByNameInner = ({
  isOpen,
  onClose,
  onConfirm,
  name,
  title,
  description,
  confirmLabel,
  pending = false,
  error = null,
}: ConfirmByNameProps) => {
  const { t } = useTranslation("uiPrimitives");
  const [typed, setTyped] = useState("");
  const inputId = useId();

  const matches = typed === name;
  const canConfirm = matches && !pending;

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!pending) onClose();
      }}
      title={title}
      description={description}
      footer={
        <>
          <button
            type="button"
            className="btn"
            onClick={onClose}
            disabled={pending}
          >
            {t("confirmByName.cancel")}
          </button>
          <button
            type="button"
            className="btn danger"
            disabled={!canConfirm}
            onClick={onConfirm}
          >
            {pending && <Spinner size="sm" />}
            {confirmLabel}
          </button>
        </>
      }
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (canConfirm) onConfirm();
        }}
      >
        <label
          htmlFor={inputId}
          style={{ display: "block", fontSize: 12.5, color: "var(--fg-2)" }}
        >
          {t("confirmByName.prompt")}{" "}
          <strong className="mono" style={{ color: "var(--fg-0)" }}>
            {name}
          </strong>
        </label>
        <input
          id={inputId}
          className="input mono"
          value={typed}
          onChange={(event) => {
            setTyped(event.target.value);
          }}
          autoComplete="off"
          spellCheck={false}
          disabled={pending}
          aria-invalid={typed.length > 0 && !matches}
          style={{ width: "100%", marginTop: 8 }}
        />
        {error && (
          <p
            role="alert"
            style={{
              margin: "10px 0 0",
              fontSize: 12.5,
              color: "var(--c-err)",
            }}
          >
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
};

ConfirmByName.displayName = "ConfirmByName";
