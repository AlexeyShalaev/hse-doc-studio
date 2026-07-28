import { useState } from "react";
import { Bot, Pencil, Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  useAIProviders,
  useDeleteAIProvider,
  type AIProvider,
  type AIProviderType,
} from "@entities/ai-provider";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import { AIProviderEditorModal } from "@features/manage-ai-provider";
import { Combobox } from "@shared/ui/Combobox";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import { SettingHead } from "./Setting";

const TYPE_LABEL: Record<AIProviderType, string> = {
  claude: "settings:providers.typeClaude",
  openai: "settings:providers.typeOpenai",
  openai_compat: "settings:providers.typeOpenaiCompat",
  ollama: "settings:providers.typeOllama",
};

type ProviderRowProps = {
  provider: AIProvider;
  isDefault: boolean;
  pending: boolean;
  managed: boolean;
  onEdit: () => void;
  onDelete: () => void;
};

const ProviderRow = ({
  provider,
  isDefault,
  pending,
  managed,
  onEdit,
  onDelete,
}: ProviderRowProps) => {
  const { t } = useTranslation("settings");
  return (
    <div
      className="flex items-center justify-between"
      style={{
        gap: 12,
        padding: "10px 12px",
        borderRadius: 6,
        border: isDefault
          ? "1px solid var(--accent)"
          : "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
        <div className="flex items-center" style={{ gap: 8 }}>
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
            {t(TYPE_LABEL[provider.type])}
          </span>
          {isDefault && (
            <span
              className="mono"
              style={{ fontSize: 10, color: "var(--accent)" }}
            >
              {t("providers.default")}
            </span>
          )}
        </div>
        <div className="dim" style={{ fontSize: 11 }}>
          {provider.models.length > 0
            ? t("providers.modelCount", { count: provider.models.length })
            : t("providers.modelsNotLoaded")}
          {provider.base_url ? ` · ${provider.base_url}` : ""}
          {!provider.ssl_verify && (
            <span style={{ color: "var(--c-warn)" }}> · TLS ✕</span>
          )}
        </div>
      </div>
      <div className="flex items-center" style={{ gap: 6 }}>
        {!managed && (
          <button
            type="button"
            className="btn xs"
            onClick={onEdit}
            title={t("providers.edit")}
          >
            <Pencil size={11} />
          </button>
        )}
        <button
          type="button"
          className="btn xs"
          onClick={onDelete}
          disabled={pending}
          title={
            managed ? t("providers.deleteManagedTitle") : t("providers.delete")
          }
        >
          <Trash2 size={11} />
        </button>
      </div>
    </div>
  );
};

export const ProvidersSection = () => {
  const { t } = useTranslation("settings");
  const providersQuery = useAIProviders();
  const deleteProvider = useDeleteAIProvider();
  const settings = useAppSettings();
  const updateSettings = useUpdateAppSettings();

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<AIProvider | null>(null);

  const providers = providersQuery.data ?? [];
  const defaultProviderId = settings.data?.default_ai_provider_id ?? "";
  const defaultModel = settings.data?.default_ai_model ?? "";
  const selectedProvider = providers.find((p) => p.id === defaultProviderId);

  const openCreate = () => {
    setEditing(null);
    setEditorOpen(true);
  };

  const openEdit = (provider: AIProvider) => {
    setEditing(provider);
    setEditorOpen(true);
  };

  const handleDelete = (provider: AIProvider) => {
    if (!window.confirm(t("providers.deleteConfirm", { name: provider.name })))
      return;
    deleteProvider.mutate(provider.id, {
      onSuccess: () => {
        toast.success(t("providers.deletedToast", { name: provider.name }));
        // Drop the global default if it pointed at the deleted provider.
        if (provider.id === defaultProviderId) {
          updateSettings.mutate({
            default_ai_provider_id: null,
            default_ai_model: null,
          });
        }
      },
    });
  };

  const handleProviderChange = (id: string) => {
    const provider = providers.find((p) => p.id === id);
    updateSettings.mutate({
      default_ai_provider_id: id || null,
      // Reset to the provider's first model so the pair stays consistent.
      default_ai_model: provider?.models[0] ?? null,
    });
  };

  const handleModelChange = (model: string) => {
    updateSettings.mutate({ default_ai_model: model || null });
  };

  return (
    <>
      <SettingHead
        anchorId="providers"
        title={t("providers.title")}
        sub={t("providers.subtitle")}
      />

      <div className="flex flex-col" style={{ gap: 12, paddingBottom: 14 }}>
        {providersQuery.isLoading ? (
          <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
            <Spinner size="sm" />
            <span className="dim">{t("providers.loading")}</span>
          </div>
        ) : providers.length === 0 ? (
          <div className="dim" style={{ fontSize: 12 }}>
            {t("providers.empty")}
          </div>
        ) : (
          <div className="flex flex-col" style={{ gap: 6 }}>
            {providers.map((provider) => (
              <ProviderRow
                key={provider.id}
                provider={provider}
                isDefault={provider.id === defaultProviderId}
                pending={deleteProvider.isPending}
                managed={provider.type === "ollama"}
                onEdit={() => {
                  openEdit(provider);
                }}
                onDelete={() => {
                  handleDelete(provider);
                }}
              />
            ))}
          </div>
        )}

        <div>
          <button type="button" className="btn xs" onClick={openCreate}>
            <Plus size={11} />
            {t("providers.add")}
          </button>
        </div>

        {providers.length > 0 && (
          <div
            id="providers-default-model"
            className="flex flex-col settings-anchor"
            style={{
              gap: 8,
              padding: 12,
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--bg-1)",
            }}
          >
            <div
              className="dim"
              style={{
                fontSize: 10,
                textTransform: "uppercase",
                letterSpacing: 0.5,
              }}
            >
              {t("providers.defaultModelTitle")}
            </div>
            <div
              className="grid"
              style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}
            >
              <Combobox
                value={defaultProviderId}
                onValueChange={handleProviderChange}
                options={providers.map((p) => ({ value: p.id, label: p.name }))}
                placeholder={t("providers.providerPlaceholder")}
                searchPlaceholder={t("providers.providerSearchPlaceholder")}
              />
              <Combobox
                value={defaultModel}
                onValueChange={handleModelChange}
                options={(selectedProvider?.models ?? []).map((m) => ({
                  value: m,
                  label: m,
                }))}
                placeholder={
                  selectedProvider
                    ? selectedProvider.models.length > 0
                      ? t("providers.modelPlaceholder")
                      : t("providers.noModelsPlaceholder")
                    : t("providers.selectProviderFirst")
                }
                searchPlaceholder={t("providers.modelSearchPlaceholder")}
                emptyText={t("providers.noModelsEmpty")}
                disabled={
                  !selectedProvider || selectedProvider.models.length === 0
                }
              />
            </div>
          </div>
        )}
      </div>

      {/* Mounted only while open and keyed by target → fresh form state each
          time, no reset effect needed. */}
      {editorOpen && (
        <AIProviderEditorModal
          key={editing?.id ?? "new"}
          isOpen
          onClose={() => {
            setEditorOpen(false);
          }}
          provider={editing}
        />
      )}
    </>
  );
};
