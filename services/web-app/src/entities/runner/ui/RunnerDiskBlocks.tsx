import { useState, type ReactNode } from "react";
import {
  Box,
  Database,
  HardDrive,
  History,
  Layers,
  Package,
  Trash2,
  Unlink,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import type {
  DiskTarget,
  DockerDisk,
  RunnerDiskReport,
} from "../model/runnerDisk.schema";
import { diskTargetBytes } from "../lib/runnerDiskLib";
import { diskSize } from "./format";

// Блоки «Диска» раннера (docs/design/storage-cleanup.md, 4.1): у каждого размер, пояснение и
// своя кнопка с подтверждением. Кнопки зовут onAsk(цель), подтверждение рисует панель.

const VISIBLE_ROWS = 3;

export type DiskBlockAction = {
  label: string;
  onClick: () => void;
  disabled: boolean;
};

export const DiskBlock = ({
  icon,
  title,
  size,
  detail,
  hint,
  action,
  children,
  testId,
}: {
  icon: ReactNode;
  title: string;
  size?: number | undefined;
  detail?: ReactNode;
  hint?: ReactNode;
  action?: DiskBlockAction | undefined;
  children?: ReactNode;
  testId: string;
}) => (
  <section
    data-testid={testId}
    className="flex flex-col"
    style={{
      gap: "0.375rem",
      padding: "0.625rem 0.75rem",
      borderRadius: "var(--r-3)",
      border: "1px solid var(--border)",
      background: "var(--bg-1)",
      minWidth: 0,
    }}
  >
    <div
      className="flex flex-wrap items-center justify-between"
      style={{ gap: "0.375rem 0.75rem" }}
    >
      <span
        className="flex items-center"
        style={{ gap: "0.5rem", minWidth: 0 }}
      >
        <span style={{ color: "var(--fg-2)", display: "flex", flexShrink: 0 }}>
          {icon}
        </span>
        <span style={{ fontSize: "0.8125rem", fontWeight: 600 }}>{title}</span>
        {size !== undefined && size > 0 && (
          <span className="mono dim" style={{ fontSize: "0.71875rem" }}>
            {diskSize(size)}
          </span>
        )}
      </span>
      {action && (
        <Button
          type="button"
          size="xs"
          variant="secondary"
          disabled={action.disabled}
          onClick={action.onClick}
          data-testid={`${testId}-action`}
        >
          <Trash2 size="0.6875rem" aria-hidden="true" />
          {action.label}
        </Button>
      )}
    </div>
    {detail != null && <div style={{ fontSize: "0.75rem" }}>{detail}</div>}
    {hint != null && (
      <div className="dim" style={{ fontSize: "0.71875rem", lineHeight: 1.5 }}>
        {hint}
      </div>
    )}
    {children}
  </section>
);

/** Строка образа или контейнера: ссылка моноширинно, справа пометка и размер. */
export const DiskRefRow = ({
  refName,
  bytes,
  note,
}: {
  refName: string;
  bytes: number;
  note?: string | undefined;
}) => (
  <div
    className="flex flex-wrap items-baseline justify-between"
    style={{ gap: "0.125rem 0.5rem", fontSize: "0.71875rem", minWidth: 0 }}
  >
    <span
      className="mono"
      style={{ minWidth: 0, overflowWrap: "anywhere" }}
      title={refName}
    >
      {refName}
    </span>
    <span className="flex items-center" style={{ gap: "0.5rem" }}>
      {note && <span className="dim">{note}</span>}
      <span className="mono dim">{diskSize(bytes)}</span>
    </span>
  </div>
);

/** Первые строки списка и «Показать все»: в блоке до сотни образов. */
const RefList = ({
  rows,
}: {
  rows: { key: string; refName: string; bytes: number; note?: string }[];
}) => {
  const { t } = useTranslation("runnerDisk");
  const [open, setOpen] = useState(false);
  const shown = open ? rows : rows.slice(0, VISIBLE_ROWS);
  return (
    <div className="flex flex-col" style={{ gap: "0.25rem" }}>
      {shown.map((row) => (
        <DiskRefRow
          key={row.key}
          refName={row.refName}
          bytes={row.bytes}
          note={row.note}
        />
      ))}
      {rows.length > VISIBLE_ROWS && (
        <Button
          type="button"
          size="xs"
          variant="ghost"
          style={{ alignSelf: "flex-start" }}
          aria-expanded={open}
          onClick={() => {
            setOpen((v) => !v);
          }}
        >
          {open ? t("showLess") : t("showAll", { count: rows.length })}
        </Button>
      )}
    </div>
  );
};

const OldVersionsBlock = ({
  docker,
  personal,
  action,
}: {
  docker: DockerDisk;
  personal: boolean;
  action: DiskBlockAction;
}) => {
  const { t } = useTranslation("runnerDisk");
  const { current_version, rollback, items, reclaimable_bytes } =
    docker.old_versions;
  return (
    <DiskBlock
      testId="runner-disk-old"
      icon={<History size="0.875rem" />}
      title={t("old.title")}
      size={reclaimable_bytes}
      hint={t("old.hint")}
      action={action}
      detail={
        <span className="dim" style={{ fontSize: "0.71875rem" }}>
          {t("old.current", { version: current_version })}
          {rollback && (
            <>
              <br />
              <span style={{ overflowWrap: "anywhere" }}>
                {t("old.rollback", {
                  ref: rollback.ref,
                  size: diskSize(rollback.size_bytes),
                })}
              </span>
            </>
          )}
          {rollback && personal && (
            <>
              <br />
              {t("old.rollbackAdminHint")}
            </>
          )}
        </span>
      }
    >
      {items.length === 0 ? (
        <div style={{ fontSize: "0.75rem" }}>{t("old.none")}</div>
      ) : (
        <RefList
          rows={items.map((item) => ({
            key: `${item.kind}-${item.ref}`,
            refName: item.ref,
            bytes: item.size_bytes,
            note: t(`old.kind.${item.kind}`),
          }))}
        />
      )}
    </DiskBlock>
  );
};

/** Блоки Docker-части: старые версии, неиспользуемые, кэш сборки, висячие, остановленные. */
export const DockerBlocks = ({
  report,
  docker,
  personal,
  actionFor,
}: {
  report: RunnerDiskReport;
  docker: DockerDisk;
  /** Личный раннер в админке: откат удаляет только владелец. */
  personal: boolean;
  actionFor: (target: DiskTarget, label: string) => DiskBlockAction;
}) => {
  const { t } = useTranslation("runnerDisk");
  const unusedBytes = diskTargetBytes(report, "unused_images");
  return (
    <>
      <OldVersionsBlock
        docker={docker}
        personal={personal}
        action={actionFor("old_versions", t("old.action"))}
      />
      <DiskBlock
        testId="runner-disk-unused"
        icon={<Package size="0.875rem" />}
        title={t("unused.title")}
        size={unusedBytes}
        hint={t("unused.hint")}
        action={actionFor("unused_images", t("unused.action"))}
      >
        {docker.unused_images.length === 0 ? (
          <div style={{ fontSize: "0.75rem" }}>{t("unused.none")}</div>
        ) : (
          <>
            <RefList
              rows={docker.unused_images.map((image) => ({
                key: image.ref,
                refName: image.ref,
                bytes: image.size_bytes,
                note: t(`category.${image.category}`),
              }))}
            />
            {docker.unused_truncated && (
              <div className="dim" style={{ fontSize: "0.6875rem" }}>
                {t("unused.truncated")}
              </div>
            )}
          </>
        )}
      </DiskBlock>
      <DiskBlock
        testId="runner-disk-build-cache"
        icon={<Layers size="0.875rem" />}
        title={t("cache.title")}
        size={docker.build_cache.reclaimable_bytes}
        detail={
          <span className="dim">
            {t("cache.detail", {
              size: diskSize(docker.build_cache.bytes),
              reclaimable: diskSize(docker.build_cache.reclaimable_bytes),
            })}
          </span>
        }
        action={actionFor("build_cache", t("cache.action"))}
      />
      <DiskBlock
        testId="runner-disk-dangling"
        icon={<Unlink size="0.875rem" />}
        title={t("dangling.title")}
        size={docker.dangling.bytes}
        detail={
          <span className="dim">
            {t("dangling.detail", {
              count: docker.dangling.count,
              size: diskSize(docker.dangling.bytes),
            })}
          </span>
        }
        action={actionFor("dangling_images", t("dangling.action"))}
      />
      {docker.stopped_containers.count > 0 && (
        <DiskBlock
          testId="runner-disk-stopped"
          icon={<Box size="0.875rem" />}
          title={t("stopped.title")}
          size={docker.stopped_containers.bytes}
          detail={
            <span className="dim">
              {t("stopped.detail", {
                count: docker.stopped_containers.count,
                size: diskSize(docker.stopped_containers.bytes),
              })}
            </span>
          }
          hint={t("stopped.hint")}
        />
      )}
    </>
  );
};

/** Кэш раннера: кэш файлов и рабочие копии с пределами и «занято сборками». */
export const RunnerCacheBlock = ({
  report,
  action,
}: {
  report: RunnerDiskReport;
  action: DiskBlockAction;
}) => {
  const { t } = useTranslation("runnerDisk");
  const { blobs, workspaces } = report.cache;
  return (
    <DiskBlock
      testId="runner-disk-cache"
      icon={<HardDrive size="0.875rem" />}
      title={t("runnerCache.title")}
      size={diskTargetBytes(report, "runner_cache")}
      hint={t("runnerCache.hint")}
      action={action}
      detail={
        <span className="flex flex-col dim" style={{ gap: "0.125rem" }}>
          <span>
            {t("runnerCache.blobs", {
              count: blobs.count,
              size: diskSize(blobs.bytes),
              limit: diskSize(blobs.limit_bytes),
            })}
          </span>
          <span>
            {t("runnerCache.workspaces", {
              count: workspaces.count,
              size: diskSize(workspaces.bytes),
              limit: diskSize(workspaces.limit_bytes),
            })}
            {workspaces.busy > 0 && (
              <>
                {", "}
                <span style={{ color: "var(--c-warn)" }}>
                  {t("runnerCache.busy", { count: workspaces.busy })}
                </span>
              </>
            )}
          </span>
        </span>
      }
    />
  );
};

/** Тома Студии: только размер, без кнопок. */
export const VolumesBlock = ({ docker }: { docker: DockerDisk }) => {
  const { t } = useTranslation("runnerDisk");
  if (docker.volumes.length === 0) return null;
  return (
    <DiskBlock
      testId="runner-disk-volumes"
      icon={<Database size="0.875rem" />}
      title={t("volumes.title")}
      hint={t("volumes.hint")}
    >
      <div className="flex flex-col" style={{ gap: "0.25rem" }}>
        {docker.volumes.map((volume) => (
          <DiskRefRow
            key={volume.name}
            refName={volume.name}
            bytes={volume.size_bytes}
          />
        ))}
      </div>
    </DiskBlock>
  );
};
