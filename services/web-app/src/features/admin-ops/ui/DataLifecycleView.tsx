import { useState } from "react";
import { useTranslation } from "react-i18next";
import { formatFileSize, formatPastTime } from "@shared/lib";
import { Button, Input, PageHeader, Section } from "@shared/ui";
import type {
  AdminDataLifecycle,
  LifecycleSource,
  StorageThresholds,
} from "@entities/session";
import type { ViewStatus } from "../lib/viewStatus";
import { Banner, ViewState } from "./parts";

export type DataLifecycleViewProps = {
  status: ViewStatus;
  data: AdminDataLifecycle | null;
  busyKey?: string | null;
  failure?: string | null;
  onRetry?: () => void;
  onSetRetention: (key: string, days: number | null) => void;
  onRun: (key: string) => void;
  onSetThresholds: (body: StorageThresholds) => void;
};

const GROUPS = ["database", "objects", "disk", "logs"] as const;

const SourceRow = ({
  source,
  busy,
  onSetRetention,
  onRun,
}: {
  source: LifecycleSource;
  busy: boolean;
  onSetRetention: DataLifecycleViewProps["onSetRetention"];
  onRun: DataLifecycleViewProps["onRun"];
}) => {
  const { t } = useTranslation("adminOps");
  const [draft, setDraft] = useState(String(source.days ?? ""));
  const value = Number(draft);
  const valid =
    Number.isInteger(value) &&
    value >= (source.min_days ?? 1) &&
    value <= (source.max_days ?? 0);
  const changed = draft !== String(source.days ?? "");
  const run = source.last_run;
  return (
    <tr data-testid={`lc-row-${source.key}`}>
      <td>
        <strong>{t(`lifecycle.source.${source.key}.title`)}</strong>
        <div className="lc-sub">{t(`lifecycle.source.${source.key}.body`)}</div>
      </td>
      <td>{t(`lifecycle.strategy.${source.strategy}`)}</td>
      <td data-testid={`lc-size-${source.key}`}>
        {source.bytes === null ? "—" : formatFileSize(source.bytes)}
        {source.rows ? (
          <div className="lc-sub">
            {t("lifecycle.rows", { count: source.rows })}
          </div>
        ) : null}
      </td>
      <td>
        {source.editable ? (
          <div className="flex items-center" style={{ gap: 6 }}>
            <Input
              type="number"
              style={{ width: 90 }}
              value={draft}
              min={source.min_days ?? 1}
              max={source.max_days ?? undefined}
              aria-label={t("lifecycle.daysAria", {
                name: t(`lifecycle.source.${source.key}.title`),
              })}
              onChange={(e) => {
                setDraft(e.target.value);
              }}
              data-testid={`lc-days-${source.key}`}
            />
            <span className="lc-sub">{t("lifecycle.days")}</span>
            <Button
              size="sm"
              disabled={!changed || !valid || busy}
              onClick={() => {
                onSetRetention(source.key, value);
              }}
              data-testid={`lc-save-${source.key}`}
            >
              {t("lifecycle.save")}
            </Button>
            {source.days_source === "admin" && (
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  onSetRetention(source.key, null);
                }}
                data-testid={`lc-reset-${source.key}`}
              >
                {t("lifecycle.reset")}
              </Button>
            )}
          </div>
        ) : (
          <span>
            {t(`lifecycle.fixed.${source.key}`, { defaultValue: "—" })}
          </span>
        )}
        {source.editable && (
          <div className="lc-sub">
            {t(`lifecycle.daysSource.${source.days_source}`)}
            {source.min_days !== null &&
              ` · ${t("lifecycle.bounds", { min: source.min_days, max: source.max_days })}`}
            {source.days === null && ` · ${t("lifecycle.forever")}`}
          </div>
        )}
      </td>
      <td data-testid={`lc-last-${source.key}`}>
        {run?.at ? formatPastTime(run.at) : "—"}
        {run?.removed ? (
          <div className="lc-sub">
            {t("lifecycle.removed", { count: run.removed })}
          </div>
        ) : null}
        {run?.error && (
          <div role="alert" style={{ color: "var(--c-err)", fontSize: 12 }}>
            {run.error}
          </div>
        )}
      </td>
      <td>
        {source.run_now && (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => {
              onRun(source.key);
            }}
            data-testid={`lc-run-${source.key}`}
          >
            {t("lifecycle.runNow")}
          </Button>
        )}
      </td>
    </tr>
  );
};

