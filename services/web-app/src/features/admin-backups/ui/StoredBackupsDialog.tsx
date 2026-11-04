import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatFileSize, localeTag } from "@shared/lib";
import { Button, CopyField, EmptyState, Modal, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { useDeleteStored, useStoredBackups } from "../api/queries";
import type { BackupDestination } from "../api/schemas";
import { RestoreDialog } from "./RestoreDialog";
import { failureKey, failureOf } from "../lib/failure";

/** Бэкапы, лежащие в назначении: манифест, размер и готовая команда восстановления. */
export const StoredBackupsDialog = ({
  destination,
  onClose,
}: {
  destination: BackupDestination;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminBackups");
  const stored = useStoredBackups(destination.id, true);
  const remove = useDeleteStored();
  const [confirm, setConfirm] = useState<string | null>(null);
  const [restoring, setRestoring] = useState<string | null>(null);
  const failure = stored.isError
    ? failureOf(stored.error)
    : remove.isError
      ? failureOf(remove.error)
      : null;
  return (
    <Modal
      isOpen
      onClose={onClose}
      title={t("stored.title", { name: destination.name })}
      description={t("stored.lead")}
      width={700}
      footer={
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("close")}
        </Button>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: "0.75rem" }}
        data-testid="backup-stored"
      >
        <Notice tone="info" text={t("stored.restoreNote")} />
        {stored.isPending && <Spinner size="sm" />}
        {failure && (
          <Notice tone="err" role="alert" text={t(failureKey(failure.code))} />
        )}
        {stored.data?.length === 0 && (
          <EmptyState compact title={t("stored.empty")} />
        )}
        {stored.data?.map((item) => (
          <div
            key={item.backup_id}
            className="ops-card"
            data-testid={`backup-stored-${item.backup_id}`}
          >
            <div
              className="flex items-center"
              style={{ gap: "0.5rem", justifyContent: "space-between" }}
            >
              <strong>{item.backup_id}</strong>
              <span className="dim">
                {new Date(item.created_at).toLocaleString(localeTag())} ·{" "}
                {formatFileSize(item.size)}
              </span>
            </div>
            <div className="dim" style={{ fontSize: "0.75rem" }}>
              {t("stored.meta", {
                version: item.app_version,
                schema: item.schema_revision ?? "—",
                mode: t(`settings.encryption.options.${item.encryption_mode}`),
              })}
            </div>
            <CopyField
              value={item.restore_command}
              label={t("stored.command")}
              multiline
              wrap="spaces"
            />
            <div className="flex items-center" style={{ gap: "0.5rem" }}>
              <Button
                size="sm"
                onClick={() => {
                  setRestoring(item.backup_id);
                }}
                data-testid={`backup-stored-restore-${item.backup_id}`}
              >
                {t("stored.restore")}
              </Button>
            </div>
            {confirm === item.backup_id ? (
              <div className="flex items-center" style={{ gap: "0.5rem" }}>
                <span>{t("stored.confirmDelete")}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setConfirm(null);
                  }}
                >
                  {t("cancel")}
                </Button>
                <button
                  type="button"
                  className="btn danger"
                  disabled={remove.isPending}
                  data-testid={`backup-stored-delete-confirm-${item.backup_id}`}
                  onClick={() => {
                    remove.mutate(
                      { id: destination.id, backupId: item.backup_id },
                      {
                        onSettled: () => {
                          setConfirm(null);
                        },
                      },
                    );
                  }}
                >
                  {t("stored.delete")}
                </button>
              </div>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setConfirm(item.backup_id);
                }}
                data-testid={`backup-stored-delete-${item.backup_id}`}
              >
                {t("stored.delete")}
              </Button>
            )}
          </div>
        ))}
      </div>
      {restoring && (
        <RestoreDialog
          destinationId={destination.id}
          backupId={restoring}
          onClose={() => {
            setRestoring(null);
          }}
        />
      )}
    </Modal>
  );
};
