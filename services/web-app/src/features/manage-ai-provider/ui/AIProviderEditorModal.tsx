import { useState } from "react";
import { useTranslation } from "react-i18next";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { clsx } from "clsx";
import { Download, Loader2, Plus, Trash2, X } from "lucide-react";
import { Link } from "react-router";
import {
  aiProviderApiFor,
  type AIProviderOwner,
  CreateAIProviderSchema,
  useCreateAIProvider,
  useUpdateAIProvider,
  type AIProvider,
  type AIProviderType,
  type UpdateAIProviderInput,
} from "@entities/ai-provider";
import { useCapabilities } from "@entities/session";
import { useMyRunners, type MyRunner } from "@entities/runner";
import { Button } from "@shared/ui/Button";
import { Select } from "@shared/ui/Select";
import { useUiVariant } from "@shared/ui/UiVariant";
import { i18n, toast } from "@shared/lib";
import { failureCode } from "@shared/api";

type AIProviderEditorModalProps = {
  isOpen: boolean;
  onClose: () => void;
  // null/undefined → create a new provider; a provider → edit it.
  provider?: AIProvider | null;
  // Whose provider this is: personal (default) or the installation-wide one (admin).
  owner?: AIProviderOwner;
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
  // У провайдера через раннер ключа нет: он хранится у раннера.
  runner: "",
};

const DEFAULT_CONNECT_TIMEOUT_S = 10;
const DEFAULT_REQUEST_TIMEOUT_S = 60;
// Модель на своём железе отвечает медленнее облачной: таймаут ответа больше.
const RUNNER_REQUEST_TIMEOUT_S = 120;

/** Текст отказа ретрансляции: каталог ошибок сервера или как есть. */
const reasonOf = (error: unknown): string => {
  const key = `errors:code.${failureCode(error)}`;
  if (i18n.exists(key)) return i18n.t(key);
  return error instanceof Error ? error.message : String(error);
};

type FetchState = "idle" | "loading" | "error";

