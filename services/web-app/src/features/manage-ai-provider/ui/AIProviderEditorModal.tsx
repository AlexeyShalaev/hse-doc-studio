import { useState } from "react";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { clsx } from "clsx";
import { Download, Loader2, Plus, Trash2, X } from "lucide-react";
import {
  aiProviderApi,
  CreateAIProviderSchema,
  useCreateAIProvider,
  useUpdateAIProvider,
  type AIProvider,
  type AIProviderType,
  type UpdateAIProviderInput,
} from "@entities/ai-provider";
import { Button } from "@shared/ui/Button";
import { toast } from "@shared/lib";

type AIProviderEditorModalProps = {
  isOpen: boolean;
  onClose: () => void;
  // null/undefined → create a new provider; a provider → edit it.
  provider?: AIProvider | null;
};

// `ollama` providers are auto-managed by the local runtime and never created or
// edited through this modal, so the manual form only covers the user-creatable
// types.
type EditableProviderType = Exclude<AIProviderType, "ollama">;

// Labels for `Anthropic` / `OpenAI` are brand names kept verbatim; only the
// `openai_compat` label is localised (see `type.openaiCompat`).
const TYPE_OPTIONS: { value: EditableProviderType; label: string | null }[] = [
  { value: "claude", label: "Anthropic" },
  { value: "openai", label: "OpenAI" },
  { value: "openai_compat", label: null },
];

const KEY_PLACEHOLDER: Record<EditableProviderType, string> = {
  claude: "sk-ant-api03-…",
  openai: "sk-…",
  // openai_compat placeholder is localised (see `keyPlaceholder.openaiCompat`).
  openai_compat: "",
};

const DEFAULT_CONNECT_TIMEOUT_S = 10;
const DEFAULT_REQUEST_TIMEOUT_S = 60;

type FetchState = "idle" | "loading" | "error";

