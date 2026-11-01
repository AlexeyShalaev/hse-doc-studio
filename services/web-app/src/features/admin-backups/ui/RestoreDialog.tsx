import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { formatFileSize, localeTag } from "@shared/lib";
import { Button, Input, Modal, SettingRow, Spinner } from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import {
  useMaintenance,
  useRestoreApply,
  useRestoreCancel,
  useRestoreJob,
  useRestorePreview,
} from "../api/queries";
import type { RestoreJob } from "../api/schemas";
import { failureKey, failureOf } from "../lib/failure";

/**
 * Восстановление из админки. Шаги: предпросмотр (сухой прогон, ничего не пишет), подтверждение
 * (id бэкапа руками и согласие на перезапись непустой установки), запись в режиме обслуживания.
 */
export const RestoreDialog = ({
  destinationId,
  backupId,
  onClose,
}: {
  destinationId: string;
  backupId: string;
  onClose: () => void;
}) => {
  const { t } = useTranslation("adminBackups");
  const preview = useRestorePreview();
  const apply = useRestoreApply();
  const cancel = useRestoreCancel();
  const current = useRestoreJob(true);
  const [confirm, setConfirm] = useState("");
  const [overwrite, setOverwrite] = useState(false);

  const job: RestoreJob | null =
    current.data?.backup_id === backupId ? current.data : null;
  // Пока идёт запись, вход и админка отвечают 503: состояние берём из открытой ручки.
  const started = !preview.isIdle;
  const writing = job?.phase === "applying" || (started && current.isError);
  const maintenance = useMaintenance(writing || job?.phase === "done");
  const rebooted = job?.phase === "done" && maintenance.data?.active === false;

  useEffect(() => {
    if (current.isSuccess && current.data === null && preview.isIdle) {
      preview.mutate({ destinationId, backupId });
    }
  }, [
    current.isSuccess,
    current.data,
    started,
    preview,
    destinationId,
    backupId,
  ]);

  const other = current.data && current.data.backup_id !== backupId;
  const failure = preview.isError
    ? failureOf(preview.error)
    : apply.isError
      ? failureOf(apply.error)
      : cancel.isError
        ? failureOf(cancel.error)
        : null;
  const phase = job?.phase ?? maintenance.data?.phase ?? null;
  const busy = phase === "verifying" || phase === "applying";
  const canApply =
    job?.phase === "verified" || (job?.phase === "failed" && job.wrote);
  const confirmed =
    confirm.trim() === backupId && (!job?.requires_overwrite || overwrite);

  const close = () => {
    if (job?.phase === "verified" || (job?.phase === "failed" && !job.wrote)) {
      cancel.mutate(undefined, { onSettled: onClose });
    } else {
      onClose();
    }
  };

  return (
    <Modal
      isOpen
      onClose={busy ? () => undefined : close}
      title={t("restore.title")}
      description={backupId}
      width={720}
      footer={
        <>
          {job?.phase === "failed" && job.wrote && (
            <Button
              variant="ghost"
              disabled={cancel.isPending}
              data-testid="backup-restore-leave"
              onClick={() => {
                cancel.mutate(undefined, { onSuccess: onClose });
              }}
            >
              {t("restore.leave")}
            </Button>
          )}
          {!busy && !(phase === "done") && (
            <Button
              type="button"
              variant="ghost"
              onClick={close}
              data-testid="backup-restore-close"
            >
              {job?.phase === "verified" ? t("cancel") : t("close")}
            </Button>
          )}
          {canApply && job.apply_allowed && (
            <button
              type="button"
              className="btn danger"
              disabled={!confirmed || apply.isPending}
              data-testid="backup-restore-apply"
              onClick={() => {
                apply.mutate({ job_id: job.id, confirm, overwrite });
              }}
            >
              {job.wrote ? t("restore.retry") : t("restore.apply")}
            </button>
          )}
        </>
      }
    >
      <div
        className="flex flex-col"
        style={{ gap: 12 }}
        data-testid="backup-restore"
        data-phase={phase ?? "none"}
      >
        {other && (
          <Notice tone="warn" role="alert" text={t("restore.otherJob")} />
        )}
        {failure && (
          <div data-testid="backup-restore-failure">
            <Notice
              tone="err"
              role="alert"
              text={t(failureKey(failure.code))}
            />
          </div>
        )}
        {(phase === "verifying" || (!job && !failure && !other)) && (
          <div className="flex items-center" style={{ gap: 8 }}>
            <Spinner size="sm" />
            <span>{t("restore.verifying")}</span>
          </div>
        )}
        {job && <Facts job={job} />}
        {job?.phase === "verified" && (
          <Confirmation
            job={job}
            confirm={confirm}
            overwrite={overwrite}
            onConfirm={setConfirm}
            onOverwrite={setOverwrite}
          />
        )}
        {phase === "applying" && (
          <>
            <div className="flex items-center" style={{ gap: 8 }}>
              <Spinner size="sm" />
              <span>{t("restore.applying")}</span>
            </div>
            <Notice tone="info" text={t("restore.maintenanceNote")} />
          </>
        )}
        {phase === "done" && (
          <div data-testid="backup-restore-done">
            <Notice
              tone="info"
              text={t(rebooted ? "restore.doneBack" : "restore.done")}
            />
          </div>
        )}
        {phase === "done" && rebooted && (
          <Button
            data-testid="backup-restore-relogin"
            onClick={() => {
              window.location.assign("/");
            }}
          >
            {t("restore.relogin")}
          </Button>
        )}
        {job?.phase === "failed" && (
          <div data-testid="backup-restore-error">
            <Notice
              tone="err"
              role="alert"
              text={
                <>
                  {t(failureKey(job.error_code ?? "unknown"))}
                  {job.error ? <code> {job.error}</code> : null}
                </>
              }
            />
          </div>
        )}
        {job?.phase === "failed" && job.wrote && (
          <Notice tone="warn" text={t("restore.partial")} />
        )}
        {job && job.log.length > 0 && (
          <pre
            className="form-hint"
            style={{ maxHeight: 180, overflow: "auto", margin: 0 }}
            data-testid="backup-restore-log"
          >
            {job.log.join("\n")}
          </pre>
        )}
      </div>
    </Modal>
  );
};

