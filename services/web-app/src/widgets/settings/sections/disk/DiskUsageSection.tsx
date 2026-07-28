import { useMemo, useState } from "react";
import { clsx } from "clsx";
import { AlertTriangle, RefreshCw, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Spinner } from "@shared/ui/Spinner";
import { Modal } from "@shared/ui/Modal";
import { formatBytes } from "@shared/lib";
import { useAppSettings, useUpdateAppSettings } from "@entities/app-settings";
import {
  isJobActive,
  useCleanupJob,
  useDockerUsage,
  useStartCleanup,
  type CleanupTarget,
  type DockerUsage,
} from "@entities/docker-system";
import { Setting, SettingHead } from "../Setting";
import { DiskCleanupPanel } from "./DiskCleanupPanel";
import { DiskEntityLists } from "./DiskEntityLists";
import { buildSegments, type Segment } from "./lib";

const WARN_THRESHOLDS = [0, 5, 10, 20, 50] as const;
type WarnThreshold = (typeof WARN_THRESHOLDS)[number];

const StackedBar = ({ segments }: { segments: Segment[] }) => (
  <div
    className="flex items-center"
    style={{
      height: 22,
      borderRadius: "var(--r-2)",
      overflow: "hidden",
      background: "var(--bg-2)",
      gap: 2,
      padding: 2,
    }}
  >
    {segments.map((s) => (
      <div
        key={s.key}
        title={formatBytes(s.bytes)}
        style={{
          flex: `${s.bytes.toFixed(0)} 0 0`,
          height: "100%",
          borderRadius: 2,
          background: s.color,
          minWidth: 3,
        }}
      />
    ))}
  </div>
);

const Legend = ({ segments }: { segments: Segment[] }) => {
  const { t } = useTranslation("settings");
  return (
    <div
      className="flex flex-wrap items-center"
      style={{ gap: "6px 16px", fontSize: 11.5 }}
    >
      {segments.map((s) => (
        <div key={s.key} className="flex items-center" style={{ gap: 6 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              background: s.color,
              flexShrink: 0,
            }}
          />
          <span className="dim">{t(s.labelKey)}</span>
          <span className="mono">{formatBytes(s.bytes)}</span>
        </div>
      ))}
    </div>
  );
};

// What «Очистить всё» would actually remove — shown in the confirm modal so
// the user approves a concrete list, not an abstract "everything".
const buildCleanAllPlan = (usage: DockerUsage) => {
  const unusedImages = usage.images.filter(
    (i) => !i.protected && !i.dangling && i.category !== "other",
  );
  const danglingBytes = usage.images
    .filter((i) => i.dangling)
    .reduce((sum, i) => sum + i.size_bytes, 0);
  const stoppedContainers = usage.containers.filter(
    (c) => c.managed && c.state !== "running",
  );
  return { unusedImages, danglingBytes, stoppedContainers };
};

