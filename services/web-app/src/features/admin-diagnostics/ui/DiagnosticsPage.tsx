import { useEffect, useState } from "react";
import {
  CircleAlert,
  CircleCheck,
  CircleHelp,
  CircleMinus,
  RefreshCw,
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
import type {
  AdminDiagnostics,
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
import { ThresholdsPanel } from "./ThresholdsPanel";

const GROUPS = ["data", "compute", "security", "operations"] as const;

const BADGE = { ok: "success", warn: "warning", fail: "error" } as const;
const TONE = { ok: "success", warn: "warning", fail: "danger" } as const;
const ICON = {
  ok: <CircleCheck size={15} />,
  warn: <TriangleAlert size={15} />,
  fail: <CircleAlert size={15} />,
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

const CheckRow = ({
  check,
  busy,
  onRecheck,
}: {
  check: DiagCheck;
  busy: boolean;
  onRecheck: (id: string) => void;
}) => {
  const { t } = useTranslation("adminDiagnostics");
  const status: DiagStatus | null = check.status;
  const muted = !check.applicable;
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
      tone={status ? TONE[status] : "neutral"}
      icon={
        muted ? (
          <CircleMinus size={15} />
        ) : status ? (
          ICON[status]
        ) : (
          <CircleHelp size={15} />
        )
      }
      title={
        <span
          data-testid={`diag-status-${check.id}`}
          data-status={status ?? "none"}
          data-applicable={String(check.applicable)}
        >
          {t(`check.${check.id}`, { defaultValue: check.id })}{" "}
          {status && !muted && (
            <Badge variant={BADGE[status]}>{t(`status.${status}`)}</Badge>
          )}
          {muted && <Badge variant="subtle">{t("status.na")}</Badge>}
        </span>
      }
      description={
        <span>
          <span data-testid={`diag-reason-${check.id}`}>{reason}</span>
          {check.hint && (
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
        <span className="flex items-center" style={{ gap: 8 }}>
          {check.checked_at && (
            <span className="dim" data-testid={`diag-time-${check.id}`}>
              {when(check.checked_at)}
            </span>
          )}
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
    checked.filter((c) => c.status === s && c.applicable).length;
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
        {last ? ` · ${t("summary.last", { at: last })}` : ""}
        {data.enabled ? "" : ` · ${t("summary.disabled")}`}
      </span>
    </Banner>
  );
};

const DiagnosticsContent = () => {
  const { t } = useTranslation("adminDiagnostics");
  const overview = useDiagnostics();
  const run = useRunDiagnostics();
  const save = useSaveThresholds();
  const [runningId, setRunningId] = useState<string | null>(null);
  const data = overview.data;

  return (
    <div
      className="flex flex-col"
      style={{ gap: 20 }}
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
              <RefreshCw size={14} />
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
