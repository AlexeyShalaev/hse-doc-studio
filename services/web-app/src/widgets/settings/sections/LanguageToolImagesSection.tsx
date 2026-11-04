import { useMemo, useState } from "react";
import {
  CheckCircle2,
  Cloud,
  Download,
  RefreshCw,
  Search,
  Star,
  Trash2,
  XCircle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui/Spinner";
import {
  useLanguageToolImages,
  useLanguageToolRemoteTags,
  useLanguageToolStatus,
  useRemoveLanguageToolImage,
  useSetActiveLanguageToolImage,
  type LanguageToolImage,
  type LanguageToolRemoteTag,
  type LanguageToolStatus,
} from "@entities/languagetool";
import { DockerUnavailableNotice } from "@entities/compile-images";
import { i18n, toast } from "@shared/lib";
import { InstallLanguageToolModal } from "@features/install-languagetool";
import { SettingHead } from "./Setting";

const formatBytes = (bytes: number): string => {
  if (bytes <= 0) return "—";
  const gb = bytes / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  const mb = bytes / 1024 ** 2;
  return `${mb.toFixed(0)} MB`;
};

const formatRelativeDate = (iso: string | null): string => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const days = Math.floor((Date.now() - d.getTime()) / (1000 * 60 * 60 * 24));
  if (days < 1) return i18n.t("settings:languageTool.today");
  if (days < 30)
    return i18n.t("settings:languageTool.daysAgo", { count: days });
  const months = Math.floor(days / 30);
  if (months < 12)
    return i18n.t("settings:languageTool.monthsAgo", { count: months });
  const years = Math.floor(months / 12);
  return i18n.t("settings:languageTool.yearsAgo", { count: years });
};

const InstalledRow = ({
  entry,
  active,
  onSetActive,
  onRemove,
  onUpdate,
  pending,
}: {
  entry: LanguageToolImage;
  active: boolean;
  onSetActive: (image: string) => void;
  onRemove: (image: string) => void;
  onUpdate: (image: string) => void;
  pending: boolean;
}) => {
  const { t } = useTranslation("settings");
  return (
    <div
      className="flex items-center justify-between"
      style={{
        gap: "0.75rem",
        padding: "0.625rem 0.75rem",
        borderRadius: "0.375rem",
        border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
        background: active ? "var(--accent-soft, var(--bg-1))" : "var(--bg-1)",
      }}
    >
      <div className="flex flex-col" style={{ gap: "0.25rem", minWidth: 0 }}>
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          {active ? (
            <Star
              size="0.8125rem"
              style={{ color: "var(--accent)", fill: "var(--accent)" }}
            />
          ) : (
            <CheckCircle2 size="0.8125rem" style={{ color: "var(--c-ok)" }} />
          )}
          <span
            className="mono"
            style={{ fontSize: "0.75rem", fontWeight: 500 }}
          >
            {entry.image}
          </span>
          {active && (
            <span
              className="mono"
              style={{
                fontSize: "0.625rem",
                padding: "1px 0.375rem",
                borderRadius: "0.1875rem",
                background: "var(--accent)",
                color: "var(--bg-0)",
                textTransform: "uppercase",
                letterSpacing: "0.03125rem",
              }}
            >
              {t("languageTool.activeBadge")}
            </span>
          )}
        </div>
        <div
          className="dim"
          style={{
            fontSize: "0.6875rem",
            display: "flex",
            gap: "0.5rem",
            alignItems: "center",
          }}
        >
          <span>{formatBytes(entry.size_bytes)}</span>
          <span>·</span>
          <span className="mono" style={{ fontSize: "0.625rem" }}>
            {entry.id.slice(7, 19)}
          </span>
        </div>
      </div>
      <div className="flex items-center" style={{ gap: "0.375rem" }}>
        {!active && (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              onSetActive(entry.image);
            }}
            disabled={pending}
            title={t("languageTool.makeActiveCheckTitle")}
          >
            <Star size="0.6875rem" />
            {t("languageTool.makeActive")}
          </button>
        )}
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            onUpdate(entry.image);
          }}
          disabled={pending}
          title={t("languageTool.updateTitle")}
        >
          <RefreshCw size="0.6875rem" />
        </button>
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            onRemove(entry.image);
          }}
          disabled={pending || active}
          title={
            active
              ? t("languageTool.removeActiveDisabledTitle")
              : t("languageTool.removeLocalTitle")
          }
        >
          <Trash2 size="0.6875rem" />
        </button>
      </div>
    </div>
  );
};