export const AIProviderEditorModal = ({
  isOpen,
  onClose,
  provider,
}: AIProviderEditorModalProps) => {
  const { t } = useTranslation("aiProvider");
  const isEdit = Boolean(provider);
  const createProvider = useCreateAIProvider();
  const updateProvider = useUpdateAIProvider();

  // Initialised straight from props: the caller mounts this modal fresh per
  // open (and keys it by provider), so there is no stale state to reset.
  const [name, setName] = useState(provider?.name ?? "");
  const [type, setType] = useState<EditableProviderType>(
    provider && provider.type !== "ollama" ? provider.type : "claude",
  );
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? "");
  const [models, setModels] = useState<string[]>(provider?.models ?? []);
  const [newModel, setNewModel] = useState("");
  const [sslVerify, setSslVerify] = useState(provider?.ssl_verify ?? true);
  // Timeouts are held as strings so the number inputs can be edited freely;
  // parsed + validated on submit.
  const [connectTimeout, setConnectTimeout] = useState(
    String(provider?.connect_timeout_s ?? DEFAULT_CONNECT_TIMEOUT_S),
  );
  const [requestTimeout, setRequestTimeout] = useState(
    String(provider?.request_timeout_s ?? DEFAULT_REQUEST_TIMEOUT_S),
  );
  const [error, setError] = useState<string | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>("idle");
  const [fetchError, setFetchError] = useState<string | null>(null);

  const showBaseUrl = type !== "claude";
  const isPending = createProvider.isPending || updateProvider.isPending;

  const keyPlaceholder =
    type === "openai_compat"
      ? t("keyPlaceholder.openaiCompat")
      : KEY_PLACEHOLDER[type];
  const baseUrlPlaceholder =
    type === "openai"
      ? t("baseUrlPlaceholder.openai")
      : type === "openai_compat"
        ? t("baseUrlPlaceholder.openaiCompat")
        : "";

  const addModel = () => {
    const trimmed = newModel.trim();
    if (!trimmed) return;
    if (!models.includes(trimmed)) setModels([...models, trimmed]);
    setNewModel("");
  };

  const removeModel = (model: string) => {
    setModels(models.filter((m) => m !== model));
  };

  const handleFetchModels = async () => {
    if (!provider) return;
    setFetchState("loading");
    setFetchError(null);
    try {
      const { models: fetched } = await aiProviderApi.fetchModels(provider.id);
      if (fetched.length === 0) throw new Error(t("fetch.emptyModels"));
      setModels(fetched);
      setFetchState("idle");
    } catch (e) {
      setFetchError(e instanceof Error ? e.message : t("fetch.failed"));
      setFetchState("error");
    }
  };

  const handleSubmit = () => {
    setError(null);
    const resolvedBaseUrl = showBaseUrl ? baseUrl.trim() : "";

    const connectTimeoutS = Number(connectTimeout);
    const requestTimeoutS = Number(requestTimeout);
    if (!(connectTimeoutS > 0) || !(requestTimeoutS > 0)) {
      setError(t("validation.timeoutsPositive"));
      return;
    }

    if (isEdit && provider) {
      const body: UpdateAIProviderInput = {
        name: name.trim(),
        type,
        base_url: resolvedBaseUrl,
        models,
        ssl_verify: sslVerify,
        connect_timeout_s: connectTimeoutS,
        request_timeout_s: requestTimeoutS,
      };
      // Blank key → keep the stored one (never sent back to the browser).
      if (apiKey.trim()) body.api_key = apiKey;
      if (!body.name) {
        setError(t("validation.nameRequired"));
        return;
      }
      updateProvider.mutate(
        { id: provider.id, body },
        {
          onSuccess: (updated) => {
            toast.success(t("toast.saved", { name: updated.name }));
            onClose();
          },
        },
      );
      return;
    }

    const parsed = CreateAIProviderSchema.safeParse({
      name: name.trim(),
      type,
      api_key: apiKey,
      base_url: resolvedBaseUrl,
      models,
      ssl_verify: sslVerify,
      connect_timeout_s: connectTimeoutS,
      request_timeout_s: requestTimeoutS,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? t("validation.checkFields"));
      return;
    }
    createProvider.mutate(parsed.data, {
      onSuccess: (created) => {
        toast.success(t("toast.added", { name: created.name }));
        onClose();
      },
    });
  };

  return (
    <DialogPrimitive.Root
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="scrim" />
        <DialogPrimitive.Content
          className="modal-panel fixed left-1/2 top-1/2 z-[102] -translate-x-1/2 -translate-y-1/2"
          style={{ width: 460, maxWidth: "calc(100vw - 32px)" }}
        >
          <DialogPrimitive.Description className="sr-only">
            {t("modal.a11yDescription")}
          </DialogPrimitive.Description>

          <div
            className="flex items-center justify-between"
            style={{
              padding: "12px 18px",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <DialogPrimitive.Title
              style={{ fontSize: 14, fontWeight: 600, margin: 0 }}
            >
              {isEdit ? t("modal.titleEdit") : t("modal.titleCreate")}
            </DialogPrimitive.Title>
            <button
              type="button"
              className="icon-btn"
              onClick={onClose}
              title={t("modal.close")}
            >
              <X size={14} />
            </button>
          </div>

          <div style={{ padding: 18, overflowY: "auto" }}>
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-fg-1">
                  {t("fields.name")}
                </label>
                <input
                  className="input"
                  value={name}
                  placeholder={t("fields.namePlaceholder")}
                  onChange={(e) => {
                    setName(e.target.value);
                  }}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-fg-1">
                  {t("fields.type")}
                </label>
                <div className="seg">
                  {TYPE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      className={clsx(type === opt.value && "active")}
                      onClick={() => {
                        setType(opt.value);
                      }}
                    >
                      {opt.label ?? t("type.openaiCompat")}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-fg-1">
                  {t("fields.apiKey")}
                </label>
                <input
                  className="input mono"
                  type="password"
                  value={apiKey}
                  placeholder={
                    isEdit ? t("fields.apiKeyPlaceholderEdit") : keyPlaceholder
                  }
                  onChange={(e) => {
                    setApiKey(e.target.value);
                  }}
                />
                <span className="hint">{t("fields.apiKeyHint")}</span>
              </div>

              {showBaseUrl && (
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-fg-1">
                    {t("fields.baseUrl")}
                  </label>
                  <input
                    className="input mono"
                    type="url"
                    value={baseUrl}
                    placeholder={baseUrlPlaceholder}
                    onChange={(e) => {
                      setBaseUrl(e.target.value);
                    }}
                  />
                </div>
              )}

              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-medium text-fg-1">
                    {t("fields.models")}
                  </label>
                  {isEdit && (
                    <button
                      type="button"
                      className="btn xs"
                      onClick={() => {
                        void handleFetchModels();
                      }}
                      disabled={fetchState === "loading"}
                      title={t("models.fetchTitle")}
                    >
                      {fetchState === "loading" ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : (
                        <Download size={11} />
                      )}
                      {t("models.fetchFromApi")}
                    </button>
                  )}
                </div>

                {models.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {models.map((model) => (
                      <span
                        key={model}
                        className="mono rounded-r-1 flex items-center gap-1 border border-border bg-bg-2 px-2 py-0.5 text-xs"
                      >
                        {model}
                        <button
                          type="button"
                          className="text-fg-3 hover:text-c-err"
                          onClick={() => {
                            removeModel(model);
                          }}
                          title={t("models.removeModel")}
                        >
                          <Trash2 size={11} />
                        </button>
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="hint">
                    {isEdit ? t("models.emptyEdit") : t("models.emptyCreate")}
                  </span>
                )}

                <div className="flex items-center gap-2">
                  <input
                    className="input mono"
                    value={newModel}
                    placeholder={t("models.newModelPlaceholder")}
                    onChange={(e) => {
                      setNewModel(e.target.value);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addModel();
                      }
                    }}
                  />
                  <button
                    type="button"
                    className="btn xs"
                    onClick={addModel}
                    disabled={!newModel.trim()}
                  >
                    <Plus size={11} />
                  </button>
                </div>
                {fetchState === "error" && fetchError && (
                  <span className="text-xs text-c-err">{fetchError}</span>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-fg-1">
                  {t("fields.tlsVerify")}
                </label>
                <div className="seg">
                  <button
                    type="button"
                    className={clsx(sslVerify && "active")}
                    onClick={() => {
                      setSslVerify(true);
                    }}
                  >
                    {t("fields.tlsOn")}
                  </button>
                  <button
                    type="button"
                    className={clsx(!sslVerify && "active")}
                    onClick={() => {
                      setSslVerify(false);
                    }}
                  >
                    {t("fields.tlsOff")}
                  </button>
                </div>
                {!sslVerify && (
                  <span className="hint" style={{ color: "var(--c-warn)" }}>
                    {t("fields.tlsWarning")}
                  </span>
                )}
              </div>

              <div
                className="grid"
                style={{ gridTemplateColumns: "1fr 1fr", gap: 8 }}
              >
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-fg-1">
                    {t("fields.connectTimeout")}
                  </label>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    step={1}
                    value={connectTimeout}
                    onChange={(e) => {
                      setConnectTimeout(e.target.value);
                    }}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium text-fg-1">
                    {t("fields.requestTimeout")}
                  </label>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    step={1}
                    value={requestTimeout}
                    onChange={(e) => {
                      setRequestTimeout(e.target.value);
                    }}
                  />
                </div>
              </div>

              {error && <span className="text-xs text-c-err">{error}</span>}
            </div>
          </div>

          <div
            className="flex items-center justify-end"
            style={{
              gap: 8,
              padding: "10px 18px",
              borderTop: "1px solid var(--border)",
            }}
          >
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={isPending}
            >
              {t("actions.cancel")}
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={isPending}>
              {isEdit ? t("actions.save") : t("actions.add")}
            </Button>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
