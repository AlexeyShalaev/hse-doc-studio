import { useCallback, useEffect, useState } from "react";
import { Download, RefreshCw, Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { localeTag } from "@shared/lib";
import {
  Button,
  CopyField,
  Modal,
  PageHeader,
  Section,
  Spinner,
  TableSkeleton,
} from "@shared/ui";
import { Notice } from "@shared/ui/ConflictKit";
import { Switch } from "@shared/ui/Switch";
import { Banner, ViewState } from "@features/admin-ops/ui/parts";
import {
  useCancelUpdate,
  useCheckUpdates,
  useRollbackUpdate,
  useSaveUpdateSettings,
  useStartUpdate,
  useUpdateRuns,
  useUpdateStatus,
} from "../api/queries";
import type { UpdateRun } from "../api/schemas";
import { failureKey, failureOf, type UpdateFailure } from "../lib/failure";
import { ensureAdminUpdatesLocales } from "../lib/locales";
import { HistoryTable } from "./HistoryTable";
import { PolicyPanel } from "./PolicyPanel";

/** Раздел админки «Обновления»: версия, политика и окно, история, «обновить сейчас» и «откатить». */
export const UpdatesPage = () => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void ensureAdminUpdatesLocales().then(() => {
      setReady(true);
    });
  }, []);
  return ready ? <UpdatesContent /> : <TableSkeleton rows={4} />;
};

