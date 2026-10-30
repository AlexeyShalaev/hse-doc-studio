import { useState, type ReactNode } from "react";
import { KeyRound, Pencil, Plus, Power, PowerOff, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  ActionMenu,
  Button,
  ConfirmByName,
  EmptyState,
  ErrorState,
  NoResults,
  Section,
  StatusDot,
  TableSkeleton,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import type { AdminOidcProvider } from "@entities/session";
import { failureKey, type Failure } from "../lib/failure";
import type { OidcDraft } from "../lib/validate";
import { OidcProviderForm } from "./OidcProviderForm";

export type OidcSectionProps = {
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
  /** Поиск, фильтр и порядок над списком. */
  toolbar?: ReactNode;
  /** Листание под списком. */
  pagination?: ReactNode;
  /**
   * Заданы поиск или фильтр: пустой список значит «ничего не найдено», а не
   * «провайдеров пока нет».
   */
  filtered?: boolean;
  /** Текущий поиск: попадает в пояснение «ничего не найдено». */
  query?: string;
  onResetFilters?: () => void;
  /** Идёт запрос с новыми условиями: прежние строки приглушены. */
  busy?: boolean;
};

const hostOf = (issuer: string): string => {
  try {
    const url = new URL(issuer);
    return `${url.host}${url.pathname === "/" ? "" : url.pathname}`;
  } catch {
    return issuer;
  }
};

/**
 * Провайдеры единого входа (OIDC): список с состоянием, действия в меню «⋯».
 * Включение и удаление применяются сразу, без общей панели сохранения.
 */
export const OidcSection = ({
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
  toolbar,
  pagination,
  filtered = false,
  query,
  onResetFilters,
  busy = false,
}: OidcSectionProps) => {
  const { t } = useTranslation("adminSettings");
  const [form, setForm] = useState<
    { mode: "create" } | { mode: "edit"; provider: AdminOidcProvider } | null
  >(null);
  const [removing, setRemoving] = useState<AdminOidcProvider | null>(null);

  const open = (next: NonNullable<typeof form>) => {
    onReset?.();
    setForm(next);
  };
  const add = () => {
    open({ mode: "create" });
  };

  return (
    <Section
      id="admin-oidc"
      testId="admin-oidc"
      title={t("oidc.title")}
      description={t("oidc.sub")}
      flush
      actions={
        status !== "loading" &&
        (providers.length > 0 || filtered) && (
          <Button
            size="sm"
            variant="secondary"
            type="button"
            onClick={add}
            data-testid="oidc-add"
          >
            <Plus size={14} aria-hidden="true" />
            {t("oidc.add")}
          </Button>
        )
      }
    >
      {toolbar && <div className="adm-section-toolbar">{toolbar}</div>}
      {status === "loading" && (
        <TableSkeleton
          rows={2}
          columns={2}
          withAvatar
          framed={false}
          testId="oidc-loading"
        />
      )}
      {status === "error" && (
        <div style={{ padding: "0 20px 16px" }}>
          <ErrorState
            compact
            title={t("oidc.loadFailed")}
            onRetry={onRetry}
            testId="oidc-failed"
          />
        </div>
      )}
      {status === "ready" && providers.length === 0 && filtered && (
        <NoResults
          compact
          query={query}
          onReset={onResetFilters}
          testId="oidc-none"
        />
      )}
      {status === "ready" && providers.length === 0 && !filtered && (
        <EmptyState
          icon={<KeyRound size={18} />}
          title={t("oidc.empty.title")}
          description={t("oidc.empty.body")}
          testId="oidc-empty"
          action={
            <Button
              size="sm"
              variant="secondary"
              type="button"
              onClick={add}
              data-testid="oidc-add"
            >
              <Plus size={14} aria-hidden="true" />
              {t("oidc.add")}
            </Button>
          }
        />
      )}
      {status === "ready" && providers.length > 0 && (
        <ul
          className="adm-list"
          aria-label={t("oidc.title")}
          aria-busy={busy}
          style={{ opacity: busy ? 0.6 : 1, transition: "opacity 0.12s" }}
        >
          {providers.map((provider) => (
            <li key={provider.id} data-testid={`oidc-provider-${provider.id}`}>
              <div className="adm-item">
                <span
                  className="adm-row-icon"
                  data-tone={provider.enabled ? "accent" : "neutral"}
                  aria-hidden="true"
                >
                  <KeyRound size={15} />
                </span>
                <div className="adm-item-text">
                  <span className="adm-item-title">{provider.label}</span>
                  <span className="adm-item-desc">
                    {hostOf(provider.issuer)}
                    {provider.auto_provision && (
                      <span className="adm-dotsep">
                        {t("oidc.autoProvision")}
                      </span>
                    )}
                    {!provider.client_secret_set && (
                      <span
                        className="adm-dotsep"
                        style={{ color: "var(--c-warn)" }}
                      >
                        {t("oidc.secretMissing")}
                      </span>
                    )}
                  </span>
                </div>
                <div className="adm-item-meta">
                  <span data-testid={`oidc-state-${provider.id}`}>
                    <StatusDot
                      status={provider.enabled ? "success" : "neutral"}
                      label={provider.enabled ? t("oidc.on") : t("oidc.off")}
                    />
                  </span>
                  <ActionMenu
                    label={t("oidc.actionsNamed", { name: provider.label })}
                    testId={`oidc-menu-${provider.id}`}
                    items={[
                      {
                        id: "edit",
                        label: t("oidc.edit"),
                        icon: <Pencil size={14} />,
                        onSelect: () => {
                          open({ mode: "edit", provider });
                        },
                        testId: `oidc-edit-${provider.id}`,
                      },
                      {
                        id: "toggle",
                        label: provider.enabled
                          ? t("oidc.disable")
                          : t("oidc.enable"),
                        icon: provider.enabled ? (
                          <PowerOff size={14} />
                        ) : (
                          <Power size={14} />
                        ),
                        onSelect: () => {
                          onToggle(provider);
                        },
                        testId: `oidc-toggle-${provider.id}`,
                      },
                      {
                        id: "delete",
                        label: t("oidc.delete"),
                        icon: <Trash2 size={14} />,
                        danger: true,
                        onSelect: () => {
                          onReset?.();
                          setRemoving(provider);
                        },
                        testId: `oidc-delete-${provider.id}`,
                      },
                    ]}
                  />
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {status === "ready" && pagination && providers.length > 0 && (
        <div className="adm-list-pager">{pagination}</div>
      )}
      {failure && !removing && !form && (
        <div style={{ padding: "0 20px 16px" }}>
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        </div>
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
    </Section>
  );
};