export const DiskUsageSection = () => {
  const { t } = useTranslation("settings");
  const usageQuery = useDockerUsage();
  const jobQuery = useCleanupJob();
  const startCleanup = useStartCleanup();
  const { data: appSettings } = useAppSettings();
  const { mutate: updateAppSettings, isPending: isSavingThreshold } =
    useUpdateAppSettings();
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);

  const usage = usageQuery.data;
  const warnGb = (appSettings?.disk_usage_warn_gb ?? 10) as WarnThreshold;
  const busy = isJobActive(jobQuery.data?.job) || startCleanup.isPending;

  const segments = useMemo(
    () => (usage?.available ? buildSegments(usage) : []),
    [usage],
  );
  const total = segments.reduce((sum, s) => sum + s.bytes, 0);

  const start = (input: {
    targets?: CleanupTarget[];
    images?: string[];
    containers?: string[];
  }) => {
    startCleanup.mutate(input);
  };

  const handleWarnThreshold = (gb: WarnThreshold) => {
    if (gb === warnGb) return;
    updateAppSettings({ disk_usage_warn_gb: gb });
  };

  const plan = usage?.available ? buildCleanAllPlan(usage) : null;

  const renderOverview = (data: DockerUsage) => (
    <div className="flex flex-col" style={{ gap: 10 }}>
      <div className="flex items-center justify-between" style={{ gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {t("disk.total")}: {formatBytes(total)}
        </span>
        <span className="flex items-center" style={{ gap: 8 }}>
          {data.cleanable_bytes > 0 && (
            <span className="dim" style={{ fontSize: 11.5 }}>
              {t("disk.cleanable", { size: formatBytes(data.cleanable_bytes) })}
            </span>
          )}
          <button
            type="button"
            className="icon-btn"
            title={t("disk.refresh")}
            disabled={usageQuery.isFetching}
            onClick={() => {
              void usageQuery.refetch();
            }}
          >
            <RefreshCw
              size={12}
              className={usageQuery.isFetching ? "animate-spin" : undefined}
            />
          </button>
        </span>
      </div>
      <StackedBar segments={segments} />
      <Legend segments={segments} />
    </div>
  );

  const renderActions = (data: DockerUsage) => (
    <div className="flex flex-wrap items-center" style={{ gap: 8 }}>
      <button
        type="button"
        className="btn xs"
        disabled={busy || data.build_cache_reclaimable_bytes === 0}
        onClick={() => {
          start({ targets: ["build_cache"] });
        }}
      >
        {t("disk.cleanBuildCache")}
        {data.build_cache_reclaimable_bytes > 0 && (
          <span className="dim mono" style={{ fontSize: 10 }}>
            {formatBytes(data.build_cache_reclaimable_bytes)}
          </span>
        )}
      </button>
      <button
        type="button"
        className="btn xs"
        disabled={busy}
        onClick={() => {
          start({ targets: ["dangling_images"] });
        }}
      >
        {t("disk.cleanDangling")}
      </button>
      <button
        type="button"
        className="btn xs"
        disabled={busy}
        style={{ borderColor: "var(--accent)", color: "var(--accent)" }}
        onClick={() => {
          setConfirmAllOpen(true);
        }}
      >
        {busy ? <Spinner size="sm" /> : <Trash2 size={11} />}
        {t("disk.cleanAll")}
      </button>
    </div>
  );

  return (
    <>
      <SettingHead
        anchorId="disk"
        title={t("disk.title")}
        sub={t("disk.subtitle")}
      />

      <div className="flex flex-col" style={{ gap: 12, paddingBottom: 14 }}>
        {usageQuery.isLoading ? (
          <div className="flex items-center" style={{ gap: 8, fontSize: 12 }}>
            <Spinner size="sm" />
            <span className="dim">{t("disk.loading")}</span>
          </div>
        ) : !usage?.available ? (
          <div
            className="flex items-start"
            style={{
              gap: 10,
              padding: 12,
              borderRadius: 6,
              border: "1px solid var(--c-err)",
              background: "var(--c-err-soft)",
            }}
          >
            <AlertTriangle
              size={14}
              style={{ color: "var(--c-err)", marginTop: 1, flexShrink: 0 }}
            />
            <div style={{ fontSize: 12.5, color: "var(--c-err)" }}>
              {t("disk.dockerUnavailable")}
            </div>
          </div>
        ) : (
          <>
            {renderOverview(usage)}
            {renderActions(usage)}
            <DiskCleanupPanel />
            <div id="disk-entities" className="settings-anchor">
              <DiskEntityLists
                usage={usage}
                busy={busy}
                onRemoveImage={(image) => {
                  if (
                    !window.confirm(
                      t("disk.removeImageConfirm", { image: image.reference }),
                    )
                  ) {
                    return;
                  }
                  start({ images: [image.reference] });
                }}
                onRemoveDangling={() => {
                  start({ targets: ["dangling_images"] });
                }}
                onRemoveContainer={(container) => {
                  start({ containers: [container.name] });
                }}
              />
            </div>
          </>
        )}
      </div>

      <Setting
        anchorId="disk-warn-threshold"
        label={t("disk.warnThresholdLabel")}
        hint={t("disk.warnThresholdHint")}
      >
        <div className="seg">
          {WARN_THRESHOLDS.map((gb) => (
            <button
              key={gb}
              type="button"
              className={clsx(warnGb === gb && "active")}
              onClick={() => {
                handleWarnThreshold(gb);
              }}
              disabled={isSavingThreshold}
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {gb === 0 ? t("disk.warnThresholdOff") : `${gb.toFixed(0)} GB`}
            </button>
          ))}
        </div>
      </Setting>

      <Modal
        isOpen={confirmAllOpen}
        onClose={() => {
          setConfirmAllOpen(false);
        }}
        title={t("disk.cleanAllTitle")}
        description={t("disk.cleanAllDescription")}
        footer={
          <>
            <button
              type="button"
              className="btn"
              onClick={() => {
                setConfirmAllOpen(false);
              }}
            >
              {t("disk.cleanAllCancel")}
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => {
                setConfirmAllOpen(false);
                start({
                  targets: [
                    "build_cache",
                    "dangling_images",
                    "unused_images",
                    "stopped_containers",
                  ],
                });
              }}
            >
              <Trash2 size={12} />
              {t("disk.cleanAllConfirmButton")}
            </button>
          </>
        }
      >
        {plan && usage && (
          <div className="flex flex-col" style={{ gap: 6, fontSize: 12 }}>
            {usage.build_cache_reclaimable_bytes > 0 && (
              <div className="flex items-center justify-between">
                <span className="dim">{t("disk.stepBuildCache")}</span>
                <span className="mono">
                  {formatBytes(usage.build_cache_reclaimable_bytes)}
                </span>
              </div>
            )}
            {plan.danglingBytes > 0 && (
              <div className="flex items-center justify-between">
                <span className="dim">{t("disk.stepDangling")}</span>
                <span className="mono">{formatBytes(plan.danglingBytes)}</span>
              </div>
            )}
            {plan.unusedImages.map((image) => (
              <div
                key={image.reference}
                className="flex items-center justify-between"
                style={{ gap: 8, minWidth: 0 }}
              >
                <span
                  className="mono"
                  style={{
                    minWidth: 0,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {image.reference}
                </span>
                <span className="mono dim" style={{ flexShrink: 0 }}>
                  {formatBytes(image.size_bytes)}
                </span>
              </div>
            ))}
            {plan.stoppedContainers.map((container) => (
              <div
                key={container.name}
                className="flex items-center justify-between"
                style={{ gap: 8 }}
              >
                <span className="mono">{container.name}</span>
                <span className="mono dim">
                  {formatBytes(container.size_bytes)}
                </span>
              </div>
            ))}
            {usage.build_cache_reclaimable_bytes === 0 &&
              plan.danglingBytes === 0 &&
              plan.unusedImages.length === 0 &&
              plan.stoppedContainers.length === 0 && (
                <span className="dim">{t("disk.cleanAllNothing")}</span>
              )}
          </div>
        )}
      </Modal>
    </>
  );
};