const RemoteRow = ({
  repo,
  tag,
  installed,
  active,
  onInstall,
  onSetActive,
}: {
  repo: string;
  tag: LanguageToolRemoteTag;
  installed: boolean;
  active: boolean;
  onInstall: (image: string) => void;
  onSetActive: (image: string) => void;
}) => {
  const { t } = useTranslation("settings");
  const image = `${repo}:${tag.name}`;
  return (
    <div
      className="flex items-center justify-between"
      style={{
        gap: "0.75rem",
        padding: "0.5rem 0.75rem",
        borderRadius: "0.375rem",
        background: installed ? "var(--bg-1)" : "transparent",
        border: "1px solid transparent",
      }}
    >
      <div className="flex flex-col" style={{ gap: "0.125rem", minWidth: 0 }}>
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          <span className="mono" style={{ fontSize: "0.75rem" }}>
            {tag.name}
          </span>
          {active && (
            <span
              className="mono"
              style={{ fontSize: "0.625rem", color: "var(--accent)" }}
            >
              {t("languageTool.activeStar")}
            </span>
          )}
          {installed && !active && (
            <span
              className="mono"
              style={{ fontSize: "0.625rem", color: "var(--c-ok)" }}
            >
              {t("languageTool.installedBadge")}
            </span>
          )}
        </div>
        <div
          className="dim"
          style={{ fontSize: "0.65625rem", display: "flex", gap: "0.5rem" }}
        >
          {tag.size_bytes > 0 && <span>{formatBytes(tag.size_bytes)}</span>}
          {tag.last_updated && (
            <>
              <span>·</span>
              <span>{formatRelativeDate(tag.last_updated)}</span>
            </>
          )}
        </div>
      </div>
      <div className="flex items-center" style={{ gap: "0.375rem" }}>
        {installed && !active && (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              onSetActive(image);
            }}
            title={t("languageTool.makeActiveCheckTitle")}
          >
            <Star size="0.6875rem" />
            {t("languageTool.activate")}
          </button>
        )}
        {!installed && (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              onInstall(image);
            }}
          >
            <Download size="0.6875rem" />
            {t("languageTool.install")}
          </button>
        )}
      </div>
    </div>
  );
};

const RepoBlock = ({
  repo,
  activeImage,
  installedTags,
  onInstall,
  onSetActive,
}: {
  repo: string;
  activeImage: string;
  installedTags: Set<string>;
  onInstall: (image: string) => void;
  onSetActive: (image: string) => void;
}) => {
  const { t } = useTranslation("settings");
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [query, setQuery] = useState("");

  // Defer the Docker Hub call until the user opens the repo block.
  const remoteTags = useLanguageToolRemoteTags(expanded ? repo : null);

  const tags = useMemo(() => remoteTags.data?.tags ?? [], [remoteTags.data]);
  const trimmed = query.trim().toLowerCase();
  const filteredTags = useMemo(
    () =>
      trimmed.length === 0
        ? tags
        : tags.filter((t) => t.name.toLowerCase().includes(trimmed)),
    [tags, trimmed],
  );
  const isSearching = trimmed.length > 0;
  const visibleTags =
    showAll || isSearching ? filteredTags : filteredTags.slice(0, 20);

  return (
    <div
      className="flex flex-col"
      style={{
        gap: "0.375rem",
        padding: "0.625rem",
        borderRadius: "0.375rem",
        border: "1px solid var(--border)",
      }}
    >
      <button
        type="button"
        className="flex items-center justify-between"
        style={{
          gap: "0.5rem",
          background: "transparent",
          border: "none",
          padding: 0,
          cursor: "pointer",
          color: "inherit",
        }}
        onClick={() => {
          setExpanded((v) => !v);
        }}
      >
        <span
          className="flex items-center"
          style={{ gap: "0.5rem", fontSize: "0.75rem", fontWeight: 600 }}
        >
          <Cloud size="0.8125rem" style={{ color: "var(--fg-2)" }} />
          <span className="mono">{repo}</span>
        </span>
        <span className="dim" style={{ fontSize: "0.6875rem" }}>
          {expanded ? t("languageTool.hideTags") : t("languageTool.showTags")}
        </span>
      </button>

      {expanded && (
        <>
          {remoteTags.isLoading && (
            <div
              className="flex items-center"
              style={{
                gap: "0.5rem",
                fontSize: "0.71875rem",
                padding: "0.5rem",
              }}
            >
              <Spinner size="sm" />
              <span className="dim">{t("languageTool.fetchingTags")}</span>
            </div>
          )}
          {remoteTags.isError && (
            <div
              className="dim"
              style={{
                fontSize: "0.71875rem",
                padding: "0.5rem",
                color: "var(--c-warn)",
              }}
            >
              {t("languageTool.fetchTagsError")}
            </div>
          )}
          {!remoteTags.isLoading && tags.length > 0 && (
            <div
              className="flex items-center"
              style={{
                gap: "0.375rem",
                padding: "0.25rem 0.5rem",
                borderRadius: "0.25rem",
                border: "1px solid var(--border)",
                background: "var(--bg-0)",
              }}
            >
              <Search size="0.6875rem" style={{ color: "var(--fg-3)" }} />
              <input
                type="search"
                value={query}
                placeholder={t("languageTool.tagSearchPlaceholder")}
                onChange={(e) => {
                  setQuery(e.target.value);
                }}
                style={{
                  flex: 1,
                  background: "transparent",
                  border: "none",
                  outline: "none",
                  color: "var(--fg-0)",
                  fontSize: "0.71875rem",
                  fontFamily: "var(--font-mono)",
                }}
              />
              {isSearching && (
                <span className="dim" style={{ fontSize: "0.65625rem" }}>
                  {filteredTags.length}/{tags.length}
                </span>
              )}
            </div>
          )}
          {!remoteTags.isLoading &&
            tags.length === 0 &&
            !remoteTags.isError && (
              <div
                className="dim"
                style={{ fontSize: "0.71875rem", padding: "0.5rem" }}
              >
                {t("languageTool.noTags")}
              </div>
            )}
          {!remoteTags.isLoading &&
            tags.length > 0 &&
            filteredTags.length === 0 && (
              <div
                className="dim"
                style={{ fontSize: "0.71875rem", padding: "0.5rem" }}
              >
                {t("languageTool.noMatch", { query })}
              </div>
            )}
          {visibleTags.length > 0 && (
            <div className="flex flex-col" style={{ gap: "0.125rem" }}>
              {visibleTags.map((tag) => {
                const image = `${repo}:${tag.name}`;
                return (
                  <RemoteRow
                    key={tag.name}
                    repo={repo}
                    tag={tag}
                    installed={installedTags.has(image)}
                    active={image === activeImage}
                    onInstall={onInstall}
                    onSetActive={onSetActive}
                  />
                );
              })}
            </div>
          )}
          {!isSearching && filteredTags.length > visibleTags.length && (
            <button
              type="button"
              className="btn xs"
              style={{ alignSelf: "center" }}
              onClick={() => {
                setShowAll(true);
              }}
            >
              {t("languageTool.showMore", {
                count: filteredTags.length - visibleTags.length,
              })}
            </button>
          )}
        </>
      )}
    </div>
  );
};

