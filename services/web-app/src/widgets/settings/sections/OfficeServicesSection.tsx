import { useMemo, useState } from "react";
import {
  CheckCircle2,
  Cloud,
  Download,
  FileText,
  Presentation,
  RefreshCw,
  Search,
  Star,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui/Spinner";
import {
  officeImageRef,
  officeImageRepo,
  useOfficeServiceImages,
  useOfficeServiceRemoteTags,
  useOfficeServicesStatus,
  useSetActiveOfficeServiceImage,
  type OfficeServiceId,
  type OfficeServiceImage,
  type OfficeServiceRemoteTag,
  type OfficeServiceStatus,
} from "@entities/office-services";
import { i18n, toast } from "@shared/lib";
import {
  InstallOfficeImageModal,
  type InstallOfficeImageTarget,
} from "@features/install-office-image";
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
  if (days < 1) return i18n.t("settings:officeServices.today");
  if (days < 30)
    return i18n.t("settings:officeServices.daysAgo", { count: days });
  const months = Math.floor(days / 30);
  if (months < 12)
    return i18n.t("settings:officeServices.monthsAgo", { count: months });
  const years = Math.floor(months / 12);
  return i18n.t("settings:officeServices.yearsAgo", { count: years });
};

const InstalledRow = ({
  entry,
  image,
  onSetActive,
  onUpdate,
  pending,
}: {
  entry: OfficeServiceImage;
  image: string;
  onSetActive: (image: string) => void;
  onUpdate: (image: string) => void;
  pending: boolean;
}) => {
  const { t } = useTranslation("settings");
  const active = entry.active;
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
            {image}
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
              {t("officeServices.activeBadge")}
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
          <span>{formatBytes(entry.size)}</span>
          {entry.created && (
            <>
              <span>·</span>
              <span>{formatRelativeDate(entry.created)}</span>
            </>
          )}
        </div>
      </div>
      <div className="flex items-center" style={{ gap: 6 }}>
        {!active && (
          <button
            type="button"
            className="btn xs"
            onClick={() => {
              onSetActive(image);
            }}
            disabled={pending}
            title={t("officeServices.makeActiveTitle")}
          >
            <Star size={11} />
            {t("officeServices.makeActive")}
          </button>
        )}
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            onUpdate(image);
          }}
          disabled={pending}
          title={t("officeServices.updateTitle")}
        >
          <RefreshCw size={11} />
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
  tag: OfficeServiceRemoteTag;
  installed: boolean;
  active: boolean;
  onInstall: (image: string) => void;
  onSetActive: (image: string) => void;
}) => {
  const { t } = useTranslation("settings");
  const image = officeImageRef(repo, tag.name);
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
              {t("officeServices.activeStar")}
            </span>
          )}
          {installed && !active && (
            <span
              className="mono"
              style={{ fontSize: 10, color: "var(--c-ok)" }}
            >
              {t("officeServices.installedBadge")}
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
            title={t("officeServices.makeActiveTitle")}
          >
            <Star size={11} />
            {t("officeServices.activate")}
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
            {t("officeServices.install")}
          </button>
        )}
      </div>
    </div>
  );
};