const Facts = ({ job }: { job: RestoreJob }) => {
  const { t } = useTranslation("adminBackups");
  if (!job.app_version) return null;
  return (
    <dl className="ops-facts" data-testid="backup-restore-facts">
      <div>
        <dt>{t("restore.facts.backup")}</dt>
        <dd>
          {job.backup_created_at
            ? new Date(job.backup_created_at).toLocaleString(localeTag())
            : "—"}
          {job.size !== null ? ` · ${formatFileSize(job.size)}` : ""}
        </dd>
      </div>
      <div>
        <dt>{t("restore.facts.version")}</dt>
        <dd>
          {job.app_version} · {job.schema_revision ?? "—"}
        </dd>
      </div>
      {job.target && (
        <div>
          <dt>{t("restore.facts.target")}</dt>
          <dd>
            {t("restore.facts.targetValue", {
              users: job.target.users,
              projects: job.target.projects,
              objects: job.target.objects,
            })}
          </dd>
        </div>
      )}
    </dl>
  );
};

const Confirmation = ({
  job,
  confirm,
  overwrite,
  onConfirm,
  onOverwrite,
}: {
  job: RestoreJob;
  confirm: string;
  overwrite: boolean;
  onConfirm: (v: string) => void;
  onOverwrite: (v: boolean) => void;
}) => {
  const { t } = useTranslation("adminBackups");
  return (
    <div className="flex flex-col" style={{ gap: 10 }}>
      <Notice tone="info" text={t("restore.verified")} />
      {!job.apply_allowed ? (
        <Notice tone="info" text={t("restore.disabled")} />
      ) : (
        <>
          <Notice tone="warn" text={t("restore.maintenanceNote")} />
          {job.requires_overwrite && (
            <>
              <Notice
                tone="err"
                text={t("restore.destroys", {
                  users: job.target?.users ?? 0,
                  projects: job.target?.projects ?? 0,
                  objects: job.target?.objects ?? 0,
                })}
              />
              <SettingRow
                label={t("restore.overwrite")}
                htmlFor="bk-restore-overwrite"
              >
                <Switch
                  id="bk-restore-overwrite"
                  checked={overwrite}
                  onChange={onOverwrite}
                />
              </SettingRow>
            </>
          )}
          <label htmlFor="bk-restore-confirm" className="form-hint">
            {t("restore.typeId", { id: job.backup_id })}
          </label>
          <Input
            id="bk-restore-confirm"
            value={confirm}
            autoComplete="off"
            onChange={(e) => {
              onConfirm(e.target.value);
            }}
            data-testid="backup-restore-confirm"
          />
        </>
      )}
    </div>
  );
};
