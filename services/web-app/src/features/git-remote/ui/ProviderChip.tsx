import { useId, useState } from "react";
import { Check, FolderGit2, GitBranch, Server } from "lucide-react";
import { useTranslation } from "react-i18next";
import { GIT_PROVIDERS, type GitProvider } from "@entities/git-remote";
import { describeGitError, type GitProviderInfo } from "@entities/git-sync";
import { Notice } from "@shared/ui/ConflictKit";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui/Popover";
import { Spinner } from "@shared/ui/Spinner";
import { shortVersion } from "../lib/formatDate";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";
import { useHostProvider, type HostProvider } from "../model/useHostProvider";

export type ProviderChipProps = {
  url: ParsedRemoteUrl;
  /** Что сервер сказал о себе при проверке: версия и способ определения. */
  known?: GitProviderInfo | null;
  /** false: без «изменить» (например, внутри уже подключённого проекта). */
  editable?: boolean;
};

const PROVIDER_ORDER: readonly GitProvider[] = GIT_PROVIDERS;

const ProviderPicker = ({
  provider,
  host,
}: {
  provider: HostProvider;
  host: string;
}) => {
  const { t } = useTranslation("gitRemote");
  const uid = useId();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { detection } = provider;
  const hasOverride = detection.detected_by === "override";

  const choose = async (next: GitProvider | null): Promise<void> => {
    setError(null);
    try {
      await provider.setOverride(next);
      setOpen(false);
    } catch (caught) {
      setError(describeGitError(caught, t("providerPicker.failed")));
    }
  };

  return (
    <Popover
      modal
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setError(null);
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="sync-history-link"
          data-testid="provider-change"
          aria-label={t("providerChip.changeLabel", { host })}
        >
          {t("providerChip.change")}
        </button>
      </PopoverTrigger>
      <PopoverContent
        width={320}
        align="start"
        aria-label={t("providerPicker.title")}
      >
        <div
          className="flex flex-col"
          style={{ gap: "0.625rem", padding: "0.75rem" }}
          data-testid="provider-picker"
        >
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.8125rem" }}>
              {t("providerPicker.title")}
            </div>
            <p
              className="dim"
              style={{ margin: "0.1875rem 0 0", fontSize: "0.71875rem" }}
            >
              {t("providerPicker.text", { host })}
            </p>
          </div>
          <div
            role="radiogroup"
            aria-label={t("providerPicker.title")}
            className="flex flex-col"
            style={{ gap: "0.1875rem" }}
          >
            {PROVIDER_ORDER.map((id) => {
              const active = detection.id === id;
              return (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  disabled={provider.isSaving}
                  className="row-btn"
                  data-testid={`provider-option-${id}`}
                  onClick={() => {
                    void choose(id);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    padding: "0.375rem 0.5rem",
                    borderRadius: "var(--r-2)",
                    background: active ? "var(--accent-soft)" : "transparent",
                    textAlign: "left",
                    fontSize: "0.78125rem",
                  }}
                >
                  <span style={{ width: "0.875rem", flexShrink: 0 }}>
                    {active && <Check size="0.8125rem" aria-hidden="true" />}
                  </span>
                  {t(`providerPicker.option.${id}`)}
                </button>
              );
            })}
          </div>
          {hasOverride && (
            <button
              type="button"
              className="btn xs"
              disabled={provider.isSaving}
              style={{ alignSelf: "flex-start" }}
              onClick={() => {
                void choose(null);
              }}
            >
              {provider.isSaving && <Spinner size="sm" />}
              {t("providerPicker.auto")}
            </button>
          )}
          <div className="field">
            <label htmlFor={`${uid}-path`}>{t("providerPicker.path")}</label>
            <input
              id={`${uid}-path`}
              type="text"
              className="input mono"
              value={provider.subpath}
              placeholder="/gitlab"
              spellCheck={false}
              autoComplete="off"
              autoCapitalize="off"
              onChange={(event) => {
                provider.setSubpath(event.target.value);
              }}
            />
            <p className="hint" style={{ margin: 0 }}>
              {t("providerPicker.pathHint")}
            </p>
          </div>
          {error && <Notice tone="err" role="alert" text={error} />}
        </div>
      </PopoverContent>
    </Popover>
  );
};

// Что за адрес введён: сервер (с версией, если она известна), владелец и
// репозиторий. Показывается под полем адреса, чтобы сразу было видно, что мы
// поняли из строки; тип сервера человек может поправить, выбор запоминается.
export const ProviderChip = ({
  url,
  known = null,
  editable = true,
}: ProviderChipProps) => {
  const { t } = useTranslation("gitRemote");
  const provider = useHostProvider(url, known);
  const { detection } = provider;
  const Icon =
    url.kind === "file"
      ? FolderGit2
      : detection.id === "other"
        ? Server
        : GitBranch;
  const repoPath = [url.owner, url.repo].filter(Boolean).join("/");
  const version = shortVersion(detection.version);
  const unknown =
    url.kind !== "file" && detection.id === "other" && !detection.version;

  return (
    <div className="flex flex-col" style={{ gap: "0.25rem" }}>
      <div
        className="flex items-center"
        data-testid="provider-chip"
        data-detected-by={detection.detected_by}
        style={{ gap: "0.5rem", minWidth: 0, flexWrap: "wrap" }}
      >
        <span
          className="chip accent"
          style={{ gap: "0.3125rem" }}
          title={
            url.kind === "file"
              ? undefined
              : t(`providerChip.detectedBy.${detection.detected_by}`)
          }
        >
          <Icon size="0.6875rem" aria-hidden="true" />
          {url.kind === "file"
            ? t("urlKind.file")
            : t(`provider.${detection.id}`)}
          {version !== "" && (
            <span data-testid="provider-version" style={{ opacity: 0.8 }}>
              {` · v${version}`}
            </span>
          )}
        </span>
        {url.host && (
          <span
            className="mono dim"
            style={{ fontSize: "0.71875rem" }}
            data-testid="provider-host"
          >
            {url.host}
            {url.port !== null ? `:${String(url.port)}` : ""}
          </span>
        )}
        {repoPath !== "" && (
          <span
            className="mono truncate"
            style={{
              fontSize: "0.71875rem",
              color: "var(--fg-0)",
              minWidth: 0,
            }}
            title={repoPath}
          >
            {repoPath}
          </span>
        )}
        {editable && url.kind !== "file" && url.host && (
          <ProviderPicker provider={provider} host={url.host} />
        )}
        {url.kind !== "file" && (
          <span className="chip subtle" style={{ marginLeft: "auto" }}>
            {t(`urlKind.${url.kind}`)}
          </span>
        )}
      </div>
      {unknown && editable && (
        <p
          className="dim"
          data-testid="provider-unknown-hint"
          style={{ margin: 0, fontSize: "0.71875rem" }}
        >
          {t("providerChip.unknownHint")}
        </p>
      )}
    </div>
  );
};