const RemoteTagsBlock = ({
  service,
  repo,
  activeImage,
  installedRefs,
  onInstall,
  onSetActive,
}: {
  service: OfficeServiceId;
  repo: string;
  activeImage: string;
  installedRefs: Set<string>;
  onInstall: (image: string) => void;
  onSetActive: (image: string) => void;
}) => {
  const { t } = useTranslation("settings");
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [query, setQuery] = useState("");

  // Defer the Docker Hub call until the user opens the block.
  const remoteTags = useOfficeServiceRemoteTags(expanded ? service : null);

  const tags = useMemo(() => remoteTags.data?.tags ?? [], [remoteTags.data]);
  const trimmed = query.trim().toLowerCase();
  const filteredTags = useMemo(
    () =>
      trimmed.length === 0
        ? tags
        : tags.filter((tag) => tag.name.toLowerCase().includes(trimmed)),
    [tags, trimmed],
  );
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
          {expanded
            ? t("officeServices.hideTags")
            : t("officeServices.showTags")}
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
              <span className="dim">{t("officeServices.fetchingTags")}</span>
            </div>
          )}
          {remoteTags.isError && (
            <div
              className="dim"
              style={{ fontSize: 11.5, padding: 8, color: "var(--c-warn)" }}
            >
              {t("officeServices.fetchTagsError")}
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
                placeholder={t("officeServices.tagSearchPlaceholder")}
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
                {t("officeServices.noTags")}
              </div>
            )}
          {!remoteTags.isLoading &&
            tags.length > 0 &&
            filteredTags.length === 0 && (
              <div className="dim" style={{ fontSize: 11.5, padding: 8 }}>
                {t("officeServices.noMatch", { query })}
              </div>
            )}
          {visibleTags.length > 0 && (
            <div className="flex flex-col" style={{ gap: 2 }}>
              {visibleTags.map((tag) => {
                const image = officeImageRef(repo, tag.name);
                return (
                  <RemoteRow
                    key={tag.name}
                    repo={repo}
                    tag={tag}
                    installed={installedRefs.has(image)}
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
              {t("officeServices.showMore", {
                count: filteredTags.length - visibleTags.length,
              })}
            </button>
          )}
        </>
      )}
    </div>
  );
};

const ContainerPill = ({ status }: { status: OfficeServiceStatus }) => {
  const { t } = useTranslation("settings");
  if (status.container.running) {
    return (
      <span style={{ fontSize: 11, color: "var(--c-ok)" }}>
        {t("officeServices.containerRunning")}
      </span>
    );
  }
  if (status.container.present) {
    return (
      <span
        className="dim"
        style={{ fontSize: 11 }}
        title={status.container.status_text ?? undefined}
      >
        {t("officeServices.containerStopped")}
      </span>
    );
  }
  return (
    <span className="dim" style={{ fontSize: 11 }}>
      {t("officeServices.containerAbsent")}
    </span>
  );
};

