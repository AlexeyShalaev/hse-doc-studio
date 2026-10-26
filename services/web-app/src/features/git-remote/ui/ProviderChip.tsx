import { FolderGit2, GitBranch, Server } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ParsedRemoteUrl } from "../lib/parseRemoteUrl";

export type ProviderChipProps = {
  url: ParsedRemoteUrl;
};

// Что за адрес введён: сервер, владелец и репозиторий. Показывается под полем
// адреса, чтобы сразу было видно, что мы поняли из строки.
export const ProviderChip = ({ url }: ProviderChipProps) => {
  const { t } = useTranslation("gitRemote");
  const Icon =
    url.kind === "file"
      ? FolderGit2
      : url.provider === "other"
        ? Server
        : GitBranch;
  const repoPath = [url.owner, url.repo].filter(Boolean).join("/");
  return (
    <div
      className="flex items-center"
      data-testid="provider-chip"
      style={{ gap: 8, minWidth: 0, flexWrap: "wrap" }}
    >
      <span className="chip accent" style={{ gap: 5 }}>
        <Icon size={11} aria-hidden="true" />
        {url.kind === "file"
          ? t("urlKind.file")
          : t(`provider.${url.provider}`)}
      </span>
      {url.host && (
        <span
          className="mono dim"
          style={{ fontSize: 11.5 }}
          data-testid="provider-host"
        >
          {url.host}
          {url.port !== null ? `:${String(url.port)}` : ""}
        </span>
      )}
      {repoPath !== "" && (
        <span
          className="mono truncate"
          style={{ fontSize: 11.5, color: "var(--fg-0)", minWidth: 0 }}
          title={repoPath}
        >
          {repoPath}
        </span>
      )}
      {url.kind !== "file" && (
        <span className="chip subtle" style={{ marginLeft: "auto" }}>
          {t(`urlKind.${url.kind}`)}
        </span>
      )}
    </div>
  );
};
