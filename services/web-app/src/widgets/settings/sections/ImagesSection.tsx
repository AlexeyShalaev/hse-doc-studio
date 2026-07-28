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
        gap: 12,
        padding: "10px 12px",
        borderRadius: 6,
        border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
        background: active ? "var(--accent-soft, var(--bg-1))" : "var(--bg-1)",
      }}
    >
      <div className="flex flex-col" style={{ gap: 4, minWidth: 0 }}>
        <div className="flex items-center" style={{ gap: 8 }}>
          {active ? (
            <Star
              size={13}
              style={{ color: "var(--accent)", fill: "var(--accent)" }}
            />
          ) : (
            <CheckCircle2 size={13} style={{ color: "var(--c-ok)" }} />
          )}
          <span className="mono" style={{ fontSize: 12, fontWeight: 500 }}>
            {entry.image}
          </span>
          {active && (
            <span
              className="mono"
              style={{
                fontSize: 10,
                padding: "1px 6px",
                borderRadius: 3,
                background: "var(--accent)",
                color: "var(--bg-0)",
                textTransform: "uppercase",
                letterSpacing: 0.5,
              }}
            >
              {t("images.activeBadge")}
            </span>
          )}
        </div>
        <div
          className="dim"
          style={{
            fontSize: 11,
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <span>{formatBytes(entry.size_bytes)}</span>
          <span>·</span>
          <span className="mono" style={{ fontSize: 10 }}>
            {entry.id.slice(7, 19)}
          </span>
        </div>
      </div>
      <div className="flex items-center" style={{ gap: 6 }}>
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
            <Star size={11} />
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
          <RefreshCw size={11} />
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
          <Trash2 size={11} />
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
        gap: 12,
        padding: "8px 12px",
        borderRadius: 6,
        background: installed ? "var(--bg-1)" : "transparent",
        border: "1px solid transparent",
      }}
    >
      <div className="flex flex-col" style={{ gap: 2, minWidth: 0 }}>
        <div className="flex items-center" style={{ gap: 8 }}>
          <span className="mono" style={{ fontSize: 12 }}>
            {tag.name}
          </span>
          {active && (
            <span
              className="mono"
              style={{ fontSize: 10, color: "var(--accent)" }}
            >
              {t("images.activeStar")}
            </span>
          )}
          {installed && !active && (
            <span
              className="mono"
              style={{ fontSize: 10, color: "var(--c-ok)" }}
            >
              {t("images.installedBadge")}
            </span>
          )}
        </div>
        <div
          className="dim"
          style={{ fontSize: 10.5, display: "flex", gap: 8 }}
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
      <div className="flex items-center" style={{ gap: 6 }}>
        {installed && !active && (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              onSetActive(image);
            }}
            title={t("images.makeActiveBuildTitle")}
          >
            <Star size={11} />
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
            <Download size={11} />
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
        gap: 6,
        padding: 10,
        borderRadius: 6,
        border: "1px solid var(--border)",
      }}
    >
      <button
        type="button"
        className="flex items-center justify-between"
        style={{
          gap: 8,
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
          style={{ gap: 8, fontSize: 12, fontWeight: 600 }}
        >
          <Cloud size={13} style={{ color: "var(--fg-2)" }} />
          <span className="mono">{repo}</span>
        </span>
        <span className="dim" style={{ fontSize: 11 }}>
          {expanded ? t("images.hideTags") : t("images.showTags")}
        </span>
      </button>

      {expanded && (
        <>
          {remoteTags.isLoading && (
            <div
              className="flex items-center"
              style={{ gap: 8, fontSize: 11.5, padding: 8 }}
            >
              <Spinner size="sm" />
              <span className="dim">{t("images.fetchingTags")}</span>
            </div>
          )}
          {remoteTags.isError && (
            <div
              className="dim"
              style={{ fontSize: 11.5, padding: 8, color: "var(--c-warn)" }}
            >
              {t("images.fetchTagsError")}
            </div>
          )}
          {!remoteTags.isLoading && tags.length > 0 && (
            <div
              className="flex items-center"
              style={{
                gap: 6,
                padding: "4px 8px",
                borderRadius: 4,
                border: "1px solid var(--border)",
                background: "var(--bg-0)",
              }}
            >
              <Search size={11} style={{ color: "var(--fg-3)" }} />
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
                  fontSize: 11.5,
                  fontFamily: "var(--font-mono)",
                }}
              />
              {isSearching && (
                <span className="dim" style={{ fontSize: 10.5 }}>
                  {filteredTags.length}/{tags.length}
                </span>
              )}
            </div>
          )}
          {!remoteTags.isLoading &&
            tags.length === 0 &&
            !remoteTags.isError && (
              <div className="dim" style={{ fontSize: 11.5, padding: 8 }}>
                {t("images.noTags")}
              </div>
            )}
          {!remoteTags.isLoading &&
            tags.length > 0 &&
            filteredTags.length === 0 && (
              <div className="dim" style={{ fontSize: 11.5, padding: 8 }}>
                {t("images.noMatch", { query })}
              </div>
            )}
          {visibleTags.length > 0 && (
            <div className="flex flex-col" style={{ gap: 2 }}>
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
        <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          <span className="dim">{t("images.checkingDocker")}</span>
        </div>
      );
    }
    const data = dockerStatus.data;
    if (!data || !data.available) {
      return (
        <DockerUnavailableNotice
          status={data}
          fallbackDetail={t("images.dockerUnavailableDetail")}
        />
      );
    }
    return (
      <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
        <CheckCircle2 size={13} style={{ color: "var(--c-ok)" }} />
        <span>{t("images.dockerConnected")}</span>
        {data.version && (
          <span className="mono dim" style={{ fontSize: 11 }}>
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
          gap: 6,
          padding: 12,
          borderRadius: 6,
          border: "1px solid var(--accent)",
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
          {t("images.activeImage")}
        </div>
        <div className="flex items-center" style={{ gap: 8 }}>
          <Star
            size={14}
            style={{ color: "var(--accent)", fill: "var(--accent)" }}
          />
          <span className="mono" style={{ fontSize: 13, fontWeight: 500 }}>
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
              <Download size={11} />
              {t("images.install")}
            </button>
          )}
        </div>
        {!isInstalled && (
          <div
            className="dim"
            style={{
              fontSize: 11,
              display: "flex",
              alignItems: "center",
              gap: 6,
              color: "var(--c-warn)",
            }}
          >
            <XCircle size={12} />
            {t("images.activeImageNotInstalled")}
          </div>
        )}
      </div>
    );
  };

  const renderInstalled = () => {
    if (imagesList.isLoading) {
      return (
        <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          <span className="dim">{t("images.loadingInstalled")}</span>
        </div>
      );
    }
    const installed = imagesList.data?.installed ?? [];
    if (installed.length === 0) {
      return (
        <div className="dim" style={{ fontSize: 12 }}>
          {t("images.noInstalled")}
        </div>
      );
    }
    return (
      <div className="flex flex-col" style={{ gap: 6 }}>
        <div
          className="dim"
          style={{
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: 0.5,
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
      <div className="flex flex-col" style={{ gap: 6 }}>
        <div
          className="dim"
          style={{
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: 0.5,
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
      <div className="flex flex-col" style={{ gap: 12, paddingBottom: 14 }}>
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