const ServiceCard = ({
  service,
  anchorId,
  icon: Icon,
  status,
  statusLoading,
  statusError,
  onInstall,
}: {
  service: OfficeServiceId;
  anchorId: string;
  icon: LucideIcon;
  status: OfficeServiceStatus | undefined;
  statusLoading: boolean;
  statusError: boolean;
  onInstall: (target: InstallOfficeImageTarget) => void;
}) => {
  const { t } = useTranslation("settings");
  const imagesList = useOfficeServiceImages(service);
  const setActive = useSetActiveOfficeServiceImage(service);

  const activeImage = status?.active_image ?? "";
  const repo = activeImage
    ? officeImageRepo(activeImage)
    : (status?.label_hint ?? "");

  const installedRefs = useMemo(
    () =>
      new Set(
        (imagesList.data?.images ?? [])
          .filter((entry) => entry.installed)
          .map((entry) => officeImageRef(repo, entry.tag)),
      ),
    [imagesList.data, repo],
  );
  const activeInstalled =
    status?.image_installed ?? installedRefs.has(activeImage);

  const handleSetActive = (image: string) => {
    setActive.mutate(image, {
      onSuccess: () => {
        toast.success(t("officeServices.activeToast", { image }));
      },
    });
  };

  const renderStatus = () => {
    if (statusLoading) {
      return (
        <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
          <Spinner size="sm" />
          <span className="dim">{t("officeServices.statusLoading")}</span>
        </div>
      );
    }
    if (statusError || !status) {
      return (
        <div className="dim" style={{ fontSize: 12, color: "var(--c-warn)" }}>
          {t("officeServices.statusError")}
        </div>
      );
    }
    return (
      <div
        className="flex flex-col"
        style={{
          gap: 6,
          padding: 12,
          borderRadius: 6,
          border: activeInstalled
            ? "1px solid var(--accent)"
            : "1px solid var(--border)",
          background: "var(--bg-1)",
        }}
      >
        <div className="flex items-center justify-between" style={{ gap: 8 }}>
          <div
            className="dim"
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: 0.5,
            }}
          >
            {t("officeServices.activeImage")}
          </div>
          <ContainerPill status={status} />
        </div>
        <div className="flex items-center" style={{ gap: 8 }}>
          <Star
            size={14}
            style={{ color: "var(--accent)", fill: "var(--accent)" }}
          />
          <span className="mono" style={{ fontSize: 13, fontWeight: 500 }}>
            {activeImage || "—"}
          </span>
          {!activeInstalled && activeImage && (
            <button
              type="button"
              className="btn xs"
              onClick={() => {
                onInstall({ service, image: activeImage });
              }}
            >
              <Download size={11} />
              {t("officeServices.install")}
            </button>
          )}
        </div>
        {!activeInstalled && (
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
            {t(
              service === "convert"
                ? "officeServices.convertNotInstalled"
                : "officeServices.editorNotInstalled",
            )}
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
          <span className="dim">{t("officeServices.loadingInstalled")}</span>
        </div>
      );
    }
    const installed = (imagesList.data?.images ?? []).filter(
      (entry) => entry.installed,
    );
    if (installed.length === 0) {
      return (
        <div className="dim" style={{ fontSize: 12 }}>
          {t("officeServices.noInstalled")}
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
          {t("officeServices.installedLocally")}
        </div>
        {installed.map((entry) => (
          <InstalledRow
            key={entry.tag}
            entry={entry}
            image={officeImageRef(repo, entry.tag)}
            onSetActive={handleSetActive}
            onUpdate={(image) => {
              onInstall({ service, image });
            }}
            pending={setActive.isPending}
          />
        ))}
      </div>
    );
  };

  return (
    <div
      id={anchorId}
      className="settings-anchor flex flex-col"
      style={{
        gap: 10,
        padding: 12,
        borderRadius: 8,
        border: "1px solid var(--border)",
        marginBottom: 14,
      }}
    >
      <div className="flex flex-col" style={{ gap: 2 }}>
        <div className="flex items-center" style={{ gap: 8 }}>
          <Icon size={14} style={{ color: "var(--accent)" }} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            {t(
              service === "convert"
                ? "officeServices.convertTitle"
                : "officeServices.editorTitle",
            )}
          </span>
        </div>
        <span className="dim" style={{ fontSize: 11.5 }}>
          {t(
            service === "convert"
              ? "officeServices.convertSub"
              : "officeServices.editorSub",
          )}
        </span>
      </div>

      {renderStatus()}
      {renderInstalled()}
      {repo && (
        <RemoteTagsBlock
          service={service}
          repo={repo}
          activeImage={activeImage}
          installedRefs={installedRefs}
          onInstall={(image) => {
            onInstall({ service, image });
          }}
          onSetActive={handleSetActive}
        />
      )}
    </div>
  );
};

export const OfficeServicesSection = () => {
  const { t } = useTranslation("settings");
  const status = useOfficeServicesStatus();
  const [installing, setInstalling] = useState<InstallOfficeImageTarget | null>(
    null,
  );

  const serviceStatus = (id: OfficeServiceId) =>
    status.data?.services.find((s) => s.service === id);

  return (
    <>
      <SettingHead
        anchorId="presentations"
        title={t("officeServices.title")}
        sub={t("officeServices.subtitle")}
      />
      <ServiceCard
        service="convert"
        anchorId="presentations-convert"
        icon={FileText}
        status={serviceStatus("convert")}
        statusLoading={status.isLoading}
        statusError={status.isError}
        onInstall={setInstalling}
      />
      <ServiceCard
        service="editor"
        anchorId="presentations-editor"
        icon={Presentation}
        status={serviceStatus("editor")}
        statusLoading={status.isLoading}
        statusError={status.isError}
        onInstall={setInstalling}
      />
      <InstallOfficeImageModal
        target={installing}
        onClose={() => {
          setInstalling(null);
        }}
      />
    </>
  );
};
