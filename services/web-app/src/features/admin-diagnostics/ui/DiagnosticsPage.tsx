import { useEffect, useState } from "react";
import {
  CircleAlert,
  CircleCheck,
  CircleHelp,
  CircleMinus,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
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
import type { TFunction } from "i18next";
import type {
  AdminDiagnostics,
  DiagAcceptance,
  DiagCheck,
  DiagStatus,
} from "@entities/session";
import { Banner, ViewState } from "@features/admin-ops/ui/parts";
import {
  useDiagnostics,
  useRunDiagnostics,
  useSaveThresholds,
} from "../api/queries";
import { ensureAdminDiagnosticsLocales } from "../lib/locales";
import { AcceptDialog } from "./AcceptDialog";
import { RevokeButton } from "./RevokeButton";
import { ThresholdsPanel } from "./ThresholdsPanel";

const GROUPS = ["data", "compute", "security", "operations"] as const;

const BADGE = { ok: "success", warn: "warning", fail: "error" } as const;
const TONE = { ok: "success", warn: "warning", fail: "danger" } as const;
const ICON = {
  ok: <CircleCheck size="0.9375rem" />,
  warn: <TriangleAlert size="0.9375rem" />,
  fail: <CircleAlert size="0.9375rem" />,
};

/** Раздел админки «Самодиагностика»: состояние проверок, подсказки, пороги. */
export const DiagnosticsPage = () => {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    void ensureAdminDiagnosticsLocales().then(() => {
      setReady(true);
    });
  }, []);
  return ready ? <DiagnosticsContent /> : <TableSkeleton rows={6} />;
};

/** Кто, когда и до какого срока принял предупреждение. */
const acceptedLine = (
  t: TFunction,
  acc: DiagAcceptance,
  when: (iso: string) => string,
): string =>
  t(acc.until ? "accepted.lineUntil" : "accepted.line", {
    by: acc.by_name,
    at: when(acc.at),
    until: acc.until ? when(acc.until) : "",
  });

const CheckRow = ({
  check,
  busy,
  onRecheck,
  onAccept,
}: {
  check: DiagCheck;
  busy: boolean;
  onRecheck: (id: string) => void;
  onAccept: (id: string) => void;
}) => {
  const { t } = useTranslation("adminDiagnostics");
  const status: DiagStatus | null = check.status;
  const accepted = check.accepted;
  const muted = !check.applicable || accepted !== null;
  const when = (iso: string) => new Date(iso).toLocaleString(localeTag());
  const reasonKey =
    check.reason === "ok"
      ? `okReason.${check.id}`
      : `reason.${check.reason ?? ""}`;
  const reason =
    check.reason && status
      ? t(reasonKey, {
          ...check.values,
          defaultValue: t("reason.unknown", { code: check.reason }),
        })
      : t("notChecked");
  return (
    <ListRow
      testId={`diag-check-${check.id}`}
      tone={status && !accepted ? TONE[status] : "neutral"}
      icon={
        muted ? (
          <CircleMinus size="0.9375rem" />
        ) : status ? (
          ICON[status]
        ) : (
          <CircleHelp size="0.9375rem" />
        )
      }
      title={
        <span
          data-testid={`diag-status-${check.id}`}
          data-status={status ?? "none"}
          data-applicable={String(check.applicable)}
          data-accepted={String(accepted !== null)}
        >
          {t(`check.${check.id}`, { defaultValue: check.id })}{" "}
          {status && !muted && (
            <Badge variant={BADGE[status]}>{t(`status.${status}`)}</Badge>
          )}
          {accepted && <Badge variant="subtle">{t("status.accepted")}</Badge>}
          {!check.applicable && (
            <Badge variant="subtle">{t("status.na")}</Badge>
          )}
        </span>
      }
      description={
        <span>
          <span data-testid={`diag-reason-${check.id}`}>{reason}</span>
          {accepted && (
            <span
              className="dim"
              style={{ display: "block" }}
              data-testid={`diag-accepted-note-${check.id}`}
            >
              {t("accepted.noteReason", { reason: accepted.reason })}
              {" · "}
              {acceptedLine(t, accepted, when)}
            </span>
          )}
          {check.hint && !accepted && (
            <span
              className="dim"
              style={{ display: "block" }}
              data-testid={`diag-hint-${check.id}`}
            >
              {t("hintPrefix")}{" "}
              {t(`hint.${check.hint}`, {
                ...check.values,
                defaultValue: t("hint.unknown"),
              })}
            </span>
          )}
        </span>
      }
      meta={
        <span className="flex items-center" style={{ gap: "0.5rem" }}>
          {check.checked_at && (
            <span className="dim" data-testid={`diag-time-${check.id}`}>
              {when(check.checked_at)}
            </span>
          )}
          {check.acceptable && (
            <Button
              size="sm"
              variant="secondary"
              data-testid={`diag-accept-${check.id}`}
              onClick={() => {
                onAccept(check.id);
              }}
            >
              {t("accept.button")}
            </Button>
          )}
          {accepted && <RevokeButton check={check.id} />}
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            data-testid={`diag-recheck-${check.id}`}
            onClick={() => {
              onRecheck(check.id);
            }}
          >
            {t("recheck")}
          </Button>
        </span>
      }
    />
  );
};

