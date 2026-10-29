import { useState } from "react";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge, Button, ConfirmByName, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminOidcProvider } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import type { OidcDraft } from "../lib/validate";
import { OidcProviderForm } from "./OidcProviderForm";
import { SettingsCard } from "./parts";

export type OidcCardProps = {
  status: "loading" | "ready" | "error";
  providers: readonly AdminOidcProvider[];
  baseUrl: string;
  /** Идёт сохранение формы. */
  saving?: boolean;
  /** Отказ последнего сохранения формы. */
  formFailure?: Failure | null;
  /** Отказ включения или удаления вне формы. */
  failure?: Failure | null;
  deleting?: boolean;
  onRetry?: () => void;
  /** Результат true закрывает форму; при отказе она остаётся открытой. */
  onCreate: (draft: OidcDraft) => Promise<boolean> | undefined;
  onUpdate: (
    provider: AdminOidcProvider,
    draft: OidcDraft,
  ) => Promise<boolean> | undefined;
  onToggle: (provider: AdminOidcProvider) => void;
  onDelete: (provider: AdminOidcProvider) => Promise<boolean> | undefined;
  /** Сбросить отказы при открытии формы. */
  onReset?: () => void;
};

/** Провайдеры единого входа (OIDC): список, добавление, правка, включение и удаление. */
export const OidcCard = ({
  status,
  providers,
  baseUrl,
  saving = false,
  formFailure = null,
  failure = null,
  deleting = false,
  onRetry,
  onCreate,
  onUpdate,
  onToggle,
  onDelete,
  onReset,
}: OidcCardProps) => {
  const { t } = useTranslation("adminSettings");
  const [form, setForm] = useState<
    { mode: "create" } | { mode: "edit"; provider: AdminOidcProvider } | null
  >(null);
  const [removing, setRemoving] = useState<AdminOidcProvider | null>(null);

  const open = (next: NonNullable<typeof form>) => {
    onReset?.();
    setForm(next);
  };

  return (
    <SettingsCard
      id="admin-oidc"
      testId="admin-oidc"
      title={t("oidc.title")}
      sub={t("oidc.sub")}
      aside={
        status === "ready" && (
          <Button
            size="sm"
            variant="secondary"
            type="button"
            style={{ gap: 6 }}
            onClick={() => {
              open({ mode: "create" });
            }}
            data-testid="oidc-add"
          >
            <Plus size={14} aria-hidden="true" />
            {t("oidc.add")}
          </Button>
        )
      }
    >
      {status === "loading" && (
        <div
          className="flex items-center"
          style={{ gap: 8, fontSize: 12 }}
          data-testid="oidc-loading"
        >
          <Spinner size="sm" />
          <span className="dim">{t("loading")}</span>
        </div>
      )}
      {status === "error" && (
        <Notice
          tone="err"
          role="alert"
          text={t("oidc.loadFailed")}
          action={
            <button type="button" className="btn xs" onClick={onRetry}>
              {t("retry")}
            </button>
          }
        />
      )}
      {status === "ready" && providers.length === 0 && (
        <div
          className="flex flex-col items-start"
          style={{
            gap: 8,
            padding: 16,
            border: "1px dashed var(--border)",
            borderRadius: "var(--r-2)",
          }}
          data-testid="oidc-empty"
        >
          <KeyRound
            size={18}
            aria-hidden="true"
            style={{ color: "var(--fg-3)" }}
          />
          <strong style={{ fontSize: 13 }}>{t("oidc.empty.title")}</strong>
          <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
            {t("oidc.empty.body")}
          </span>
        </div>
      )}
      {status === "ready" && providers.length > 0 && (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
          aria-label={t("oidc.title")}
        >
          {providers.map((provider) => (
            <li
              key={provider.id}
              data-testid={`oidc-provider-${provider.id}`}
              className="flex items-center"
              style={{
                gap: 10,
                padding: "10px 12px",
                border: "1px solid var(--border)",
                borderRadius: "var(--r-2)",
                background: "var(--bg-0)",
                flexWrap: "wrap",
              }}
            >
              <div
                className="flex flex-col"
                style={{ gap: 2, minWidth: 0, flex: "1 1 220px" }}
              >
                <span
                  className="flex items-center"
                  style={{ gap: 8, fontSize: 13, fontWeight: 600 }}
                >
                  {provider.label}
                  <Badge variant={provider.enabled ? "success" : "subtle"}>
                    {provider.enabled ? t("oidc.on") : t("oidc.off")}
                  </Badge>
                  {provider.auto_provision && (
                    <Badge variant="info">{t("oidc.autoProvision")}</Badge>
                  )}
                </span>
                <span
                  className="mono"
                  style={{
                    fontSize: 11.5,
                    color: "var(--fg-2)",
                    overflowWrap: "anywhere",
                  }}
                >
                  {provider.issuer}
                </span>
                <span style={{ fontSize: 11.5, color: "var(--fg-3)" }}>
                  {provider.client_secret_set
                    ? t("oidc.secretSet")
                    : t("oidc.secretMissing")}
                </span>
              </div>
              <div className="flex items-center" style={{ gap: 6 }}>
                <Button
                  size="xs"
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    onToggle(provider);
                  }}
                  data-testid={`oidc-toggle-${provider.id}`}
                >
                  {provider.enabled ? t("oidc.disable") : t("oidc.enable")}
                </Button>
                <Button
                  size="xs"
                  variant="ghost"
                  type="button"
                  style={{ gap: 4 }}
                  onClick={() => {
                    open({ mode: "edit", provider });
                  }}
                  data-testid={`oidc-edit-${provider.id}`}
                >
                  <Pencil size={12} aria-hidden="true" />
                  {t("oidc.edit")}
                </Button>
                <Button
                  size="xs"
                  variant="ghost"
                  type="button"
                  style={{ gap: 4, color: "var(--c-err)" }}
                  onClick={() => {
                    onReset?.();
                    setRemoving(provider);
                  }}
                  data-testid={`oidc-delete-${provider.id}`}
                >
                  <Trash2 size={12} aria-hidden="true" />
                  {t("oidc.delete")}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {failure && !removing && (
        <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
      )}

      {form && (
        <OidcProviderForm
          provider={form.mode === "edit" ? form.provider : null}
          baseUrl={baseUrl}
          pending={saving}
          failure={formFailure}
          onClose={() => {
            setForm(null);
          }}
          onSubmit={(draft) => {
            const result =
              form.mode === "edit"
                ? onUpdate(form.provider, draft)
                : onCreate(draft);
            void Promise.resolve(result).then((ok) => {
              if (ok === true) setForm(null);
            });
          }}
        />
      )}
      <ConfirmByName
        isOpen={removing !== null}
        onClose={() => {
          setRemoving(null);
        }}
        onConfirm={() => {
          if (!removing) return;
          void Promise.resolve(onDelete(removing)).then((ok) => {
            if (ok === true) setRemoving(null);
          });
        }}
        name={removing?.label ?? ""}
        title={t("oidc.confirm.title")}
        description={t("oidc.confirm.body", { name: removing?.label ?? "" })}
        confirmLabel={t("oidc.confirm.action")}
        pending={deleting}
        error={failure ? t(failureKey(failure.code)) : null}
      />
    </SettingsCard>
  );
};