const Thresholds = ({
  value,
  onSave,
}: {
  value: StorageThresholds;
  onSave: (body: StorageThresholds) => void;
}) => {
  const { t } = useTranslation("adminOps");
  const [warn, setWarn] = useState(String(value.warn_percent));
  const [crit, setCrit] = useState(String(value.critical_percent));
  const w = Number(warn);
  const c = Number(crit);
  const ok =
    Number.isInteger(w) && Number.isInteger(c) && w >= 50 && c <= 99 && w < c;
  const changed = w !== value.warn_percent || c !== value.critical_percent;
  return (
    <div className="flex items-center" style={{ gap: 8 }}>
      <span>{t("lifecycle.thresholds.warn")}</span>
      <Input
        type="number"
        style={{ width: 80 }}
        value={warn}
        onChange={(e) => {
          setWarn(e.target.value);
        }}
        data-testid="lc-warn"
      />
      <span>{t("lifecycle.thresholds.critical")}</span>
      <Input
        type="number"
        style={{ width: 80 }}
        value={crit}
        onChange={(e) => {
          setCrit(e.target.value);
        }}
        data-testid="lc-critical"
      />
      <Button
        size="sm"
        disabled={!ok || !changed}
        onClick={() => {
          onSave({ warn_percent: w, critical_percent: c });
        }}
        data-testid="lc-thresholds-save"
      >
        {t("lifecycle.save")}
      </Button>
    </div>
  );
};

/** «Хранение данных»: тома и база с порогами, затем источники роста со сроками и очисткой. */
export const DataLifecycleView = (props: DataLifecycleViewProps) => {
  const { t } = useTranslation("adminOps");
  const { data } = props;
  return (
    <div className="ops-stack" data-testid="lifecycle">
      <PageHeader
        title={t("lifecycle.title")}
        description={t("lifecycle.lead")}
      />
      <ViewState
        status={props.status}
        errorText={t("lifecycle.loadFailed")}
        onRetry={props.onRetry}
        testId="lifecycle"
      />
      {props.failure && (
        <div role="alert" style={{ color: "var(--c-err)" }}>
          {t(`failure.${props.failure}`, {
            defaultValue: t("failure.unknown"),
          })}
        </div>
      )}
      {data && (
        <>
          {data.safe_mode && (
            <Banner
              tone="danger"
              title={t("lifecycle.safeMode.title")}
              testId="lc-safe-mode"
            >
              {t("lifecycle.safeMode.body")}
            </Banner>
          )}
          {!data.safe_mode && data.level === "warning" && (
            <Banner tone="warning" title={t("lifecycle.warning.title")}>
              {t("lifecycle.warning.body")}
            </Banner>
          )}
          <Section
            title={t("lifecycle.volumes.title")}
            description={t("lifecycle.volumes.lead")}
            testId="lc-volumes"
            footer={
              <Thresholds
                key={`${String(data.thresholds.warn_percent)}-${String(data.thresholds.critical_percent)}`}
                value={data.thresholds}
                onSave={props.onSetThresholds}
              />
            }
          >
            {data.volumes.map((v) => {
              const pct = Math.round((v.used_ratio ?? 0) * 100);
              return (
                <div
                  key={v.name}
                  className="ops-disk"
                  data-testid={`lc-volume-${v.name}`}
                  data-level={v.level}
                >
                  <div className="ops-disk-figure">
                    <span className="ops-disk-value">
                      {v.used_ratio === null ? "—" : `${String(pct)}%`}
                    </span>
                    <span className="ops-disk-of">
                      {t(
                        `lifecycle.volume.${v.name === "database" ? "database" : "disk"}`,
                        {
                          name: v.name,
                        },
                      )}
                      {": "}
                      {formatFileSize(v.used_bytes)}
                      {v.total_bytes !== null &&
                        ` / ${formatFileSize(v.total_bytes)}`}
                    </span>
                  </div>
                  <div className="ops-bar" role="img" aria-label={v.name}>
                    <span
                      data-part="used"
                      data-tone={
                        v.level === "critical"
                          ? "danger"
                          : v.level === "warning"
                            ? "warning"
                            : "neutral"
                      }
                      style={{ width: `${String(Math.min(100, pct))}%` }}
                    />
                    <span data-part="free" style={{ flex: 1 }} />
                  </div>
                </div>
              );
            })}
          </Section>
          {GROUPS.map((group) => {
            const rows = data.sources.filter((s) => s.group === group);
            if (rows.length === 0) return null;
            return (
              <Section
                key={group}
                title={t(`lifecycle.group.${group}`)}
                testId={`lc-group-${group}`}
              >
                <table className="lc-table">
                  <thead>
                    <tr>
                      <th>{t("lifecycle.col.source")}</th>
                      <th>{t("lifecycle.col.how")}</th>
                      <th>{t("lifecycle.col.size")}</th>
                      <th>{t("lifecycle.col.retention")}</th>
                      <th>{t("lifecycle.col.last")}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => (
                      <SourceRow
                        key={`${s.key}-${String(s.days)}`}
                        source={s}
                        busy={props.busyKey === s.key}
                        onSetRetention={props.onSetRetention}
                        onRun={props.onRun}
                      />
                    ))}
                  </tbody>
                </table>
              </Section>
            );
          })}
        </>
      )}
    </div>
  );
};
