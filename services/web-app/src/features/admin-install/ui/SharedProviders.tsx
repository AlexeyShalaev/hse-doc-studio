import type { ReactNode } from "react";
import { Bot, KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@shared/ui";
import type { AIProvider } from "@entities/ai-provider";
import { SettingsCard } from "./parts";

const TYPE_LABEL: Record<AIProvider["type"], string> = {
  claude: "Anthropic",
  openai: "OpenAI",
  openai_compat: "OpenAI-compatible",
  ollama: "Ollama",
};

export type SharedProvidersProps = {
  providers: readonly AIProvider[];
  /** Идёт удаление. */
  deleting?: boolean;
  onAdd: () => void;
  onEdit: (provider: AIProvider) => void;
  onDelete: (provider: AIProvider) => void;
  /** Диалоги, которые держит родитель (редактор, подтверждение). */
  children?: ReactNode;
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
  children,
}: SharedProvidersProps) => {
  const { t } = useTranslation("adminInstall");
  return (
    <SettingsCard
      id="admin-ai-providers"
      testId="admin-ai-providers"
      title={t("ai.title")}
      sub={t("ai.sub")}
      aside={
        <button
          type="button"
          className="btn xs"
          onClick={onAdd}
          data-testid="shared-provider-add"
        >
          <Plus size={11} aria-hidden="true" />
          {t("ai.add")}
        </button>
      }
    >
      {providers.length === 0 ? (
        <div
          className="flex flex-col"
          style={{
            gap: 6,
            padding: 20,
            border: "1px dashed var(--border)",
            borderRadius: "var(--r-2)",
          }}
          data-testid="shared-provider-empty"
        >
          <strong style={{ fontSize: 13 }}>{t("ai.empty.title")}</strong>
          <span style={{ fontSize: 12, color: "var(--fg-2)" }}>
            {t("ai.empty.body")}
          </span>
        </div>
      ) : (
        <ul
          style={{
            listStyle: "none",
            margin: 0,
            padding: 0,
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
          aria-label={t("ai.listLabel")}
        >
          {providers.map((provider) => (
            <li
              key={provider.id}
              className="flex items-center justify-between"
              style={{
                gap: 12,
                padding: "10px 12px",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "var(--bg-1)",
              }}
              data-testid={`shared-provider-${provider.id}`}
            >
              <div
                className="flex flex-col"
                style={{ gap: 4, minWidth: 0, flex: 1 }}
              >
                <div
                  className="flex items-center"
                  style={{ gap: 8, flexWrap: "wrap" }}
                >
                  <Bot size={13} style={{ color: "var(--fg-2)" }} />
                  <span style={{ fontSize: 12.5, fontWeight: 500 }}>
                    {provider.name}
                  </span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 10,
                      padding: "1px 6px",
                      borderRadius: 3,
                      background: "var(--bg-3)",
                      color: "var(--fg-2)",
                    }}
                  >
                    {TYPE_LABEL[provider.type]}
                  </span>
                  <Badge variant="info">{t("ai.shared")}</Badge>
                  {provider.has_api_key ? (
                    <Badge variant="subtle" data-testid="provider-key-set">
                      <KeyRound
                        size={10}
                        aria-hidden="true"
                        style={{ marginRight: 4 }}
                      />
                      {t("ai.keySet")}
                    </Badge>
                  ) : (
                    <Badge variant="warning" data-testid="provider-key-missing">
                      {t("ai.keyMissing")}
                    </Badge>
                  )}
                </div>
                <div className="dim" style={{ fontSize: 11 }}>
                  {provider.models.length > 0
                    ? t("ai.modelCount", { count: provider.models.length })
                    : t("ai.modelsNotLoaded")}
                  {provider.base_url ? ` · ${provider.base_url}` : ""}
                  {!provider.ssl_verify && (
                    <span style={{ color: "var(--c-warn)" }}>
                      {" · "}
                      {t("ai.noTls")}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center" style={{ gap: 6 }}>
                <button
                  type="button"
                  className="btn xs"
                  onClick={() => {
                    onEdit(provider);
                  }}
                  title={t("ai.edit")}
                  aria-label={t("ai.editNamed", { name: provider.name })}
                >
                  <Pencil size={11} />
                </button>
                <button
                  type="button"
                  className="btn xs"
                  disabled={deleting}
                  onClick={() => {
                    onDelete(provider);
                  }}
                  title={t("ai.delete")}
                  aria-label={t("ai.deleteNamed", { name: provider.name })}
                >
                  <Trash2 size={11} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <p style={{ margin: 0, fontSize: 11.5, color: "var(--fg-2)" }}>
        {t("ai.keyNote")}
      </p>
      {children}
    </SettingsCard>
  );
};
