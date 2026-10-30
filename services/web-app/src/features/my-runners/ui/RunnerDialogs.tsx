import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  CopyField,
  Input,
  Modal,
  SecretOnce,
  Spinner,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { MyRunner, MyRunnerRotated } from "@entities/runner";

const NAME_MAX = 128;

/** Подтверждение действия с последствиями (смена токена, отзыв токена). */
export const ConfirmDialog = ({
  isOpen,
  title,
  body,
  confirmLabel,
  danger = false,
  pending = false,
  error = null,
  onConfirm,
  onClose,
  testId,
}: {
  isOpen: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  pending?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onClose: () => void;
  testId?: string;
}) => {
  const { t } = useTranslation("runners");
  return (
    <Modal
      isOpen={isOpen}
      onClose={() => {
        if (!pending) onClose();
      }}
      title={title}
      footer={
        <>
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={pending}
          >
            {t("cancel")}
          </Button>
          <button
            type="button"
            className={danger ? "btn danger" : "btn primary"}
            disabled={pending}
            onClick={onConfirm}
            data-testid={testId ? `${testId}-confirm` : undefined}
          >
            {pending && <Spinner size="sm" />}
            {confirmLabel}
          </button>
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: 10, fontSize: 13, color: "var(--fg-1)" }}
        data-testid={testId}
      >
        <div>{body}</div>
        {error && <Notice tone="err" role="alert" text={error} />}
      </div>
    </Modal>
  );
};

/** Новое имя раннера: его видят соавторы, если сборки идут на этом раннере. */
export const RenameDialog = ({
  runner,
  pending = false,
  error = null,
  onSave,
  onClose,
}: {
  runner: MyRunner | null;
  pending?: boolean;
  error?: string | null;
  onSave: (name: string) => void;
  onClose: () => void;
}) => {
  const { t } = useTranslation("runners");
  return (
    <Modal
      isOpen={runner !== null}
      onClose={() => {
        if (!pending) onClose();
      }}
      title={t("rename.title")}
    >
      {runner && (
        <RenameForm
          key={runner.id}
          initial={runner.name}
          pending={pending}
          error={error}
          onSave={onSave}
          onClose={onClose}
        />
      )}
    </Modal>
  );
};

const RenameForm = ({
  initial,
  pending,
  error,
  onSave,
  onClose,
}: {
  initial: string;
  pending: boolean;
  error: string | null;
  onSave: (name: string) => void;
  onClose: () => void;
}) => {
  const { t } = useTranslation("runners");
  const [name, setName] = useState(initial);
  const [tried, setTried] = useState(false);
  const trimmed = name.replace(/\s+/g, " ").trim();
  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      data-testid="my-runner-rename-form"
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (trimmed !== "") onSave(trimmed);
      }}
    >
      <Input
        label={t("rename.label")}
        hint={t("rename.hint")}
        value={name}
        maxLength={NAME_MAX}
        autoFocus
        {...(tried && trimmed === "" ? { error: t("rename.required") } : {})}
        onChange={(event) => {
          setName(event.target.value);
        }}
        data-testid="my-runner-rename-input"
      />
      {error && <Notice tone="err" role="alert" text={error} />}
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onClose}
          disabled={pending}
        >
          {t("cancel")}
        </Button>
        <Button
          type="submit"
          disabled={pending}
          data-testid="my-runner-rename-save"
        >
          {pending && <Spinner size="sm" />}
          {t("rename.save")}
        </Button>
      </div>
    </form>
  );
};

/** Новый токен раннера после смены: старый уже не работает. Показывается один раз. */
export const RotatedDialog = ({
  rotated,
  onClose,
}: {
  rotated: MyRunnerRotated | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("runners");
  return (
    <Modal
      isOpen={rotated !== null}
      onClose={onClose}
      title={t("rotate.title", { name: rotated?.runner.name ?? "" })}
      width={560}
    >
      {rotated && (
        <div
          data-testid="my-runner-rotated"
          className="flex flex-col"
          style={{ gap: 12 }}
        >
          <Notice tone="warn" text={t("rotate.lead")} />
          <SecretOnce
            label={t("rotate.label")}
            value={rotated.runner_token}
            onClose={onClose}
            extra={
              <div
                className="flex flex-col"
                style={{
                  gap: 6,
                  paddingTop: 12,
                  borderTop: "1px solid var(--border)",
                }}
              >
                <span className="form-label">{t("rotate.commandTitle")}</span>
                <CopyField
                  value={rotated.command}
                  label={t("rotate.commandLabel")}
                  multiline
                  wrap="spaces"
                />
              </div>
            }
          />
        </div>
      )}
    </Modal>
  );
};

/** Студия хранит токен сама: вместо смены токена её подключают заново. */
export const ReconnectDialog = ({
  runner,
  onClose,
}: {
  runner: MyRunner | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("runners");
  return (
    <Modal
      isOpen={runner !== null}
      onClose={onClose}
      title={t("reconnect.title", { name: runner?.name ?? "" })}
      description={t("reconnect.body")}
      footer={
        <Button
          type="button"
          onClick={onClose}
          data-testid="my-runner-reconnect-done"
        >
          {t("reconnect.done")}
        </Button>
      }
    />
  );
};
