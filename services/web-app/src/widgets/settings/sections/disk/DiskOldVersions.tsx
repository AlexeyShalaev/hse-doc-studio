import { useState } from "react";
import { History, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Modal } from "@shared/ui/Modal";
import { formatBytes } from "@shared/lib";
import type { OldVersionItem, OldVersions } from "@entities/docker-system";

const KIND_LABEL_KEY: Record<OldVersionItem["kind"], string> = {
  studio_image: "disk.oldKindStudio",
  service_image: "disk.oldKindService",
  container: "disk.oldKindContainer",
};

const ItemRow = ({ item }: { item: OldVersionItem }) => {
  const { t } = useTranslation("settings");
  return (
    <div
      className="flex flex-wrap items-center justify-between"
      style={{ gap: "0.125rem 0.5rem", fontSize: "0.75rem", minWidth: 0 }}
    >
      <span
        className="mono"
        style={{ minWidth: 0, overflowWrap: "anywhere" }}
        title={item.ref}
      >
        {item.ref}
      </span>
      <span className="flex items-center" style={{ gap: "0.5rem" }}>
        <span className="dim" style={{ fontSize: "0.6875rem" }}>
          {t(KIND_LABEL_KEY[item.kind])}
        </span>
        <span className="mono dim">{formatBytes(item.size_bytes)}</span>
      </span>
    </div>
  );
};

/**
 * «Старые версии»: what updates left behind and a one-button, confirmed
 * cleanup. The current version and the latest previous one (rollback) are
 * never in the list; the rollback can only be removed on purpose, with an
 * explicit checkbox in the confirmation.
 */
export const DiskOldVersions = ({
  oldVersions,
  busy,
  onClean,
}: {
  oldVersions: OldVersions;
  busy: boolean;
  onClean: (includeRollback: boolean) => void;
}) => {
  const { t } = useTranslation("settings");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [includeRollback, setIncludeRollback] = useState(false);
  const { rollback, items } = oldVersions;
  const nothing = items.length === 0;
  const closeConfirm = () => {
    setConfirmOpen(false);
    setIncludeRollback(false);
  };
  const planItems = includeRollback && rollback ? [...items, rollback] : items;
  const planBytes = planItems.reduce((sum, i) => sum + i.size_bytes, 0);

  return (
    <div
      id="disk-old-versions"
      className="settings-anchor flex flex-col"
      style={{
        gap: "0.5rem",
        padding: "0.75rem",
        borderRadius: "var(--r-3)",
        border: "1px solid var(--border)",
        background: "var(--bg-1)",
      }}
    >
      <div
        className="flex flex-wrap items-center justify-between"
        style={{ gap: "0.375rem 0.5rem" }}
      >
        <span className="flex items-center" style={{ gap: "0.5rem" }}>
          <History size="0.875rem" style={{ color: "var(--fg-2)" }} />
          <span style={{ fontSize: "0.8125rem", fontWeight: 600 }}>
            {t("disk.oldTitle")}
          </span>
          {!nothing && (
            <span className="mono dim" style={{ fontSize: "0.71875rem" }}>
              {formatBytes(oldVersions.reclaimable_bytes)}
            </span>
          )}
        </span>
        <button
          type="button"
          className="btn xs"
          disabled={busy || nothing}
          onClick={() => {
            setConfirmOpen(true);
          }}
        >
          <Trash2 size="0.6875rem" />
          {t("disk.oldClean")}
        </button>
      </div>

      <div className="dim" style={{ fontSize: "0.71875rem" }}>
        {t("disk.oldBlockHint")}
      </div>

      <div className="dim" style={{ fontSize: "0.71875rem" }}>
        {t("disk.oldCurrent", { version: oldVersions.current_version })}
        {rollback && (
          <>
            {" · "}
            <span className="mono">
              {t("disk.oldRollback", { ref: rollback.ref })}
            </span>{" "}
            ({formatBytes(rollback.size_bytes)}, {t("disk.oldRollbackKept")})
          </>
        )}
      </div>

      {nothing ? (
        <div style={{ fontSize: "0.75rem" }}>{t("disk.oldNone")}</div>
      ) : (
        <div className="flex flex-col" style={{ gap: "0.25rem" }}>
          {items.map((item) => (
            <ItemRow key={`${item.kind}-${item.ref}`} item={item} />
          ))}
        </div>
      )}

      <Modal
        isOpen={confirmOpen}
        onClose={closeConfirm}
        title={t("disk.oldCleanTitle")}
        description={t("disk.oldCleanDescription")}
        footer={
          <>
            <button type="button" className="btn" onClick={closeConfirm}>
              {t("disk.cleanAllCancel")}
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => {
                onClean(includeRollback);
                closeConfirm();
              }}
            >
              <Trash2 size="0.75rem" />
              {t("disk.oldConfirmButton")} · {formatBytes(planBytes)}
            </button>
          </>
        }
      >
        <div
          className="flex flex-col"
          style={{ gap: "0.375rem", fontSize: "0.75rem" }}
        >
          {planItems.map((item) => (
            <ItemRow key={`${item.kind}-${item.ref}`} item={item} />
          ))}
          {rollback && (
            <label
              className="flex items-start"
              style={{ gap: "0.5rem", marginTop: "0.375rem" }}
            >
              <input
                type="checkbox"
                checked={includeRollback}
                style={{ marginTop: "0.1875rem" }}
                onChange={(e) => {
                  setIncludeRollback(e.target.checked);
                }}
              />
              <span>
                {t("disk.oldIncludeRollback", {
                  ref: rollback.ref,
                  size: formatBytes(rollback.size_bytes),
                })}
                <span
                  className="dim"
                  style={{ display: "block", fontSize: "0.6875rem" }}
                >
                  {t("disk.oldIncludeRollbackHint")}
                </span>
              </span>
            </label>
          )}
        </div>
      </Modal>
    </div>
  );
};
