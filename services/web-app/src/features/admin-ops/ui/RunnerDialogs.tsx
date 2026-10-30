import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  CopyField,
  Input,
  Modal,
  SecretOnce,
  Select,
  Spinner,
} from "@shared/ui";
import type {
  AdminRunnerRotated,
  AdminRunnerTokenCreated,
  CreateAdminRunnerTokenRequest,
} from "@entities/session";
import type { Failure } from "../lib/failure";
import { FailureNotice } from "./parts";

/** Подтверждение действия с последствиями. */
export const ConfirmDialog = ({
  isOpen,
  title,
  body,
  confirmLabel,
  danger = false,
  pending = false,
  failure = null,
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
  failure?: Failure | null;
  onConfirm: () => void;
  onClose: () => void;
  testId?: string;
}) => {
  const { t } = useTranslation("adminOps");
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
        {failure && <FailureNotice failure={failure} />}
      </div>
    </Modal>
  );
};

/** Секрет и готовая команда запуска раннера. Показываются один раз. */
export const SecretWithCommand = ({
  label,
  secret,
  command,
  onClose,
}: {
  label: string;
  secret: string;
  command: string;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminOps");
  return (
    <div
      className="flex flex-col"
      style={{ gap: 12 }}
      data-testid="secret-once"
    >
      <SecretOnce
        label={label}
        value={secret}
        hint={t("secret.hint")}
        onClose={onClose}
      />
      <div className="flex flex-col" style={{ gap: 6 }}>
        <strong style={{ fontSize: 12.5 }}>{t("secret.commandTitle")}</strong>
        <CopyField value={command} label={t("secret.commandLabel")} multiline />
        <p style={{ margin: 0, fontSize: 11.5, color: "var(--fg-2)" }}>
          {t("secret.commandHint")}
        </p>
      </div>
    </div>
  );
};

const TTL_HOURS = [1, 24, 168, 720] as const;

export type CreateTokenFormProps = {
  pending?: boolean;
  failure?: Failure | null;
  onCancel: () => void;
  onSubmit: (body: CreateAdminRunnerTokenRequest) => void;
};

export const CreateTokenForm = ({
  pending = false,
  failure = null,
  onCancel,
  onSubmit,
}: CreateTokenFormProps) => {
  const { t } = useTranslation("adminOps");
  const [label, setLabel] = useState("");
  const [ttl, setTtl] = useState("24");
  const [uses, setUses] = useState("1");
  const [tried, setTried] = useState(false);

  const count = Number(uses);
  const usesValid = Number.isInteger(count) && count >= 1 && count <= 100;

  return (
    <form
      className="flex flex-col"
      style={{ gap: 14 }}
      noValidate
      data-testid="token-create-form"
      onSubmit={(event) => {
        event.preventDefault();
        setTried(true);
        if (!usesValid) return;
        onSubmit({
          label: label.trim(),
          ttl_hours: Number(ttl),
          max_uses: count,
        });
      }}
    >
      <Input
        label={t("tokens.form.label")}
        value={label}
        maxLength={128}
        autoFocus
        autoComplete="off"
        hint={t("tokens.form.labelHint")}
        onChange={(event) => {
          setLabel(event.target.value);
        }}
        data-testid="token-label"
      />
      <div className="field">
        <label htmlFor="token-ttl">{t("tokens.form.ttl")}</label>
        <Select
          id="token-ttl"
          value={ttl}
          onValueChange={setTtl}
          options={TTL_HOURS.map((h) => ({
            value: String(h),
            label: t(`tokens.form.ttlOption.${String(h)}`),
          }))}
          placeholder={t("tokens.form.ttl")}
        />
      </div>
      <Input
        label={t("tokens.form.maxUses")}
        type="number"
        min={1}
        max={100}
        value={uses}
        hint={t("tokens.form.maxUsesHint")}
        {...(tried && !usesValid
          ? { error: t("tokens.form.maxUsesInvalid") }
          : {})}
        onChange={(event) => {
          setUses(event.target.value);
        }}
        data-testid="token-max-uses"
      />
      {failure && <FailureNotice failure={failure} />}
      <div
        className="flex items-center"
        style={{ gap: 8, justifyContent: "flex-end" }}
      >
        <Button
          type="button"
          variant="ghost"
          onClick={onCancel}
          disabled={pending}
        >
          {t("cancel")}
        </Button>
        <Button
          type="submit"
          disabled={pending}
          data-testid="token-create-submit"
        >
          {pending && <Spinner size="sm" />}
          {t("tokens.form.submit")}
        </Button>
      </div>
    </form>
  );
};

/** Создание токена регистрации: форма, затем секрет один раз. */
export const CreateTokenDialog = ({
  isOpen,
  pending,
  failure,
  created,
  onSubmit,
  onClose,
}: {
  isOpen: boolean;
  pending: boolean;
  failure: Failure | null;
  created: AdminRunnerTokenCreated | null;
  onSubmit: (body: CreateAdminRunnerTokenRequest) => void;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminOps");
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={created ? t("tokens.created.title") : t("tokens.form.title")}
      description={created ? undefined : t("tokens.form.lead")}
      width={560}
    >
      {isOpen &&
        (created ? (
          <SecretWithCommand
            label={t("tokens.created.label")}
            secret={created.secret}
            command={created.command}
            onClose={onClose}
          />
        ) : (
          <CreateTokenForm
            pending={pending}
            failure={failure}
            onCancel={onClose}
            onSubmit={onSubmit}
          />
        ))}
    </Modal>
  );
};

/** Новый токен раннера после ротации: старый уже не работает. */
export const RotatedDialog = ({
  rotated,
  onClose,
}: {
  rotated: AdminRunnerRotated | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminOps");
  return (
    <Modal
      isOpen={rotated !== null}
      onClose={onClose}
      title={t("runners.rotated.title", { name: rotated?.runner.name ?? "" })}
      description={t("runners.rotated.lead")}
      width={560}
    >
      {rotated && (
        <SecretWithCommand
          label={t("runners.rotated.label")}
          secret={rotated.runner_token}
          command={rotated.command}
          onClose={onClose}
        />
      )}
    </Modal>
  );
};
