import { useEffect, useState } from "react";
import { Archive, HardDrive, Play, Plus, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { HelpAnchor } from "@entities/help";
import { localeTag } from "@shared/lib";
import {
  Badge,
  Button,
  ListRow,
  PageHeader,
  Section,
  SectionList,
  Spinner,
  TableSkeleton,
} from "@shared/ui";
import {
  AcceptedBanner,
  AcceptWarningButton,
  acceptedCheck,
  useDiagnosticsQuiet,
} from "@features/admin-diagnostics";
import { Banner, ViewState } from "@features/admin-ops/ui/parts";
import {
  useBackupRuns,
  useBackupStatus,
  useDeleteDestination,
  useDestinations,
  useSaveDestination,
  useSaveSettings,
  useStartBackup,
  useTestDestination,
} from "../api/queries";
import type { BackupDestination } from "../api/schemas";
import { bodyFromDraft } from "../lib/destinationDraft";
import { failureKey, failureOf, type BackupFailure } from "../lib/failure";
import { ensureAdminBackupsLocales } from "../lib/locales";
import { DestinationDialog } from "./DestinationDialog";
import { RunsTable } from "./RunsTable";
import { SettingsPanel } from "./SettingsPanel";
import { StoredBackupsDialog } from "./StoredBackupsDialog";

const describe = (d: BackupDestination): string =>
  d.kind === "s3"
    ? [d.endpoint ?? "AWS", d.bucket, d.prefix].filter(Boolean).join(" / ")
    : (d.local_path ?? "");

/** Раздел админки «Бэкапы»: назначения, расписание и хранение, история запусков. */
export const BackupsPage = () => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void ensureAdminBackupsLocales().then(() => {
      setReady(true);
    });
  }, []);
  return ready ? <BackupsContent /> : <TableSkeleton rows={4} />;
};

