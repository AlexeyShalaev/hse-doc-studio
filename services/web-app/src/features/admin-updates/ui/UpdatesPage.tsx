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
import {
  AcceptedBanner,
  AcceptWarningButton,
} from "@features/admin-diagnostics";
import { Banner, ViewState } from "@features/admin-ops/ui/parts";
import {
  useCancelUpdate,
  useCheckUpdates,
  useDowngradeUpdate,
  useRollbackUpdate,
  useSaveUpdateSettings,
  useSetAutoUpdate,
  useStartUpdate,
  useUpdateRuns,
  useUpdateStatus,
} from "../api/queries";
import type { DowngradeTarget, UpdateRun } from "../api/schemas";
import { failureKey, failureOf, type UpdateFailure } from "../lib/failure";
import { ensureAdminUpdatesLocales } from "../lib/locales";
import { buildProgress, formatDuration } from "../lib/progress";
import { useNow } from "../model/useNow";
import { useOutage } from "../model/useOutage";
import { AutoUpdateSection } from "./AutoUpdateSection";
import { FleetOffer } from "./FleetOffer";
import { HistoryTable } from "./HistoryTable";
import { PolicyPanel } from "./PolicyPanel";
import { RestartNotice } from "./RestartNotice";
import { FailureCard, SuccessCard } from "./RunOutcome";
import { ProgressSteps, RunProgressCard } from "./RunProgress";
import { VersionsSection } from "./VersionsSection";

/** Успешный итог показываем недолго: старый успех не нужен, он есть в истории. */
const RECENT_SUCCESS_MS = 30 * 60_000;