const Summary = ({ data }: { data: AdminDiagnostics }) => {
  const { t } = useTranslation("adminDiagnostics");
  const checked = data.checks.filter((c) => c.status !== null);
  const count = (s: DiagStatus) =>
    checked.filter((c) => c.status === s && c.applicable && !c.accepted).length;
  const accepted = data.checks.filter((c) => c.accepted !== null).length;
  const last = data.last_tick_at
    ? new Date(data.last_tick_at).toLocaleString(localeTag())
    : null;
  if (checked.length === 0) {
    return (
      <Banner tone="info" title={t("summary.none")} testId="diag-summary">
        {data.enabled ? t("summary.noneBody") : t("summary.disabled")}
      </Banner>
    );
  }
  const overall = data.overall;
  return (
    <Banner
      tone={
        overall === "ok" ? "info" : overall === "warn" ? "warning" : "danger"
      }
      title={t(`summary.${overall}`)}
      testId="diag-summary"
    >
      <span data-testid="diag-summary-status" data-status={overall}>
        {t("summary.counts", {
          ok: count("ok"),
          warn: count("warn"),
          fail: count("fail"),
        })}
        {accepted > 0 ? `, ${t("summary.accepted", { count: accepted })}` : ""}
        {last ? ` · ${t("summary.last", { at: last })}` : ""}
        {data.enabled ? "" : ` · ${t("summary.disabled")}`}
      </span>
    </Banner>
  );
};

/** Все принятые предупреждения в одном месте: причина, кто и когда принял, срок, «Вернуть». */
const AcceptedSection = ({ data }: { data: AdminDiagnostics }) => {
  const { t } = useTranslation("adminDiagnostics");
  const when = (iso: string) => new Date(iso).toLocaleString(localeTag());
  return (
    <Section
      title={t("accepted.title")}
      description={t("accepted.lead")}
      testId="diag-accepted"
    >
      {data.accepted.length === 0 ? (
        <p className="form-hint" data-testid="diag-accepted-empty">
          {t("accepted.empty")}
        </p>
      ) : (
        <SectionList label={t("accepted.title")}>
          {data.accepted.map(({ check, acceptance, active }) => (
            <ListRow
              key={check}
              testId={`diag-accepted-${check}`}
              tone="neutral"
              icon={<ShieldCheck size="0.9375rem" />}
              title={
                <span data-active={String(active)}>
                  {t(`check.${check}`, { defaultValue: check })}{" "}
                  <Badge variant="subtle">
                    {active ? t("status.accepted") : t("accepted.dormant")}
                  </Badge>
                </span>
              }
              description={
                <span>
                  <span data-testid={`diag-accepted-reason-${check}`}>
                    {t("accepted.noteReason", { reason: acceptance.reason })}
                  </span>
                  <span className="dim" style={{ display: "block" }}>
                    {acceptedLine(t, acceptance, when)}
                    {active ? "" : ` ${t("accepted.dormantHint")}`}
                  </span>
                </span>
              }
              meta={
                <RevokeButton
                  check={check}
                  testId={`diag-accepted-return-${check}`}
                />
              }
            />
          ))}
        </SectionList>
      )}
    </Section>
  );
};

const DiagnosticsContent = () => {
  const { t } = useTranslation("adminDiagnostics");
  const overview = useDiagnostics();
  const run = useRunDiagnostics();
  const save = useSaveThresholds();
  const [runningId, setRunningId] = useState<string | null>(null);
  const [accepting, setAccepting] = useState<string | null>(null);
  const data = overview.data;

  return (
    <div
      className="flex flex-col"
      style={{ gap: "1.25rem" }}
      data-testid="diagnostics-page"
    >
      <PageHeader
        title={t("page.title")}
        description={t("page.lead")}
        actions={
          <Button
            onClick={() => {
              setRunningId("*");
              run.mutate(null, {
                onSettled: () => {
                  setRunningId(null);
                },
              });
            }}
            disabled={run.isPending}
            data-testid="diag-run-all"
          >
            {run.isPending && runningId === "*" ? (
              <Spinner size="sm" />
            ) : (
              <RefreshCw size="0.875rem" />
            )}
            {t("page.runNow")}
          </Button>
        }
      />
      <ViewState
        status={
          overview.isPending ? "loading" : overview.isError ? "error" : "ready"
        }
        errorText={t("loadFailed")}
        onRetry={() => void overview.refetch()}
        testId="diag"
      />
      {run.isError && (
        <Banner tone="danger" title={t("runFailed")} testId="diag-run-failed" />
      )}
      {data && (
        <>
          <Summary data={data} />
          {GROUPS.map((group) => {
            const checks = data.checks.filter((c) => c.group === group);
            if (checks.length === 0) return null;
            return (
              <Section
                key={group}
                title={t(`group.${group}`)}
                testId={`diag-group-${group}`}
              >
                <SectionList label={t(`group.${group}`)}>
                  {checks.map((check) => (
                    <CheckRow
                      key={check.id}
                      check={check}
                      busy={run.isPending}
                      onAccept={setAccepting}
                      onRecheck={(id) => {
                        setRunningId(id);
                        run.mutate(id, {
                          onSettled: () => {
                            setRunningId(null);
                          },
                        });
                      }}
                    />
                  ))}
                </SectionList>
              </Section>
            );
          })}
          <AcceptedSection data={data} />
          {accepting && (
            <AcceptDialog
              check={accepting}
              onClose={() => {
                setAccepting(null);
              }}
            />
          )}
          <p className="form-hint" data-testid="diag-disk-note">
            {t("diskNote")} <Link to="/admin/data">{t("diskNoteLink")}</Link>
          </p>
          <ThresholdsPanel
            key={JSON.stringify(data.thresholds) + String(data.notify)}
            data={data}
            saving={save.isPending}
            failed={save.isError}
            onSave={(values, notify) => {
              save.mutate({ values, notify });
            }}
          />
        </>
      )}
    </div>
  );
};
