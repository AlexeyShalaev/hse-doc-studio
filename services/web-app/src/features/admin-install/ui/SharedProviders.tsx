import { useState } from "react";
import { Bot, Lock, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  ActionMenu,
  Button,
  EmptyState,
  Section,
  Spinner,
  StatusDot,
} from "@shared/ui";
import type { AIProvider } from "@entities/ai-provider";

export type ProviderCheck =
  | { state: "running" }
  | { state: "ok"; models: number }
  | { state: "failed"; error: string };

export type SharedProvidersProps = {
  providers: readonly AIProvider[];
  /** Идёт удаление. */
  deleting?: boolean;
  onAdd: () => void;
  onEdit: (provider: AIProvider) => void;
  onDelete: (provider: AIProvider) => void;
  /** Проверка подключения: число моделей или отказ с текстом ошибки. */
  onCheck?: (provider: AIProvider) => Promise<{ models: string[] }>;
};

const hostOf = (url: string): string => {
  try {
    const parsed = new URL(url);
    return `${parsed.host}${parsed.pathname === "/" ? "" : parsed.pathname}`;
  } catch {
    return url;
  }
};

/**
 * Общие ИИ-провайдеры установки. Ключ задаёт админ и никому не показывается:
 * в строке только признак «ключ задан».
 */
export const SharedProviders = ({
  providers,
  deleting = false,
  onAdd,
  onEdit,
  onDelete,
  onCheck,
}: SharedProvidersProps) => {
  const { t } = useTranslation("adminInstall");
  const [checks, setChecks] = useState<Record<string, ProviderCheck>>({});

  const check = (provider: AIProvider) => {
    if (!onCheck) return;
    const put = (value: ProviderCheck) => {
      setChecks((prev) => ({ ...prev, [provider.id]: value }));
    };
    put({ state: "running" });
    onCheck(provider).then(
      (result) => {
        put({ state: "ok", models: result.models.length });
      },
      (error: unknown) => {
        put({
          state: "failed",
          error: error instanceof Error ? error.message : String(error),
        });
      },
    );
  };

  return (
    <Section
      id="admin-ai-providers"
      testId="admin-ai-providers"
      title={t("ai.title")}
      description={t("ai.sub")}
      flush
      footer={
        <span className="adm-field-note">
          <Lock size={12} aria-hidden="true" />
          {t("ai.keyNote")}
        </span>
      }
    >
      {providers.length === 0 ? (
        <EmptyState
          icon={<Bot size={18} />}
          title={t("ai.empty.title")}
          description={t("ai.empty.body")}
          testId="shared-provider-empty"
          action={
            <Button
              size="sm"
              type="button"
              onClick={onAdd}
              data-testid="shared-provider-add"
            >
              <Plus size={14} aria-hidden="true" />
              {t("ai.addFirst")}
            </Button>
          }
        />
      ) : (
        <ul className="adm-list" aria-label={t("ai.listLabel")}>
          {providers.map((provider) => {
            const status = checks[provider.id];
            return (
              <li
                key={provider.id}
                data-testid={`shared-provider-${provider.id}`}
              >
                <div className="adm-item">
                  <span
                    className="adm-row-icon"
                    data-tone={provider.has_api_key ? "accent" : "warning"}
                    aria-hidden="true"
                  >
                    <Bot size={15} />
                  </span>
                  <div className="adm-item-text">
                    <span className="adm-item-title">{provider.name}</span>
                    <span className="adm-item-desc">
                      <span style={{ whiteSpace: "nowrap" }}>
                        {t(`ai.type.${provider.type}`)}
                      </span>
                      <span className="adm-dotsep">
                        {provider.models.length > 0
                          ? t("ai.modelCount", {
                              count: provider.models.length,
                            })
                          : t("ai.modelsNotLoaded")}
                      </span>
                    </span>
                    {provider.base_url && (
                      <span className="adm-item-desc">
                        {hostOf(provider.base_url)}
                        {!provider.ssl_verify && (
                          <span
                            className="adm-dotsep"
                            style={{ color: "var(--c-warn)" }}
                          >
                            {t("ai.noTls")}
                          </span>
                        )}
                      </span>
                    )}
                    {status && (
                      <span
                        className="adm-item-desc flex items-center"
                        style={{ gap: 6, flexWrap: "wrap" }}
                        role="status"
                        data-testid={`shared-provider-check-${provider.id}`}
                      >
                        {status.state === "running" && (
                          <>
                            <Spinner size="sm" />
                            {t("ai.checking")}
                          </>
                        )}
                        {status.state === "ok" && (
                          <StatusDot
                            status="success"
                            label={t("ai.checkOk", { count: status.models })}
                          />
                        )}
                        {status.state === "failed" && (
                          <>
                            <StatusDot
                              status="danger"
                              label={t("ai.checkFailed")}
                            />
                            <code className="mono" style={{ fontSize: 11 }}>
                              {status.error}
                            </code>
                          </>
                        )}
                      </span>
                    )}
                  </div>
                  <div className="adm-item-meta">
                    {provider.has_api_key ? (
                      <span data-testid="provider-key-set">
                        <StatusDot status="success" label={t("ai.keySet")} />
                      </span>
                    ) : (
                      <span data-testid="provider-key-missing">
                        <StatusDot
                          status="warning"
                          label={t("ai.keyMissing")}
                        />
                      </span>
                    )}
                    <ActionMenu
                      label={t("ai.actionsNamed", { name: provider.name })}
                      testId={`shared-provider-menu-${provider.id}`}
                      items={[
                        ...(onCheck
                          ? [
                              {
                                id: "check",
                                label: t("ai.check"),
                                icon: <RefreshCw size={14} />,
                                disabled: status?.state === "running",
                                onSelect: () => {
                                  check(provider);
                                },
                                testId: `shared-provider-check-run-${provider.id}`,
                              },
                            ]
                          : []),
                        {
                          id: "edit",
                          label: t("ai.edit"),
                          icon: <Pencil size={14} />,
                          onSelect: () => {
                            onEdit(provider);
                          },
                          testId: `shared-provider-edit-${provider.id}`,
                        },
                        {
                          id: "delete",
                          label: t("ai.delete"),
                          icon: <Trash2 size={14} />,
                          danger: true,
                          disabled: deleting,
                          onSelect: () => {
                            onDelete(provider);
                          },
                          testId: `shared-provider-delete-${provider.id}`,
                        },
                      ]}
                    />
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Section>
  );
};
