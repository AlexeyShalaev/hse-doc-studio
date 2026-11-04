import { useMemo, useState } from "react";
import {
  Box,
  ChevronDown,
  ChevronRight,
  Database,
  Layers,
  Lock,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { formatBytes } from "@shared/lib";
import type {
  DockerContainerUsage,
  DockerImageUsage,
  DockerUsage,
} from "@entities/docker-system";
import { categoryColor, categoryLabelKey } from "./lib";

const Badge = ({
  text,
  tone,
}: {
  text: string;
  tone: "ok" | "accent" | "warn" | "dim";
}) => {
  const color =
    tone === "ok"
      ? "var(--c-ok)"
      : tone === "accent"
        ? "var(--accent)"
        : tone === "warn"
          ? "var(--c-warn)"
          : "var(--fg-2)";
  return (
    <span
      style={{
        flexShrink: 0,
        fontSize: "0.59375rem",
        padding: "1px 0.375rem",
        borderRadius: "999px",
        border: `1px solid ${color}`,
        color,
        textTransform: "uppercase",
        letterSpacing: "0.025rem",
        whiteSpace: "nowrap",
      }}
    >
      {text}
    </span>
  );
};

const Group = ({
  icon,
  title,
  count,
  sizeBytes,
  defaultOpen = false,
  children,
  footer,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  sizeBytes: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div
      className="flex flex-col"
      style={{
        borderRadius: "var(--r-3)",
        border: "1px solid var(--border)",
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        className="flex items-center justify-between"
        style={{
          gap: "0.5rem",
          padding: "0.625rem 0.75rem",
          background: "var(--bg-1)",
          border: "none",
          cursor: "pointer",
          color: "inherit",
          textAlign: "left",
        }}
        onClick={() => {
          setOpen((v) => !v);
        }}
      >
        <span
          className="flex items-center"
          style={{ gap: "0.5rem", minWidth: 0 }}
        >
          {open ? (
            <ChevronDown size="0.8125rem" />
          ) : (
            <ChevronRight size="0.8125rem" />
          )}
          <span style={{ color: "var(--fg-2)", display: "flex" }}>{icon}</span>
          <span style={{ fontSize: "0.78125rem", fontWeight: 600 }}>
            {title}
          </span>
          <span className="dim" style={{ fontSize: "0.6875rem" }}>
            {count}
          </span>
        </span>
        <span
          className="mono dim"
          style={{ fontSize: "0.6875rem", flexShrink: 0 }}
        >
          {formatBytes(sizeBytes)}
        </span>
      </button>
      {open && (
        <div
          className="flex flex-col"
          style={{ gap: "0.125rem", padding: "0.375rem 0.5rem 0.5rem" }}
        >
          {children}
          {footer}
        </div>
      )}
    </div>
  );
};

const Row = ({
  leading,
  primary,
  meta,
  badges,
  action,
}: {
  leading: React.ReactNode;
  primary: string;
  meta: string;
  badges?: React.ReactNode;
  action: React.ReactNode;
}) => (
  <div
    className="flex items-center"
    style={{
      gap: "0.5rem",
      padding: "0.3125rem 0.375rem",
      borderRadius: "0.375rem",
      minWidth: 0,
    }}
  >
    <span style={{ flexShrink: 0, display: "flex" }}>{leading}</span>
    <span className="flex flex-col" style={{ minWidth: 0, flex: 1, gap: 1 }}>
      <span
        className="flex items-center"
        style={{ gap: "0.375rem", minWidth: 0 }}
      >
        <span
          className="mono"
          style={{
            fontSize: "0.71875rem",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={primary}
        >
          {primary}
        </span>
        {badges}
      </span>
      <span className="dim" style={{ fontSize: "0.65625rem" }}>
        {meta}
      </span>
    </span>
    <span style={{ flexShrink: 0 }}>{action}</span>
  </div>
);

const LockHint = ({ title }: { title: string }) => (
  <span
    className="dim"
    title={title}
    style={{ display: "flex", padding: "0.25rem" }}
  >
    <Lock size="0.6875rem" />
  </span>
);

export type DiskEntityListsProps = {
  usage: DockerUsage;
  busy: boolean;
  onRemoveImage: (image: DockerImageUsage) => void;
  onRemoveDangling: () => void;
  onRemoveContainer: (container: DockerContainerUsage) => void;
};

export const DiskEntityLists = ({
  usage,
  busy,
  onRemoveImage,
  onRemoveDangling,
  onRemoveContainer,
}: DiskEntityListsProps) => {
  const { t } = useTranslation("settings");

  const images = useMemo(
    () => [...usage.images].sort((a, b) => b.size_bytes - a.size_bytes),
    [usage.images],
  );
  const containers = useMemo(
    () =>
      [...usage.containers].sort((a, b) => {
        if ((a.state === "running") !== (b.state === "running")) {
          return a.state === "running" ? -1 : 1;
        }
        return b.size_bytes - a.size_bytes;
      }),
    [usage.containers],
  );
  const volumes = useMemo(
    () => [...usage.volumes].sort((a, b) => b.size_bytes - a.size_bytes),
    [usage.volumes],
  );

  const imageAction = (image: DockerImageUsage) => {
    if (image.dangling) {
      return (
        <button
          type="button"
          className="btn xs"
          disabled={busy}
          title={t("disk.removeDanglingTitle")}
          onClick={onRemoveDangling}
        >
          <Trash2 size="0.6875rem" />
        </button>
      );
    }
    if (image.protected) {
      return (
        <LockHint
          title={
            image.in_use
              ? t("disk.imageInUseTitle")
              : t("disk.imageActiveTitle")
          }
        />
      );
    }
    return (
      <button
        type="button"
        className="btn xs"
        disabled={busy}
        title={t("disk.removeImageTitle")}
        onClick={() => {
          onRemoveImage(image);
        }}
      >
        <Trash2 size="0.6875rem" />
      </button>
    );
  };

  const containerAction = (container: DockerContainerUsage) => {
    if (container.state === "running") {
      return <LockHint title={t("disk.containerRunningTitle")} />;
    }
    return (
      <button
        type="button"
        className="btn xs"
        disabled={busy}
        title={t("disk.removeContainerTitle")}
        onClick={() => {
          onRemoveContainer(container);
        }}
      >
        <Trash2 size="0.6875rem" />
      </button>
    );
  };

  return (
    <div className="flex flex-col" style={{ gap: "0.5rem" }}>
      <Group
        icon={<Layers size="0.8125rem" />}
        title={t("disk.imagesGroup")}
        count={images.length}
        sizeBytes={usage.images_total_bytes}
        defaultOpen
      >
        {images.map((image) => (
          <Row
            key={image.reference}
            leading={
              <span
                style={{
                  width: "0.5rem",
                  height: "0.5rem",
                  borderRadius: "0.125rem",
                  background: categoryColor(image.category),
                }}
              />
            }
            primary={image.dangling ? t("disk.danglingRef") : image.reference}
            meta={[
              formatBytes(image.size_bytes),
              image.created,
              t(categoryLabelKey(image.category)),
            ]
              .filter(Boolean)
              .join(" · ")}
            badges={
              <>
                {image.in_use && (
                  <Badge text={t("disk.badgeInUse")} tone="ok" />
                )}
                {!image.in_use && image.protected && (
                  <Badge text={t("disk.badgeActive")} tone="accent" />
                )}
                {image.dangling && (
                  <Badge text={t("disk.badgeDangling")} tone="warn" />
                )}
              </>
            }
            action={imageAction(image)}
          />
        ))}
      </Group>

      <Group
        icon={<Box size="0.8125rem" />}
        title={t("disk.containersGroup")}
        count={containers.length}
        sizeBytes={usage.containers_total_bytes}
      >
        {containers.map((container) => (
          <Row
            key={container.name}
            leading={
              <span
                style={{
                  width: "0.5rem",
                  height: "0.5rem",
                  borderRadius: "999px",
                  background:
                    container.state === "running"
                      ? "var(--c-ok)"
                      : "var(--fg-3)",
                }}
              />
            }
            primary={container.name}
            meta={[
              container.state === "running"
                ? t("disk.stateRunning")
                : t("disk.stateStopped"),
              formatBytes(container.size_bytes),
              container.image,
            ].join(" · ")}
            action={containerAction(container)}
          />
        ))}
        {containers.length === 0 && (
          <span
            className="dim"
            style={{ fontSize: "0.6875rem", padding: "0.375rem" }}
          >
            {t("disk.noContainers")}
          </span>
        )}
      </Group>

      <Group
        icon={<Database size="0.8125rem" />}
        title={t("disk.volumesGroup")}
        count={volumes.length}
        sizeBytes={usage.volumes_total_bytes}
        footer={
          <span
            className="dim"
            style={{ fontSize: "0.65625rem", padding: "0.25rem 0.375rem 0" }}
          >
            {t("disk.volumesHint")}
          </span>
        }
      >
        {volumes.map((volume) => (
          <Row
            key={volume.name}
            leading={
              <Database size="0.6875rem" style={{ color: "var(--fg-3)" }} />
            }
            primary={volume.name}
            meta={[
              formatBytes(volume.size_bytes),
              t("disk.volumeLinks", { count: volume.links }),
            ].join(" · ")}
            action={null}
          />
        ))}
        {volumes.length === 0 && (
          <span
            className="dim"
            style={{ fontSize: "0.6875rem", padding: "0.375rem" }}
          >
            {t("disk.noVolumes")}
          </span>
        )}
      </Group>
    </div>
  );
};