const BackupsContent = () => {
  const { t } = useTranslation("adminBackups");
  const status = useBackupStatus();
  const destinations = useDestinations();
  const accepted =
    acceptedCheck(useDiagnosticsQuiet().data, "backups") !== null;
  const [page, setPage] = useState(0);
  const busy = Boolean(status.data?.running);
  const runs = useBackupRuns(page, busy);
  const saveDest = useSaveDestination();
  const deleteDest = useDeleteDestination();
  const testDest = useTestDestination();
  const start = useStartBackup();
  const saveSettings = useSaveSettings();
  const [editing, setEditing] = useState<BackupDestination | "new" | null>(
    null,
  );
  const [viewing, setViewing] = useState<BackupDestination | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const [destFailure, setDestFailure] = useState<BackupFailure | null>(null);
  const [startFailure, setStartFailure] = useState<BackupFailure | null>(null);
  const [settingsFailure, setSettingsFailure] = useState<BackupFailure | null>(
    null,
  );
  const [checkedNow, setCheckedNow] = useState<Record<string, string>>({});
  const when = (iso: string) => new Date(iso).toLocaleString(localeTag());
  const list = destinations.data ?? [];
  const last = status.data?.last_run ?? null;

  return (
    <div
      className="flex flex-col"
      style={{ gap: "1.25rem" }}
      data-testid="backups-page"
    >
      <PageHeader
        title={t("page.title")}
        description={t("page.lead")}
        actions={
          <Button
            onClick={() => {
              setStartFailure(null);
              start.mutate(null, {
                onError: (e) => {
                  setStartFailure(failureOf(e));
                },
              });
            }}
            disabled={busy || start.isPending || list.length === 0}
            data-testid="backup-run-now"
          >
            {busy || start.isPending ? (
              <Spinner size="sm" />
            ) : (
              <Play size="0.875rem" />
            )}
            {t("page.runNow")}
          </Button>
        }
      />
      {startFailure && (
        <Banner
          tone="danger"
          title={t(failureKey(startFailure.code))}
          testId="backup-start-failure"
        />
      )}
      {status.data?.running && (
        <Banner
          tone="info"
          title={t("banner.running", {
            name: status.data.running.destination_name,
          })}
          testId="backup-banner-running"
        >
          {t("banner.stage", {
            stage: t(`runs.stage.${status.data.running.stage ?? "starting"}`, {
              defaultValue: status.data.running.stage ?? "",
            }),
          })}
        </Banner>
      )}
      {!busy &&
        last &&
        (last.status === "failed" || last.status === "interrupted") && (
          <Banner
            tone="danger"
            title={t("banner.failed", { at: when(last.started_at) })}
            testId="backup-banner-failed"
          >
            {last.error}
          </Banner>
        )}
      <AcceptedBanner check="backups" testId="backup-banner-accepted" />
      {destinations.isSuccess && list.length === 0 && !accepted && (
        <Banner
          tone="warning"
          title={t("banner.noDestination")}
          testId="backup-banner-empty"
          action={<AcceptWarningButton check="backups" />}
        >
          {t("banner.noDestinationBody")}
        </Banner>
      )}
      {status.data &&
        !status.data.settings.enabled &&
        list.length > 0 &&
        !accepted && (
          <Banner
            tone="info"
            title={t("banner.disabled")}
            testId="backup-banner-disabled"
            action={<AcceptWarningButton check="backups" />}
          />
        )}

      <Section
        title={
          <>
            {t("destinations.title")}
            <HelpAnchor article="admin/backups" step={1} />
          </>
        }
        description={t("destinations.lead")}
        testId="backup-destinations"
        actions={
          <Button
            size="sm"
            onClick={() => {
              setDestFailure(null);
              setEditing("new");
            }}
            data-testid="backup-add"
          >
            <Plus size="0.875rem" />
            {t("destinations.add")}
          </Button>
        }
      >
        <p className="form-hint" style={{ margin: "0 0 0.5rem" }}>
          {t("destinations.separate")}
        </p>
        <ViewState
          status={
            destinations.isPending
              ? "loading"
              : destinations.isError
                ? "error"
                : "ready"
          }
          errorText={t("destinations.loadFailed")}
          onRetry={() => void destinations.refetch()}
          compact
        />
        {list.length > 0 && (
          <SectionList
            label={t("destinations.title")}
            testId="backup-dest-list"
          >
            {list.map((d) => (
              <ListRow
                key={d.id}
                testId={`backup-dest-${d.id}`}
                icon={
                  d.kind === "s3" ? (
                    <Archive size="0.9375rem" />
                  ) : (
                    <HardDrive size="0.9375rem" />
                  )
                }
                title={
                  <span>
                    {d.name}{" "}
                    {d.is_default && (
                      <Badge variant="accent">
                        {t("destinations.default")}
                      </Badge>
                    )}{" "}
                    <Badge>{t(`kind.${d.kind}`)}</Badge>
                  </span>
                }
                description={
                  <span>
                    {describe(d)}
                    {d.last_check_at && (
                      <span
                        data-testid={`backup-dest-check-${d.id}`}
                        data-ok={String(d.last_check_ok)}
                        style={{
                          marginLeft: "0.5rem",
                          color: d.last_check_ok
                            ? "var(--c-ok)"
                            : "var(--c-err)",
                        }}
                      >
                        {d.last_check_ok
                          ? t("destinations.checkOk", {
                              at: when(d.last_check_at),
                            })
                          : t("destinations.checkFailed", {
                              error: d.last_check_error ?? "",
                            })}
                      </span>
                    )}
                    {checkedNow[d.id] && (
                      <span className="dim"> · {checkedNow[d.id]}</span>
                    )}
                  </span>
                }
                meta={
                  <span
                    className="flex items-center"
                    style={{ gap: "0.375rem", flexWrap: "wrap" }}
                  >
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={testDest.isPending}
                      onClick={() => {
                        testDest.mutate(d.id, {
                          onSuccess: (r) => {
                            setCheckedNow({
                              ...checkedNow,
                              [d.id]: r.warnings
                                .map((w) =>
                                  t(`warnings.${w}`, { defaultValue: w }),
                                )
                                .join(" "),
                            });
                          },
                        });
                      }}
                      data-testid={`backup-dest-test-${d.id}`}
                    >
                      {t("destinations.check")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setViewing(d);
                      }}
                      data-testid={`backup-dest-open-${d.id}`}
                    >
                      {t("destinations.backups")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setDestFailure(null);
                        setEditing(d);
                      }}
                      data-testid={`backup-dest-edit-${d.id}`}
                    >
                      {t("destinations.edit")}
                    </Button>
                    {removing === d.id ? (
                      <button
                        type="button"
                        className="btn danger"
                        onClick={() => {
                          deleteDest.mutate(d.id, {
                            onSettled: () => {
                              setRemoving(null);
                            },
                          });
                        }}
                        data-testid={`backup-dest-delete-confirm-${d.id}`}
                      >
                        {t("destinations.deleteConfirm")}
                      </button>
                    ) : (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setRemoving(d.id);
                        }}
                        data-testid={`backup-dest-delete-${d.id}`}
                      >
                        {t("destinations.delete")}
                      </Button>
                    )}
                  </span>
                }
              />
            ))}
          </SectionList>
        )}
        {deleteDest.isError && (
          <Banner
            tone="danger"
            title={t(failureKey(failureOf(deleteDest.error).code))}
          />
        )}
        {list.some((d) => d.kind === "local") && (
          <p
            className="form-hint"
            style={{ display: "flex", gap: "0.375rem", margin: "0.5rem 0 0" }}
          >
            <TriangleAlert size="0.875rem" aria-hidden="true" />
            {t("destinations.localRoot", {
              root: status.data?.local_root ?? "",
            })}
          </p>
        )}
      </Section>

      {status.data ? (
        <SettingsPanel
          key={JSON.stringify(status.data.settings)}
          status={status.data}
          saving={saveSettings.isPending}
          failure={settingsFailure}
          onSave={(body) => {
            setSettingsFailure(null);
            saveSettings.mutate(body, {
              onError: (e) => {
                setSettingsFailure(failureOf(e));
              },
            });
          }}
        />
      ) : (
        <ViewState
          status={status.isError ? "error" : "loading"}
          errorText={t("settings.loadFailed")}
          onRetry={() => void status.refetch()}
        />
      )}

      <RunsTable
        page={runs.data}
        pageIndex={page}
        loading={runs.isPending}
        error={runs.isError}
        onPage={setPage}
        onRetry={() => void runs.refetch()}
      />

      {editing !== null && (
        <DestinationDialog
          destination={editing === "new" ? null : editing}
          first={list.length === 0}
          localRoot={status.data?.local_root ?? ""}
          saving={saveDest.isPending}
          failure={destFailure}
          onClose={() => {
            setEditing(null);
          }}
          onSave={(draft) => {
            setDestFailure(null);
            saveDest.mutate(
              {
                id: editing === "new" ? null : editing.id,
                body: bodyFromDraft(draft),
              },
              {
                onSuccess: () => {
                  setEditing(null);
                },
                onError: (e) => {
                  setDestFailure(failureOf(e));
                },
              },
            );
          }}
        />
      )}
      {viewing && (
        <StoredBackupsDialog
          destination={viewing}
          onClose={() => {
            setViewing(null);
          }}
        />
      )}
    </div>
  );
};