const UpdatesContent = () => {
  const { t } = useTranslation("adminUpdates");
  const status = useUpdateStatus();
  const data = status.data;
  const busy = Boolean(data?.active_run);
  const [page, setPage] = useState(0);
  const runs = useUpdateRuns(page, busy);
  const check = useCheckUpdates();
  const start = useStartUpdate();
  const rollback = useRollbackUpdate();
  const cancel = useCancelUpdate();
  const save = useSaveUpdateSettings();
  const [failure, setFailure] = useState<UpdateFailure | null>(null);
  const [saveFailure, setSaveFailure] = useState<UpdateFailure | null>(null);
  const [confirmUpdate, setConfirmUpdate] = useState(false);
  const [acceptRisk, setAcceptRisk] = useState(false);
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [opened, setOpened] = useState<UpdateRun | null>(null);
  const onOpen = useCallback((run: UpdateRun) => {
    setOpened(run);
  }, []);
  const when = (iso: string) => new Date(iso).toLocaleString(localeTag());
  const fail = (e: unknown) => {
    setFailure(failureOf(e));
  };

  if (status.isPending || status.isError || !data) {
    return (
      <div data-testid="updates-page">
        <PageHeader title={t("page.title")} description={t("page.lead")} />
        <ViewState
          status={status.isPending ? "loading" : "error"}
          errorText={t("status.loadFailed")}
          onRetry={() => void status.refetch()}
        />
      </div>
    );
  }

  const kube = data.executor === "kubernetes";
  const needRisk = kube && data.risk_confirmation_required;
  const canStart =
    data.executor !== "none" &&
    data.updater_online &&
    !busy &&
    data.available !== null;
  const last = data.last_run;
  const active = data.active_run;

  return (
    <div
      className="flex flex-col"
      style={{ gap: "1.25rem" }}
      data-testid="updates-page"
    >
      <PageHeader
        title={t("page.title")}
        description={t("page.lead")}
        actions={
          <div className="flex" style={{ gap: "0.5rem", flexWrap: "wrap" }}>
            <Button
              variant="ghost"
              disabled={check.isPending}
              data-testid="update-check"
              onClick={() => {
                setFailure(null);
                check.mutate(undefined, { onError: fail });
              }}
            >
              {check.isPending ? (
                <Spinner size="sm" />
              ) : (
                <RefreshCw size="0.875rem" />
              )}
              {t("page.check")}
            </Button>
            <Button
              disabled={!canStart || start.isPending}
              data-testid="update-now"
              onClick={() => {
                setFailure(null);
                setAcceptRisk(false);
                setConfirmUpdate(true);
              }}
            >
              <Download size="0.875rem" />
              {t("page.updateNow")}
            </Button>
          </div>
        }
      />
      {failure && (
        <Banner
          tone="danger"
          title={t(failureKey(failure.code))}
          testId="update-failure"
        />
      )}
      {active && (
        <Banner
          tone="info"
          title={t("banner.running", {
            kind: t(`history.kind.${active.kind}`),
            from: active.from_version,
            to: active.to_version,
          })}
          testId="update-banner-running"
          action={
            active.status === "waiting_backup" || active.status === "queued" ? (
              <Button
                size="sm"
                variant="ghost"
                data-testid="update-cancel"
                onClick={() => {
                  cancel.mutate(active.id, { onError: fail });
                }}
              >
                {t("banner.cancel")}
              </Button>
            ) : undefined
          }
        >
          {t(`history.status.${active.status}`)}
          {active.phase
            ? ` · ${t(`phase.${active.phase}`, { defaultValue: active.phase })}`
            : ""}
        </Banner>
      )}
      {!active &&
        last &&
        (last.status === "failed" || last.status === "rolled_back") && (
          <Banner
            tone={last.status === "failed" ? "danger" : "warning"}
            title={t(
              last.error_code === "needs_manual_action"
                ? "banner.last.needs_hands"
                : `banner.last.${last.status}`,
              { to: last.to_version, at: when(last.created_at) },
            )}
            testId="update-banner-last"
          >
            {last.error}
          </Banner>
        )}
      {data.executor === "none" && (
        <Banner
          tone="info"
          title={t("banner.manual")}
          testId="update-banner-manual"
        >
          {t("banner.manualBody")}
        </Banner>
      )}
      {data.executor !== "none" && !data.updater_online && (
        <Banner
          tone="warning"
          title={t("banner.updaterOffline")}
          testId="update-banner-offline"
        >
          {t(kube ? "banner.updaterOfflineKube" : "banner.updaterOfflineBody")}
        </Banner>
      )}
      {needRisk && (
        <Banner
          tone="warning"
          title={t("banner.noBackupKube")}
          testId="update-banner-nobackup-kube"
        >
          {t("banner.noBackupKubeBody")}
        </Banner>
      )}
      {!kube &&
        data.settings.backup_first &&
        !data.backup_destination_configured && (
          <Banner
            tone="warning"
            title={t("banner.noBackup")}
            testId="update-banner-nobackup"
          >
            {t("banner.noBackupBody")}
          </Banner>
        )}
      {data.check_error && (
        <Banner
          tone="warning"
          title={t("banner.checkFailed")}
          testId="update-banner-check"
        >
          {data.check_error}
        </Banner>
      )}

      <Section
        title={t("version.title")}
        description={t("version.lead")}
        testId="update-version"
      >
        <dl className="ops-dl" data-testid="update-version-list">
          <div>
            <dt>{t("version.current")}</dt>
            <dd data-testid="update-current">{data.current_version}</dd>
          </div>
          <div>
            <dt>{t("version.available")}</dt>
            <dd data-testid="update-available">
              {data.available ? data.available.version : t("version.none")}
            </dd>
          </div>
          <div>
            <dt>{t("version.checked")}</dt>
            <dd>{data.checked_at ? when(data.checked_at) : "—"}</dd>
          </div>
          <div>
            <dt>{t("version.updater")}</dt>
            <dd data-testid="update-updater">
              {data.executor === "none"
                ? t("version.updaterNone")
                : data.updater_online
                  ? t("version.updaterOnline", {
                      version: data.updater_version ?? "?",
                    })
                  : t("version.updaterOffline")}
            </dd>
          </div>
          {data.settings.policy === "auto" && (
            <div>
              <dt>{t("version.window")}</dt>
              <dd data-testid="update-window">
                {data.in_window
                  ? t("version.inWindow")
                  : data.next_window_at
                    ? when(data.next_window_at)
                    : "—"}
              </dd>
            </div>
          )}
        </dl>
        {data.available && data.available.notes.length > 0 && (
          <ul
            className="form-hint"
            style={{ margin: "0.5rem 0 0 1rem" }}
            data-testid="update-notes"
          >
            {data.available.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        )}
        {data.available &&
          !data.available.has_digest &&
          data.settings.verify !== "none" && (
            <p className="form-hint" data-testid="update-no-digest">
              {t("version.noDigest")}
            </p>
          )}
        {data.executor === "none" && data.available && (
          <div style={{ marginTop: "0.5rem" }}>
            <CopyField
              value={data.manual_command}
              label={t("version.manualCommand")}
            />
          </div>
        )}
        {data.rollback_blocked && (
          <p className="form-hint" data-testid="update-rollback-blocked">
            {t("version.rollbackBlocked")}
          </p>
        )}
        {data.rollback_version && (
          <div style={{ marginTop: "0.75rem" }}>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy || !data.updater_online}
              data-testid="update-rollback"
              onClick={() => {
                setFailure(null);
                setConfirmRollback(true);
              }}
            >
              <Undo2 size="0.875rem" />
              {t("version.rollback", { version: data.rollback_version })}
            </Button>
          </div>
        )}
      </Section>

      <PolicyPanel
        key={JSON.stringify(data.settings)}
        settings={data.settings}
        executor={data.executor}
        saving={save.isPending}
        failure={saveFailure}
        onSave={(body) => {
          setSaveFailure(null);
          save.mutate(body, {
            onError: (e) => {
              setSaveFailure(failureOf(e));
            },
          });
        }}
      />

      <HistoryTable
        page={runs.data}
        pageIndex={page}
        loading={runs.isPending}
        error={runs.isError}
        onPage={setPage}
        onRetry={() => void runs.refetch()}
        onOpen={onOpen}
      />

      {confirmUpdate && data.available && (
        <Modal
          isOpen
          onClose={() => {
            setConfirmUpdate(false);
          }}
          title={t("confirmUpdate.title", { version: data.available.version })}
          description={t(
            kube ? "confirmUpdate.bodyKube" : "confirmUpdate.body",
          )}
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => {
                  setConfirmUpdate(false);
                }}
              >
                {t("cancel")}
              </Button>
              <Button
                data-testid="update-confirm"
                disabled={start.isPending || (needRisk && !acceptRisk)}
                onClick={() => {
                  start.mutate(
                    {
                      version: data.available?.version ?? null,
                      acceptRisk: needRisk && acceptRisk,
                    },
                    {
                      onSuccess: () => {
                        setConfirmUpdate(false);
                      },
                      onError: (e) => {
                        setConfirmUpdate(false);
                        fail(e);
                      },
                    },
                  );
                }}
              >
                {t("confirmUpdate.ok")}
              </Button>
            </>
          }
        >
          <Notice tone="info" text={t("confirmUpdate.downtime")} />
          {kube && (
            <p className="form-hint" data-testid="update-kube-schema">
              {t("confirmUpdate.schemaKube")}
            </p>
          )}
          {needRisk && (
            <div
              className="flex"
              style={{
                gap: "0.5rem",
                alignItems: "center",
                marginTop: "0.75rem",
              }}
            >
              <Switch
                id="update-accept-risk"
                checked={acceptRisk}
                onChange={setAcceptRisk}
                label={t("confirmUpdate.acceptRisk")}
                testId="update-accept-risk"
              />
              <label htmlFor="update-accept-risk">
                {t("confirmUpdate.acceptRisk")}
              </label>
            </div>
          )}
        </Modal>
      )}

      {confirmRollback && data.rollback_version && (
        <Modal
          isOpen
          onClose={() => {
            setConfirmRollback(false);
          }}
          title={t("confirmRollback.title", { version: data.rollback_version })}
          description={t("confirmRollback.body")}
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => {
                  setConfirmRollback(false);
                }}
              >
                {t("cancel")}
              </Button>
              <Button
                variant="danger"
                data-testid="update-rollback-confirm"
                disabled={rollback.isPending}
                onClick={() => {
                  rollback.mutate(data.rollback_needs_restore, {
                    onSuccess: () => {
                      setConfirmRollback(false);
                    },
                    onError: (e) => {
                      setConfirmRollback(false);
                      fail(e);
                    },
                  });
                }}
              >
                {t("confirmRollback.ok")}
              </Button>
            </>
          }
        >
          {data.rollback_needs_restore ? (
            <Notice tone="err" text={t("confirmRollback.dataLoss")} />
          ) : (
            <Notice tone="info" text={t("confirmRollback.noDataLoss")} />
          )}
        </Modal>
      )}

      {opened && (
        <Modal
          isOpen
          onClose={() => {
            setOpened(null);
          }}
          title={t("events.title", {
            from: opened.from_version,
            to: opened.to_version,
          })}
          width={680}
          footer={
            <Button
              variant="ghost"
              onClick={() => {
                setOpened(null);
              }}
            >
              {t("close")}
            </Button>
          }
        >
          <ol
            className="flex flex-col"
            style={{ gap: "0.375rem" }}
            data-testid="update-events"
          >
            {opened.events.map((e, i) => (
              <li key={`${String(e.seq)}-${String(i)}`} data-level={e.level}>
                <span className="dim">{when(e.at)}</span>{" "}
                <strong>
                  {t(`phase.${e.phase}`, { defaultValue: e.phase })}
                </strong>{" "}
                {e.message}
              </li>
            ))}
          </ol>
          {(opened.from_revision !== null || opened.to_revision !== null) && (
            <p className="form-hint">
              {t("events.revisions", {
                from: opened.from_revision ?? "—",
                to: opened.to_revision ?? "—",
              })}
            </p>
          )}
        </Modal>
      )}
    </div>
  );
};