const RuntimePill = ({ status }: { status: LanguageToolStatus }) => {
  const { t } = useTranslation("settings");
  if (status.healthy) {
    const port = /:(\d+)$/.exec(status.base_url ?? "")?.[1] ?? null;
    return (
      <span style={{ fontSize: "0.6875rem", color: "var(--c-ok)" }}>
        {t("languageTool.running", { port: port ? ` (:${port})` : "" })}
      </span>
    );
  }
  if (status.container_running) {
    return (
      <span style={{ fontSize: "0.6875rem", color: "var(--c-info)" }}>
        {t("languageTool.starting")}
      </span>
    );
  }
  return (
    <span className="dim" style={{ fontSize: "0.6875rem" }}>
      {t("languageTool.willStartAutomatically")}
    </span>
  );
};

export const LanguageToolImagesSection = () => {
  const { t } = useTranslation("settings");
  const status = useLanguageToolStatus();
  const imagesList = useLanguageToolImages();
  const setActive = useSetActiveLanguageToolImage();
  const removeImage = useRemoveLanguageToolImage();
  const [installing, setInstalling] = useState<string | null>(null);

  const installedSet = useMemo(
    () => new Set(imagesList.data?.installed.map((i) => i.image) ?? []),
    [imagesList.data],
  );
  const activeImage = imagesList.data?.active_image ?? "";

  const handleSetActive = (image: string) => {
    setActive.mutate(image, {
      onSuccess: () => {
        toast.success(t("languageTool.activeToast", { image }));
      },
    });
  };

  const handleRemove = (image: string) => {
    if (!window.confirm(t("languageTool.removeConfirm", { image }))) return;
    removeImage.mutate(image, {
      onSuccess: () => {
        toast.success(t("languageTool.removedToast", { image }));
      },
    });
  };

  const renderDocker = () => {
    if (status.isLoading) {
      return (
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", fontSize: "0.75rem" }}
        >
          <Spinner size="sm" />
          <span className="dim">{t("languageTool.checkingDocker")}</span>
        </div>
      );
    }
    const data = status.data;
    if (!data?.docker_available) {
      return (
        <DockerUnavailableNotice
          status={
            data
              ? {
                  available: data.docker_available,
                  version: null,
                  detail: data.docker_detail,
                  reason: data.docker_reason,
                  socket_gid: data.docker_socket_gid,
                }
              : undefined
          }
          fallbackDetail={t("languageTool.dockerUnavailableDetail")}
        />
      );
    }
    return (
      <div
        className="flex items-center"
        style={{ gap: "0.5rem", fontSize: "0.75rem" }}
      >
        <CheckCircle2 size="0.8125rem" style={{ color: "var(--c-ok)" }} />
        <span>{t("languageTool.dockerConnected")}</span>
      </div>
    );
  };

  const renderActive = () => {
    if (!activeImage) return null;
    const isInstalled = installedSet.has(activeImage);
    return (
      <div
        className="flex flex-col"
        style={{
          gap: "0.375rem",
          padding: "0.75rem",
          borderRadius: "0.375rem",
          border: "1px solid var(--accent)",
          background: "var(--bg-1)",
        }}
      >
        <div
          className="flex items-center justify-between"
          style={{ gap: "0.5rem" }}
        >
          <div
            className="dim"
            style={{
              fontSize: "0.625rem",
              textTransform: "uppercase",
              letterSpacing: "0.03125rem",
            }}
          >
            {t("languageTool.activeImage")}
          </div>
          {isInstalled && status.data && <RuntimePill status={status.data} />}
        </div>
        <div className="flex items-center" style={{ gap: "0.5rem" }}>
          <Star
            size="0.875rem"
            style={{ color: "var(--accent)", fill: "var(--accent)" }}
          />
          <span
            className="mono"
            style={{ fontSize: "0.8125rem", fontWeight: 500 }}
          >
            {activeImage}
          </span>
          {!isInstalled && (
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                setInstalling(activeImage);
              }}
            >
              <Download size="0.6875rem" />
              {t("languageTool.install")}
            </button>
          )}
        </div>
        {!isInstalled && (
          <div
            className="dim"
            style={{
              fontSize: "0.6875rem",
              display: "flex",
              alignItems: "center",
              gap: "0.375rem",
              color: "var(--c-warn)",
            }}
          >
            <XCircle size="0.75rem" />
            {t("languageTool.activeImageNotInstalled")}
          </div>
        )}
      </div>
    );
  };

  const renderInstalled = () => {
    if (imagesList.isLoading) {
      return (
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", fontSize: "0.75rem" }}
        >
          <Spinner size="sm" />
          <span className="dim">{t("languageTool.loadingInstalled")}</span>
        </div>
      );
    }
    const installed = imagesList.data?.installed ?? [];
    if (installed.length === 0) {
      return (
        <div className="dim" style={{ fontSize: "0.75rem" }}>
          {t("languageTool.noInstalled")}
        </div>
      );
    }
    return (
      <div className="flex flex-col" style={{ gap: "0.375rem" }}>
        <div
          className="dim"
          style={{
            fontSize: "0.625rem",
            textTransform: "uppercase",
            letterSpacing: "0.03125rem",
          }}
        >
          {t("languageTool.installedLocally")}
        </div>
        {installed.map((entry) => (
          <InstalledRow
            key={entry.image}
            entry={entry}
            active={entry.image === activeImage}
            onSetActive={handleSetActive}
            onRemove={handleRemove}
            onUpdate={(image) => {
              setInstalling(image);
            }}
            pending={setActive.isPending || removeImage.isPending}
          />
        ))}
      </div>
    );
  };

  const renderRepos = () => {
    const repos = imagesList.data?.allowed_repos ?? [];
    if (repos.length === 0) return null;
    return (
      <div className="flex flex-col" style={{ gap: "0.375rem" }}>
        <div
          className="dim"
          style={{
            fontSize: "0.625rem",
            textTransform: "uppercase",
            letterSpacing: "0.03125rem",
          }}
        >
          {t("languageTool.availableFromHub")}
        </div>
        {repos.map((repo) => (
          <RepoBlock
            key={repo}
            repo={repo}
            activeImage={activeImage}
            installedTags={installedSet}
            onInstall={(image) => {
              setInstalling(image);
            }}
            onSetActive={handleSetActive}
          />
        ))}
      </div>
    );
  };

  return (
    <>
      <SettingHead
        anchorId="checks-languagetool"
        title={t("languageTool.title")}
        sub={t("languageTool.subtitle")}
      />
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem", paddingBottom: "0.875rem" }}
      >
        {renderDocker()}
        {renderActive()}
        {renderInstalled()}
        {renderRepos()}
      </div>
      <InstallLanguageToolModal
        image={installing}
        onClose={() => {
          setInstalling(null);
        }}
      />
    </>
  );
};
