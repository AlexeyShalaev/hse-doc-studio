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
  DockerUnavailableNotice,
  useDockerStatus,
  useImagesList,
  useRemoteTags,
  useRemoveImage,
  useSetActiveImage,
  type LocalImage,
  type RemoteTag,
} from "@entities/compile-images";
import { i18n, toast } from "@shared/lib";
import { InstallImageModal } from "@features/install-image";
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
  if (days < 1) return i18n.t("settings:images.today");
  if (days < 30) return i18n.t("settings:images.daysAgo", { count: days });
  const months = Math.floor(days / 30);
  if (months < 12)
    return i18n.t("settings:images.monthsAgo", { count: months });
  const years = Math.floor(months / 12);
  return i18n.t("settings:images.yearsAgo", { count: years });
};

const InstalledRow = ({
  entry,
  active,
  onSetActive,
  onRemove,
  onUpdate,
  pending,
}: {
  entry: LocalImage;
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
              {t("images.activeBadge")}
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
            title={t("images.makeActiveBuildTitle")}
          >
            <Star size="0.6875rem" />
            {t("images.makeActive")}
          </button>
        )}
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            onUpdate(entry.image);
          }}
          disabled={pending}
          title={t("images.updateTitle")}
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
              ? t("images.removeActiveDisabledTitle")
              : t("images.removeLocalTitle")
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
  tag: RemoteTag;
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
              {t("images.activeStar")}
            </span>
          )}
          {installed && !active && (
            <span
              className="mono"
              style={{ fontSize: "0.625rem", color: "var(--c-ok)" }}
            >
              {t("images.installedBadge")}
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
            title={t("images.makeActiveBuildTitle")}
          >
            <Star size="0.6875rem" />
            {t("images.activate")}
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
            {t("images.install")}
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

  // Defer the Docker Hub call until the user opens the repo block — saves
  // a 100-tag fetch on every Settings open.
  const remoteTags = useRemoteTags(expanded ? repo : null);

  // Own useMemo so the `?? []` fallback keeps a stable identity across renders
  // and does not invalidate the filteredTags memo below on every render.
  const tags = useMemo(() => remoteTags.data?.tags ?? [], [remoteTags.data]);
  const trimmed = query.trim().toLowerCase();
  const filteredTags = useMemo(
    () =>
      trimmed.length === 0
        ? tags
        : tags.filter((t) => t.name.toLowerCase().includes(trimmed)),
    [tags, trimmed],
  );
  // Skip the "first 20" truncation when actively searching — a search match
  // should always be visible, even if it's the 87th tag chronologically.
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
          {expanded ? t("images.hideTags") : t("images.showTags")}
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
              <span className="dim">{t("images.fetchingTags")}</span>
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
              {t("images.fetchTagsError")}
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
                placeholder={t("images.tagSearchPlaceholder")}
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
                {t("images.noTags")}
              </div>
            )}
          {!remoteTags.isLoading &&
            tags.length > 0 &&
            filteredTags.length === 0 && (
              <div
                className="dim"
                style={{ fontSize: "0.71875rem", padding: "0.5rem" }}
              >
                {t("images.noMatch", { query })}
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
              {t("images.showMore", {
                count: filteredTags.length - visibleTags.length,
              })}
            </button>
          )}
        </>
      )}
    </div>
  );
};

export const ImagesSection = () => {
  const { t } = useTranslation("settings");
  const dockerStatus = useDockerStatus();
  const imagesList = useImagesList();
  const setActive = useSetActiveImage();
  const removeImage = useRemoveImage();
  const [installing, setInstalling] = useState<string | null>(null);

  const installedSet = useMemo(
    () => new Set(imagesList.data?.installed.map((i) => i.image) ?? []),
    [imagesList.data],
  );
  const activeImage = imagesList.data?.active_image ?? "";

  const handleSetActive = (image: string) => {
    setActive.mutate(image, {
      onSuccess: () => {
        toast.success(t("images.activeToast", { image }));
      },
    });
  };

  const handleRemove = (image: string) => {
    if (!window.confirm(t("images.removeConfirm", { image }))) return;
    removeImage.mutate(image, {
      onSuccess: () => {
        toast.success(t("images.removedToast", { image }));
      },
    });
  };

  const renderDocker = () => {
    if (dockerStatus.isLoading) {
      return (
        <div
          className="flex items-center"
          style={{ gap: "0.5rem", fontSize: "0.75rem" }}
        >
          <Spinner size="sm" />
          <span className="dim">{t("images.checkingDocker")}</span>
        </div>
      );
    }
    const data = dockerStatus.data;
    if (!data?.available) {
      return (
        <DockerUnavailableNotice
          status={data}
          fallbackDetail={t("images.dockerUnavailableDetail")}
        />
      );
    }
    return (
      <div
        className="flex items-center"
        style={{ gap: "0.5rem", fontSize: "0.75rem" }}
      >
        <CheckCircle2 size="0.8125rem" style={{ color: "var(--c-ok)" }} />
        <span>{t("images.dockerConnected")}</span>
        {data.version && (
          <span className="mono dim" style={{ fontSize: "0.6875rem" }}>
            {data.version}
          </span>
        )}
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
          className="dim"
          style={{
            fontSize: "0.625rem",
            textTransform: "uppercase",
            letterSpacing: "0.03125rem",
          }}
        >
          {t("images.activeImage")}
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
              {t("images.install")}
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
            {t("images.activeImageNotInstalled")}
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
          <span className="dim">{t("images.loadingInstalled")}</span>
        </div>
      );
    }
    const installed = imagesList.data?.installed ?? [];
    if (installed.length === 0) {
      return (
        <div className="dim" style={{ fontSize: "0.75rem" }}>
          {t("images.noInstalled")}
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
          {t("images.installedLocally")}
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
          {t("images.availableFromHub")}
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
        anchorId="compiler-images"
        title={t("images.title")}
        sub={t("images.subtitle")}
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
      <InstallImageModal
        image={installing}
        onClose={() => {
          setInstalling(null);
        }}
      />
    </>
  );
};
