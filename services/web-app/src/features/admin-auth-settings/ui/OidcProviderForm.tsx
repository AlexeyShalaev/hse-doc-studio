import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  CopyField,
  Input,
  Modal,
  Spinner,
  StatusDot,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import type { AdminOidcProvider } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import {
  draftOfProvider,
  emptyOidcDraft,
  redirectUri,
  validateOidc,
  type OidcDraft,
} from "../lib/validate";
import { HINT } from "../lib/styles";

/** Выключатель с подписью и пояснением внутри формы. */
const SwitchLine = ({
  id,
  label,
  hint,
  checked,
  onChange,
  testId,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  testId: string;
}) => (
  <div
    className="flex items-center justify-between"
    style={{ gap: 16, padding: "8px 0" }}
  >
    <span className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
      <label htmlFor={id} style={{ fontSize: 13, fontWeight: 500 }}>
        {label}
      </label>
      <span id={`${id}-hint`} style={HINT}>
        {hint}
      </span>
    </span>
    <Switch
      id={id}
      checked={checked}
      onChange={onChange}
      describedBy={`${id}-hint`}
      testId={testId}
    />
  </div>
);

export type OidcProviderFormProps = {
  /** null: новый провайдер. */
  provider: AdminOidcProvider | null;
  /** Адрес установки для redirect URI; пусто, если не определён. */
  baseUrl: string;
  pending?: boolean;
  failure?: Failure | null;
  onClose: () => void;
  onSubmit: (draft: OidcDraft) => void;
};

/** Форма провайдера единого входа. Секрет клиента принимается на запись и никогда не показывается. */
export const OidcProviderForm = ({
  provider,
  baseUrl,
  pending = false,
  failure = null,
  onClose,
  onSubmit,
}: OidcProviderFormProps) => {
  const { t } = useTranslation("adminSettings");
  const uid = useId();
  const creating = provider === null;
  const [draft, setDraft] = useState<OidcDraft>(
    provider ? draftOfProvider(provider) : emptyOidcDraft(),
  );
  const [touched, setTouched] = useState(false);
  const set = (patch: Partial<OidcDraft>) => {
    setDraft((d) => ({ ...d, ...patch }));
  };

  const issues = validateOidc(draft, { creating });
  const issue = (key: keyof typeof issues): { error?: string } => {
    const code = touched ? issues[key] : undefined;
    return code ? { error: t(`oidc.issue.${code}`) } : {};
  };
  const valid = Object.keys(issues).length === 0;

  const submit = () => {
    setTouched(true);
    if (!valid || pending) return;
    onSubmit({
      ...draft,
      label: draft.label.trim(),
      issuer: draft.issuer.trim().replace(/\/+$/, ""),
      client_id: draft.client_id.trim(),
      scopes: draft.scopes.trim().split(/\s+/).join(" "),
    });
  };

  return (
    <Modal
      isOpen
      onClose={onClose}
      width={560}
      title={creating ? t("oidc.form.createTitle") : t("oidc.form.editTitle")}
      description={t("oidc.form.lead")}
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            type="button"
            aria-disabled={pending}
            onClick={submit}
            style={{ gap: 8 }}
            data-testid="oidc-form-save"
          >
            {pending && <Spinner size="sm" />}
            {pending ? t("saving") : t("save")}
          </Button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="oidc-form"
      >
        <Input
          id={`${uid}-label`}
          label={t("oidc.form.label")}
          hint={t("oidc.form.labelHint")}
          value={draft.label}
          onChange={(e) => {
            set({ label: e.target.value });
          }}
          {...issue("label")}
        />
        <Input
          id={`${uid}-issuer`}
          label={t("oidc.form.issuer")}
          hint={t("oidc.form.issuerHint")}
          isMono
          inputMode="url"
          placeholder="https://id.example.org"
          value={draft.issuer}
          onChange={(e) => {
            set({ issuer: e.target.value });
          }}
          {...issue("issuer")}
        />
        <Input
          id={`${uid}-client`}
          label={t("oidc.form.clientId")}
          isMono
          autoComplete="off"
          value={draft.client_id}
          onChange={(e) => {
            set({ client_id: e.target.value });
          }}
          {...issue("client_id")}
        />
        <div className="flex flex-col" style={{ gap: 6 }}>
          <Input
            id={`${uid}-secret`}
            label={t("oidc.form.secret")}
            type="password"
            name="oidc-client-secret"
            autoComplete="new-password"
            value={draft.client_secret}
            placeholder={
              provider?.client_secret_set ? t("oidc.form.secretKeep") : ""
            }
            onChange={(e) => {
              set({ client_secret: e.target.value });
            }}
            {...(touched && issues.client_secret
              ? { error: t(`oidc.issue.${issues.client_secret}`) }
              : { hint: t("oidc.form.secretHint") })}
          />
          {provider?.client_secret_set && (
            <span className="adm-field-note" data-testid="oidc-secret-set">
              <StatusDot status="success" label={t("oidc.form.secretSet")} />
            </span>
          )}
        </div>
        <Input
          id={`${uid}-scopes`}
          label={t("oidc.form.scopes")}
          isMono
          value={draft.scopes}
          onChange={(e) => {
            set({ scopes: e.target.value });
          }}
          {...(touched && issues.scopes
            ? { error: t(`oidc.issue.${issues.scopes}`) }
            : { hint: t("oidc.form.scopesHint") })}
        />

        <div className="flex flex-col" style={{ gap: 2 }}>
          <SwitchLine
            id={`${uid}-enabled`}
            label={t("oidc.form.enabled")}
            hint={t("oidc.form.enabledHint")}
            checked={draft.enabled}
            onChange={(enabled) => {
              set({ enabled });
            }}
            testId="oidc-form-enabled"
          />
          <SwitchLine
            id={`${uid}-provision`}
            label={t("oidc.form.provision")}
            hint={t("oidc.form.provisionHint")}
            checked={draft.auto_provision}
            onChange={(auto_provision) => {
              set({ auto_provision });
            }}
            testId="oidc-form-provision"
          />
        </div>

        <div
          className="flex flex-col"
          style={{ gap: 6 }}
          data-testid="oidc-redirect"
        >
          <span style={{ fontSize: 12.5, fontWeight: 600 }}>
            {t("oidc.form.redirect")}
          </span>
          {baseUrl === "" ? (
            <Notice tone="warn" text={t("oidc.form.noBaseUrl")} />
          ) : (
            <>
              <CopyField
                value={redirectUri(baseUrl, provider?.id ?? "{id}")}
                label={t("oidc.form.redirect")}
              />
              <p style={HINT}>
                {creating
                  ? t("oidc.form.redirectNew")
                  : t("oidc.form.redirectHint")}
              </p>
            </>
          )}
        </div>

        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}
      </form>
    </Modal>
  );
};