const notesOf = (
  data: { releases: { version: string; notes: string[] }[] },
  version: string,
): string[] => data.releases.find((r) => r.version === version)?.notes ?? [];

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
  const toggleAuto = useSetAutoUpdate();
  const downgrade = useDowngradeUpdate();
  const [failure, setFailure] = useState<UpdateFailure | null>(null);
  const [saveFailure, setSaveFailure] = useState<UpdateFailure | null>(null);
  const [confirmUpdate, setConfirmUpdate] = useState(false);
  const [updateVersion, setUpdateVersion] = useState<string | null>(null);
  const [autoFailure, setAutoFailure] = useState<UpdateFailure | null>(null);
  const [pickedDowngrade, setPickedDowngrade] =
    useState<DowngradeTarget | null>(null);
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
  const outage = useOutage(status);
  const openedRun = opened
    ? (runs.data?.items.find((r) => r.id === opened.id) ??
      (data?.active_run?.id === opened.id ? data.active_run : opened))
    : null;
  // Запуск, который мы видели идущим на этой странице: его итог показываем карточкой, даже когда api
  // перезапускался и вкладка пропустила часть хода.
  const [watched, setWatched] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const activeId = data?.active_run?.id ?? null;
  if (activeId && watched !== activeId) setWatched(activeId);
  const nowMs = useNow(true, 10_000);

  if (status.isPending || (status.isError && !outage.down) || !data) {
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
  const units = { h: t("units.h"), min: t("units.min"), s: t("units.s") };
  const formatOutage = (seconds: number) => formatDuration(seconds, units);
  /** Итог показываем: неудачи (кроме отмены самим админом) всегда, успех недавний или виденный нами. */
  const showOutcome = (run: UpdateRun): boolean => {
    if (run.kind === "downgrade" && run.status === "succeeded") return false;
    if (run.status === "succeeded") {
      const age = run.finished_at
        ? nowMs - Date.parse(run.finished_at)
        : Number.POSITIVE_INFINITY;
      return run.id === watched || age < RECENT_SUCCESS_MS;
    }
    if (run.status === "cancelled") {
      return (
        run.error_code !== "cancelled" &&
        run.error_code !== "auto_update_disabled" &&
        (run.id === watched || run.error_code !== null)
      );
    }
    return run.status === "failed" || run.status === "rolled_back";
  };
  const retryable = (run: UpdateRun): boolean =>
    run.kind === "update" &&
    canStart &&
    (data.available?.version === run.to_version ||
      data.releases.some((r) => r.version === run.to_version));
  const canRetry = last !== null && retryable(last);
  const retry = () => {
    if (!last) return;
    setFailure(null);
    setAcceptRisk(false);
    setUpdateVersion(last.to_version);
    setConfirmUpdate(true);
  };

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
                setUpdateVersion(null);
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
      {!active && last?.kind === "downgrade" && last.status === "succeeded" && (
        <DowngradeBanner
          last={last}
          when={when}
          canReturn={
            data.updater_online &&
            data.releases.some((r) => r.version === last.from_version) &&
            last.from_version !== data.current_version
          }
          onReturn={() => {
            setFailure(null);
            setAcceptRisk(false);
            setUpdateVersion(last.from_version);
            setConfirmUpdate(true);
          }}
        />
      )}
      {outage.down && outage.since !== null && (
        <RestartNotice
          since={outage.since}
          attempts={outage.attempts}
          updating={Boolean(active) || watched !== null}
          executor={data.executor}
          onRetryNow={() => void status.refetch()}
        />
      )}
      {!outage.down && outage.recoveredAfterS !== null && (
        <Banner
          tone="info"
          title={t("restart.back", {
            time: formatOutage(outage.recoveredAfterS),
          })}
          testId="update-back"
          action={
            <Button size="sm" variant="ghost" onClick={outage.dismissRecovered}>
              {t("outcome.dismiss")}
            </Button>
          }
        />
      )}
      {active && (
        <RunProgressCard
          run={active}
          executor={data.executor}
          updaterSilent={active.status === "running" && !data.updater_online}
          frozen={outage.down}
        />
      )}
      {!active && last && last.id !== dismissed && showOutcome(last) && (
        <div data-testid="update-banner-last">
          {last.status === "succeeded" ? (
            <SuccessCard
              run={last}
              staleTab={
                data.current_version === last.to_version &&
                __APP_VERSION__ !== last.to_version
              }
              tabVersion={__APP_VERSION__}
              outageS={outage.recoveredAfterS}
              notes={notesOf(data, last.to_version)}
              onDismiss={() => {
                setDismissed(last.id);
              }}
            />
          ) : (
            <FailureCard
              run={last}
              executor={data.executor}
              appVersion={__APP_VERSION__}
              currentVersion={data.current_version}
              onRetry={canRetry ? retry : undefined}
              onJournal={() => {
                setOpened(last);
              }}
              onDismiss={() => {
                setDismissed(last.id);
              }}
            />
          )}
        </div>
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
      {kube && data.backups_accepted && (
        <AcceptedBanner
          check="backups"
          testId="update-banner-backups-accepted"
        />
      )}
      {needRisk && (
        <Banner
          tone="warning"
          title={t("banner.noBackupKube")}
          testId="update-banner-nobackup-kube"
          action={<AcceptWarningButton check="backups" />}
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

      <AutoUpdateSection
        data={data}
        pending={toggleAuto.isPending}
        failure={autoFailure}
        onToggle={(enabled) => {
          setAutoFailure(null);
          toggleAuto.mutate(enabled, {
            onError: (e) => {
              setAutoFailure(failureOf(e));
            },
          });
        }}
      />

      <VersionsSection
        data={data}
        busy={busy}
        onPick={(target) => {
          setFailure(null);
          setPickedDowngrade(target);
        }}
      />

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
        error={runs.isError && !outage.down}
        onPage={setPage}
        onRetry={() => void runs.refetch()}
        onOpen={onOpen}
      />

      {confirmUpdate && (updateVersion ?? data.available?.version) && (
        <Modal
          isOpen
          onClose={() => {
            setConfirmUpdate(false);
          }}
          title={t("confirmUpdate.title", {
            version: updateVersion ?? data.available?.version ?? "",
          })}
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
                      version: updateVersion ?? data.available?.version ?? null,
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
          <ConfirmNotes
            version={updateVersion ?? data.available?.version ?? ""}
            notes={notesOf(
              data,
              updateVersion ?? data.available?.version ?? "",
            )}
          />
          {kube && (
            <p className="form-hint" data-testid="update-kube-schema">
              {t("confirmUpdate.schemaKube")}
            </p>
          )}
          {kube && data.backups_accepted && (
            <p className="form-hint" data-testid="update-backups-accepted">
              {t("confirmUpdate.backupsAccepted", {
                reason: data.backups_accepted.reason,
              })}
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

      {pickedDowngrade && (
        <Modal
          isOpen
          onClose={() => {
            setPickedDowngrade(null);
          }}
          title={t("confirmDowngrade.title", {
            version: pickedDowngrade.version,
          })}
          description={t("confirmDowngrade.body", {
            current: data.current_version,
            version: pickedDowngrade.version,
          })}
          footer={
            <>
              <Button
                variant="ghost"
                onClick={() => {
                  setPickedDowngrade(null);
                }}
              >
                {t("cancel")}
              </Button>
              <Button
                variant="danger"
                data-testid="update-downgrade-confirm"
                disabled={downgrade.isPending}
                onClick={() => {
                  downgrade.mutate(pickedDowngrade.version, {
                    onSuccess: () => {
                      setPickedDowngrade(null);
                    },
                    onError: (e) => {
                      setPickedDowngrade(null);
                      fail(e);
                    },
                  });
                }}
              >
                {t("confirmDowngrade.ok")}
              </Button>
            </>
          }
        >
          <Notice tone="info" text={t("confirmDowngrade.downtime")} />
          <Notice
            tone="info"
            text={t(`confirmDowngrade.schema.${pickedDowngrade.compat}`, {
              revision: pickedDowngrade.revision ?? "?",
            })}
          />
          {data.settings.backup_first && data.backup_destination_configured ? (
            <p className="form-hint" data-testid="downgrade-backup-yes">
              {t("confirmDowngrade.backupYes")}
            </p>
          ) : (
            <p className="form-hint" data-testid="downgrade-backup-no">
              {t(
                kube
                  ? "confirmDowngrade.backupNoKube"
                  : "confirmDowngrade.backupNo",
              )}
            </p>
          )}
          {data.settings.policy === "auto" && (
            <p className="form-hint" data-testid="downgrade-pauses-auto">
              {t("confirmDowngrade.pausesAuto")}
            </p>
          )}
        </Modal>
      )}

      {!active && !outage.down && <FleetOffer />}

      {openedRun && (
        <Modal
          isOpen
          onClose={() => {
            setOpened(null);
          }}
          title={t("events.title", {
            from: openedRun.from_version,
            to: openedRun.to_version,
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
          <ProgressSteps
            progress={buildProgress(openedRun, data.executor, nowMs)}
            run={openedRun}
            nowMs={nowMs}
          />
          <h4 className="upd-card-sub" style={{ marginTop: "0.75rem" }}>
            <strong>{t("events.journal")}</strong>
          </h4>
          <ol
            className="flex flex-col"
            style={{ gap: "0.375rem" }}
            data-testid="update-events"
          >
            {openedRun.events.map((e, i) => (
              <li key={`${String(e.seq)}-${String(i)}`} data-level={e.level}>
                <span className="dim">{when(e.at)}</span>{" "}
                <strong>
                  {t(`phase.${e.phase}`, { defaultValue: e.phase })}
                </strong>{" "}
                {e.message}
              </li>
            ))}
          </ol>
          {(openedRun.from_revision !== null ||
            openedRun.to_revision !== null) && (
            <p className="form-hint">
              {t("events.revisions", {
                from: openedRun.from_revision ?? "—",
                to: openedRun.to_revision ?? "—",
              })}
            </p>
          )}
        </Modal>
      )}
    </div>
  );
};

/** Заметки к версии на экране подтверждения: то, что релиз принёс (берётся из ленты релизов). */
const ConfirmNotes = ({
  version,
  notes,
}: {
  version: string;
  notes: string[];
}) => {
  const { t } = useTranslation("adminUpdates");
  return (
    <div data-testid="update-confirm-notes" style={{ marginTop: "0.5rem" }}>
      <p className="form-hint">
        <strong>{t("confirmUpdate.notes", { version })}</strong>
      </p>
      {notes.length > 0 ? (
        <ul className="upd-notes">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : (
        <p className="form-hint">{t("confirmUpdate.notesNone")}</p>
      )}
    </div>
  );
};

type DowngradeBannerProps = {
  last: UpdateRun;
  when: (iso: string) => string;
  canReturn: boolean;
  onReturn: () => void;
};

/** Итог последнего отката на выбранную версию: честно про исход и, если откат встал, как вернуть прежнюю. */
const DowngradeBanner = ({
  last,
  when,
  canReturn,
  onReturn,
}: DowngradeBannerProps) => {
  const { t } = useTranslation("adminUpdates");
  if (last.status === "succeeded") {
    return (
      <Banner
        tone="info"
        title={t("banner.downgrade.succeeded", {
          to: last.to_version,
          from: last.from_version,
          at: when(last.created_at),
        })}
        testId="update-banner-downgrade"
        action={
          canReturn ? (
            <Button
              size="sm"
              variant="ghost"
              data-testid="update-return"
              onClick={onReturn}
            >
              {t("banner.downgrade.return", { version: last.from_version })}
            </Button>
          ) : undefined
        }
      />
    );
  }
  return null;
};