export const AIProviderEditorModal = ({
  isOpen,
  onClose,
  provider,
  owner = "user",
}: AIProviderEditorModalProps) => {
  const { t } = useTranslation("aiProvider");
  const variant = useUiVariant();
  const isEdit = Boolean(provider);
  const createProvider = useCreateAIProvider(owner);
  const updateProvider = useUpdateAIProvider(owner);

  // Initialised straight from props: the caller mounts this modal fresh per
  // open (and keys it by provider), so there is no stale state to reset.
  const [name, setName] = useState(provider?.name ?? "");
  const [type, setType] = useState<EditableProviderType>(
    provider && provider.type !== "ollama" ? provider.type : "claude",
  );
  // Свой раннер как ИИ-ретранслятор: только личный провайдер и только когда
  // сервер разрешает личные раннеры.
  const { has } = useCapabilities();
  const runnerKind = owner === "user" && has("personal_runners");
  const isRunner = type === "runner";
  const runners = useMyRunners({ enabled: runnerKind });
  const myRunners: MyRunner[] = (runners.data ?? []).filter((r) => !r.revoked);
  const [runnerId, setRunnerId] = useState(provider?.relay?.runner_id ?? "");
  const [endpoint, setEndpoint] = useState(provider?.relay?.endpoint ?? "");
  const pickedRunner = myRunners.find((r) => r.id === runnerId) ?? null;
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
    String(
      provider?.request_timeout_s ??
        (provider?.type === "runner"
          ? RUNNER_REQUEST_TIMEOUT_S
          : DEFAULT_REQUEST_TIMEOUT_S),
    ),
  );
  const [error, setError] = useState<string | null>(null);
  const [fetchState, setFetchState] = useState<FetchState>("idle");
  const [fetchError, setFetchError] = useState<string | null>(null);

  const showBaseUrl = type !== "claude" && !isRunner;
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
      const { models: fetched } = await aiProviderApiFor(owner).fetchModels(
        provider.id,
      );
      if (fetched.length === 0) throw new Error(t("fetch.emptyModels"));
      setModels(fetched);
      setFetchState("idle");
    } catch (e) {
      setFetchError(
        e instanceof Error || failureCode(e) !== "unknown"
          ? reasonOf(e)
          : t("fetch.failed"),
      );
      setFetchState("error");
    }
  };

  const submitRunner = (requestTimeoutS: number) => {
    if (!runnerId || !endpoint) {
      setError(t("runner.required"));
      return;
    }
    const trimmed = name.trim();
    if (!trimmed) {
      setError(t("validation.nameRequired"));
      return;
    }
    if (isEdit && provider) {
      updateProvider.mutate(
        {
          id: provider.id,
          body: {
            name: trimmed,
            request_timeout_s: requestTimeoutS,
            models,
            runner_id: runnerId,
            runner_endpoint: endpoint,
          },
        },
        {
          onSuccess: (updated) => {
            toast.success(t("toast.saved", { name: updated.name }));
            onClose();
          },
        },
      );
      return;
    }
    createProvider.mutate(
      {
        name: trimmed,
        type: "runner",
        api_key: "",
        base_url: "",
        models: [],
        ssl_verify: true,
        connect_timeout_s: DEFAULT_CONNECT_TIMEOUT_S,
        request_timeout_s: requestTimeoutS,
        runner_id: runnerId,
        runner_endpoint: endpoint,
      },
      {
        onSuccess: (created) => {
          toast.success(t("toast.added", { name: created.name }));
          onClose();
          // Модели знает только модель за раннером: просим список через него же.
          const api = aiProviderApiFor(owner);
          void api
            .fetchModels(created.id)
            .then(({ models: fetched }) =>
              updateProvider.mutateAsync({
                id: created.id,
                body: { models: fetched },
              }),
            )
            .then((saved) => {
              toast.success(
                t("runner.modelsLoaded", { count: saved.models.length }),
              );
            })
            .catch((e: unknown) => {
              toast.error(t("runner.modelsFailed", { reason: reasonOf(e) }));
            });
        },
      },
    );
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
    if (isRunner) {
      submitRunner(requestTimeoutS);
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
          className={clsx(
            "modal-panel fixed left-1/2 top-1/2 z-[102] -translate-x-1/2 -translate-y-1/2",
            variant === "console" && "ui-console",
          )}
          // Анатомия как у общего Modal: заголовок с описанием, середина,
          // кнопки справа без отдельной полосы.
          style={{
            width: runnerKind ? 560 : 480,
            maxWidth: "calc(100vw - 32px)",
            maxHeight: "calc(100vh - 64px)",
          }}
        >
          <div style={{ padding: "24px 24px 0", flexShrink: 0 }}>
            <DialogPrimitive.Title
              style={{
                margin: 0,
                paddingRight: 28,
                fontSize: 15,
                fontWeight: 600,
                color: "var(--fg-0)",
              }}
            >
              {isEdit ? t("modal.titleEdit") : t("modal.titleCreate")}
            </DialogPrimitive.Title>
            <DialogPrimitive.Description
              style={{
                margin: "8px 0 0",
                fontSize: 13,
                lineHeight: 1.5,
                color: "var(--fg-2)",
              }}
            >
              {t("modal.lead")}
            </DialogPrimitive.Description>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={onClose}
            aria-label={t("modal.close")}
            style={{ position: "absolute", right: 12, top: 12 }}
          >
            <X size={14} />
          </button>

          <div
            className="modal-body"
            style={{
              padding: "16px 24px 4px",
              overflowY: "auto",
              flex: "1 1 auto",
              minHeight: 0,
            }}
          >
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="form-label">{t("fields.name")}</label>
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
                <label className="form-label">{t("fields.type")}</label>
                <div className="seg seg-fill">
                  {/* Вид провайдера после создания через раннер не меняется:
                      у прямого провайдера нет раннера, у ретранслятора нет ключа. */}
                  {(isEdit && provider?.type === "runner"
                    ? []
                    : TYPE_OPTIONS
                  ).map((opt) => (
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
                  {runnerKind && (!isEdit || provider?.type === "runner") && (
                    <button
                      type="button"
                      className={clsx(isRunner && "active")}
                      data-testid="ai-provider-kind-runner"
                      onClick={() => {
                        setType("runner");
                        if (!isEdit) {
                          setRequestTimeout(String(RUNNER_REQUEST_TIMEOUT_S));
                        }
                      }}
                    >
                      {t("type.runner")}
                    </button>
                  )}
                </div>
              </div>

              {isRunner && (
                <RunnerFields
                  runners={myRunners}
                  loading={runners.isLoading}
                  runnerId={runnerId}
                  endpoint={endpoint}
                  picked={pickedRunner}
                  onRunner={(id) => {
                    setRunnerId(id);
                    const next = myRunners.find((r) => r.id === id);
                    // Единственный адрес раннера выбираем сразу.
                    setEndpoint(
                      next?.ai_endpoints.length === 1
                        ? (next.ai_endpoints[0]?.name ?? "")
                        : "",
                    );
                    if (!name.trim() && next) setName(next.name);
                  }}
                  onEndpoint={setEndpoint}
                />
              )}

              {!isRunner && (
                <div className="flex flex-col gap-1.5">
                  <label className="form-label">{t("fields.apiKey")}</label>
                  <input
                    className="input mono"
                    type="password"
                    value={apiKey}
                    placeholder={
                      isEdit
                        ? t("fields.apiKeyPlaceholderEdit")
                        : keyPlaceholder
                    }
                    onChange={(e) => {
                      setApiKey(e.target.value);
                    }}
                  />
                  <span className="form-hint">{t("fields.apiKeyHint")}</span>
                </div>
              )}

              {showBaseUrl && (
                <div className="flex flex-col gap-1.5">
                  <label className="form-label">{t("fields.baseUrl")}</label>
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
                  <label className="form-label">{t("fields.models")}</label>
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

                {models.length > 0 && (
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
                          aria-label={`${t("models.removeModel")}: ${model}`}
                        >
                          <Trash2 size={11} />
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-2">
                  <input
                    className="input"
                    value={newModel}
                    aria-label={t("fields.models")}
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
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={addModel}
                    disabled={!newModel.trim()}
                    style={{ gap: 6, flexShrink: 0 }}
                  >
                    <Plus size={13} aria-hidden="true" />
                    {t("models.addModel")}
                  </Button>
                </div>
                {models.length === 0 && (
                  <span className="form-hint">
                    {isRunner && !isEdit
                      ? t("runner.modelsAfter")
                      : isEdit
                        ? t("models.emptyEdit")
                        : t("models.emptyCreate")}
                  </span>
                )}
                {fetchState === "error" && fetchError && (
                  <span className="text-xs text-c-err">{fetchError}</span>
                )}
              </div>

              {!isRunner && (
                <div className="flex flex-col gap-1.5">
                  <label className="form-label">{t("fields.tlsVerify")}</label>
                  <div className="seg seg-fill">
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
                    <span
                      className="form-hint"
                      style={{ color: "var(--c-warn)" }}
                    >
                      {t("fields.tlsWarning")}
                    </span>
                  )}
                </div>
              )}

              <div
                className="grid"
                style={{
                  gridTemplateColumns: isRunner ? "1fr" : "1fr 1fr",
                  gap: 8,
                }}
              >
                {!isRunner && (
                  <div className="flex flex-col gap-1.5">
                    <label className="form-label">
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
                )}
                <div className="flex flex-col gap-1.5">
                  <label className="form-label">
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
            style={{ gap: 10, padding: "16px 24px 24px", flexShrink: 0 }}
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

type RunnerFieldsProps = {
  runners: MyRunner[];
  loading: boolean;
  runnerId: string;
  endpoint: string;
  picked: MyRunner | null;
  onRunner: (id: string) => void;
  onEndpoint: (name: string) => void;
};

/** Свой раннер и ИИ-адрес, который он объявил: сервер знает только имя адреса. */
const RunnerFields = ({
  runners,
  loading,
  runnerId,
  endpoint,
  picked,
  onRunner,
  onEndpoint,
}: RunnerFieldsProps) => {
  const { t } = useTranslation("aiProvider");
  const { t: tr } = useTranslation("runners");
  if (!loading && runners.length === 0) {
    return (
      <div
        className="flex items-center justify-between"
        style={{
          gap: 12,
          padding: "10px 12px",
          borderRadius: "var(--r-2)",
          border: "1px dashed var(--border)",
          fontSize: 12.5,
        }}
        data-testid="ai-provider-no-runners"
      >
        <span>{t("runner.noRunners")}</span>
        <Link
          to="/settings/runners"
          className="btn xs"
          style={{ textDecoration: "none" }}
        >
          {t("runner.connect")}
        </Link>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <label className="form-label" htmlFor="ai-provider-runner">
          {t("runner.runner")}
        </label>
        <div data-testid="ai-provider-runner-select">
          <Select
            id="ai-provider-runner"
            value={runnerId}
            onValueChange={onRunner}
            placeholder={t("runner.runnerPlaceholder")}
            options={runners.map((r) => ({
              value: r.id,
              label: `${r.name} · ${tr(`mine.state.${r.state}`)}`,
            }))}
          />
        </div>
      </div>
      {picked?.ai_endpoints.length === 0 ? (
        <span
          className="form-hint"
          style={{ color: "var(--c-warn)" }}
          data-testid="ai-provider-no-endpoints"
        >
          {t("runner.noEndpoints", { name: picked.name })}
        </span>
      ) : (
        <div className="flex flex-col gap-1.5">
          <label className="form-label" htmlFor="ai-provider-endpoint">
            {t("runner.endpoint")}
          </label>
          <div data-testid="ai-provider-endpoint-select">
            <Select
              id="ai-provider-endpoint"
              value={endpoint}
              onValueChange={onEndpoint}
              isDisabled={!picked}
              placeholder={t("runner.endpointPlaceholder")}
              options={(picked?.ai_endpoints ?? []).map((e) => ({
                value: e.name,
                label: `${e.name} (${e.flavor === "ollama" ? "Ollama" : "OpenAI API"})`,
              }))}
            />
          </div>
        </div>
      )}
      <span className="form-hint">{t("runner.hint")}</span>
    </div>
  );
};
