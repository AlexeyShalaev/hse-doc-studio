import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input, Modal } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";

export type PassphraseDialogProps = {
  open: boolean;
  busy: boolean;
  keyLabel: string;
  /** Подпись кнопки: «Подписать» или «Согласовать и подписать». */
  submitLabel: string;
  /** Текст отказа прошлой попытки (пароль не подошёл). */
  error: string | null;
  onClose: () => void;
  onSubmit: (passphrase: string) => void;
};

/** Пароль ключа Студии спрашивают при подписи: Студия его не хранит. */
export const PassphraseDialog = ({
  open,
  busy,
  keyLabel,
  submitLabel,
  error,
  onClose,
  onSubmit,
}: PassphraseDialogProps) => {
  const { t } = useTranslation("signing");
  const [passphrase, setPassphrase] = useState("");
  // Отказ более раннего действия страницы к этому окну не относится.
  const [tried, setTried] = useState(false);
  return (
    <Modal
      isOpen={open}
      onClose={busy ? () => undefined : onClose}
      title={t("passphrase.title")}
      description={t("passphrase.lead", { label: keyLabel })}
      width={420}
      footer={
        <>
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={onClose}
          >
            {t("cancel")}
          </Button>
          <Button
            type="submit"
            form="signing-passphrase-form"
            disabled={busy || passphrase === ""}
            data-testid="signing-passphrase-submit"
          >
            {busy ? t("actions.working") : submitLabel}
          </Button>
        </>
      }
    >
      <form
        id="signing-passphrase-form"
        className="flex flex-col"
        style={{ gap: "0.5rem" }}
        onSubmit={(event) => {
          event.preventDefault();
          if (passphrase === "" || busy) return;
          setTried(true);
          onSubmit(passphrase);
        }}
      >
        <Input
          id="signing-passphrase"
          label={t("passphrase.label")}
          type="password"
          value={passphrase}
          autoFocus
          autoComplete="off"
          data-testid="signing-passphrase"
          onChange={(event) => {
            setPassphrase(event.target.value);
          }}
        />
        {error && tried && !busy && (
          <div data-testid="signing-passphrase-error">
            <Notice tone="err" role="alert" text={error} />
          </div>
        )}
      </form>
    </Modal>
  );
};
