import { useEffect, useId, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  CircleAlert,
  CircleCheck,
  CircleMinus,
  CirclePlus,
  ChevronRight,
  TriangleAlert,
  X,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  classifyOutcomeFailure,
  packErrorText,
  packOutcomeKeys,
  packOutcomePath,
  packRulePath,
  usePackGit,
  usePackOutcomeImpact,
  usePackOutcomeInputs,
  usePackTree,
  type DiffBaseReason,
  type ImpactScenario,
  type PackOutcomeImpact,
  type PackVersionRef,
} from "@entities/pack-studio";
import { useIsPhoneWidth } from "@shared/lib";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { groupBySection } from "@entities/pack-studio/outcome/compare";
import {
  countChanges,
  impactSummaryText,
  impactVerdict,
  totalDelta,
  versionKey,
} from "@entities/pack-studio/outcome/impact";
import { ruleLocation } from "@entities/pack-studio/outcome/rules";
import {
  ChangeEnvContext,
  type ChangeEnv,
} from "../../check/compare/changeEnv";
import { ChangeList } from "../../check/compare/ChangeList";

export type VersionReport = {
  /** Расчёт идёт: до ответа не ясно, нужна ли отметка. */
  pending: boolean;
  /** Есть изменившиеся или упавшие сценарии: нужна отметка «я знаю». */
  needsAck: boolean;
  /** Компактный текст для тела PR; пусто, если результат не менялся или расчёта нет. */
  summary: string;
};

type VersionImpactProps = {
  workspaceId: string;
  version: PackVersionRef;
  /** Над блоком подпись версии (когда версий в PR несколько). */
  titled: boolean;
  onReport: (key: string, report: VersionReport) => void;
  /** Диалог закрывается перед переходом к правилу в режиме «Файлы». */
  onLeave?: (() => void) | undefined;
  /** Адрес возврата из режима «Файлы»; по умолчанию экран «Результат» этой версии. */
  backTo?: string | undefined;
  /** Создать сценарий на месте (экран «Результат»); без него ссылка на экран «Результат» версии. */
  onCreateScenario?: ((version: PackVersionRef) => void) | undefined;
};

/** Сколько секунд идёт расчёт; вне расчёта 0. */
const useElapsed = (active: boolean): number => {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return undefined;
    const start = Date.now();
    const timer = setInterval(() => {
      setSeconds(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, [active]);
  return active ? seconds : 0;
};

const Counts = ({
  added,
  changed,
  removed,
}: {
  added: number;
  changed: number;
  removed: number;
}) => {
  const { t } = useTranslation("packOutcome");
  return (
    <span className="cmp-counts imp-counts">
      <span
        data-symbol="added"
        title={t("impact.counts.added", { count: added })}
      >
        <span aria-hidden="true">+ {added}</span>
        <span className="sr-only">
          {t("impact.counts.added", { count: added })}
        </span>
      </span>
      <span
        data-symbol="changed"
        title={t("impact.counts.changed", { count: changed })}
      >
        <span aria-hidden="true">~ {changed}</span>
        <span className="sr-only">
          {t("impact.counts.changed", { count: changed })}
        </span>
      </span>
      <span
        data-symbol="removed"
        title={t("impact.counts.removed", { count: removed })}
      >
        <span aria-hidden="true">− {removed}</span>
        <span className="sr-only">
          {t("impact.counts.removed", { count: removed })}
        </span>
      </span>
    </span>
  );
};

const STATUS_ICON = {
  unchanged: CircleCheck,
  changed: CirclePlus,
  error: CircleAlert,
} as const;

const ScenarioRow = ({ scenario }: { scenario: ImpactScenario }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const [open, setOpen] = useState(scenario.status === "error");
  const panel = useId();
  const Icon = STATUS_ICON[scenario.status];
  const name = pickLocalized(scenario.name, i18n.language, scenario.scenario);
  const n = countChanges(scenario.changes);
  const expandable = scenario.status !== "unchanged";
  const groups = useMemo(
    () => groupBySection(scenario.changes),
    [scenario.changes],
  );
  const head = (
    <>
      <span className="imp-sc-status" data-status={scenario.status}>
        <Icon size="0.875rem" aria-hidden="true" />
        <span>{t(`impact.status.${scenario.status}`)}</span>
      </span>
      <span className="imp-sc-name">{name}</span>
      {scenario.status === "changed" && <Counts {...n} />}
    </>
  );
  return (
    <li
      className="imp-sc"
      data-status={scenario.status}
      data-testid={`impact-scenario-${scenario.scenario}`}
    >
      {expandable ? (
        <button
          type="button"
          className="imp-sc-head"
          aria-expanded={open}
          aria-controls={panel}
          data-testid={`impact-scenario-toggle-${scenario.scenario}`}
          onClick={() => {
            setOpen(!open);
          }}
        >
          <ChevronRight
            size="0.875rem"
            aria-hidden="true"
            className="imp-chevron"
            data-open={open ? "true" : undefined}
          />
          {head}
        </button>
      ) : (
        <div className="imp-sc-head imp-sc-static">{head}</div>
      )}
      {expandable && open && (
        <div id={panel} className="imp-sc-body">
          {scenario.status === "error" && (
            <p className="imp-error-text" data-testid="impact-scenario-message">
              {scenario.message ?? t("impact.scenarioErrorPlain")}
            </p>
          )}
          {groups.map((group) => (
            <section
              key={group.section}
              aria-label={t(`sections.${group.section}`)}
            >
              <h5 className="imp-section-title">
                {t(`sections.${group.section}`)}
              </h5>
              <ChangeList
                changes={group.changes}
                withWhy
                testId={`impact-changes-${scenario.scenario}-${group.section}`}
              />
            </section>
          ))}
        </div>
      )}
    </li>
  );
};

/** Почему базы нет и что делать: текст и (или) действие по причине `diff_base_unavailable`. */
const NoBase = ({ reason }: { reason: DiffBaseReason | null }) => {
  const { t } = useTranslation("packOutcome");
  const key = reason ?? "unknown";
  return (
    <div
      className="imp-note"
      data-tone="info"
      role="status"
      data-testid={`impact-no-base-${key}`}
    >
      <CircleMinus size="1rem" aria-hidden="true" className="imp-note-icon" />
      <div>
        <p className="imp-note-title">{t(`impact.noBase.${key}.title`)}</p>
        <p className="imp-note-lead">{t(`impact.noBase.${key}.lead`)}</p>
      </div>
    </div>
  );
};

/**
 * Один расчёт «до и после» версии: база и рабочее дерево по всем сценариям шаблона и атласу.
 * Результат считает сервер (`impact`), здесь он раскладывается по статусам, разделам и причинам.
 * Расчёт идёт, только пока диалог открыт; кэш общий с экраном (`packOutcomeKeys`), повтор без
 * изменений уходит условным запросом (ETag) и отвечается 304.
 */
export const VersionImpact = ({
  workspaceId,
  version,
  titled,
  onReport,
  onLeave,
  backTo,
  onCreateScenario,
}: VersionImpactProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const navigate = useNavigate();
  const client = useQueryClient();
  const phone = useIsPhoneWidth();
  const tree = usePackTree(workspaceId);
  const released =
    tree.data?.packs
      .find((p) => p.id === version.pack)
      ?.templates.find((tpl) => tpl.id === version.template)
      ?.versions.find((v) => v.version === version.version)?.released ?? false;
  const [cancelled, setCancelled] = useState(false);
  // Версия появилась в рабочем дереве целиком (её `version.yaml` добавлен): в основной ветке её нет,
  // сравнивать не с чем. Сервер ответил бы 409, а браузер пишет такой ответ красным в консоль,
  // поэтому запрос не уходит, а вывод «сравнивать не с чем» тот же.
  // Список изменений только читается из кэша (его уже держит панель «Изменения» или диалог
  // отправки): своего запроса блок не делает, но ждёт, пока чужой запрос идёт.
  const git = usePackGit(workspaceId, false);
  const versionYaml = `${version.pack}/templates/${version.template}/versions/${version.version}/version.yaml`;
  const isNew =
    git.data?.changed.some(
      (change) => change.status === "added" && change.path === versionYaml,
    ) ?? false;
  const impact = usePackOutcomeImpact(
    workspaceId,
    version,
    { base: "base", include_atlas: true },
    !cancelled && !released && !tree.isPending && !git.isFetching && !isNew,
  );
  const inputs = usePackOutcomeInputs(
    workspaceId,
    version,
    "work_tree",
    impact.data !== undefined,
  );
  const data = impact.data;
  const loading =
    !released && !cancelled && !isNew && data === undefined && !impact.isError;
  const elapsed = useElapsed(loading);

  const key = versionKey(version);
  const verdict = data ? impactVerdict(data) : null;
  const summary = useMemo(
    () =>
      data
        ? impactSummaryText(t, i18n.language, [{ ref: version, impact: data }])
        : "",
    [data, t, i18n.language, version],
  );
  const needsAck = verdict?.needsAck ?? false;
  useEffect(() => {
    onReport(key, { pending: loading, needsAck, summary });
  }, [key, loading, needsAck, summary, onReport]);

  const env = useMemo<ChangeEnv>(() => {
    const versionPath = `${version.pack}/templates/${version.template}/versions/${version.version}`;
    return {
      inputs: inputs.data?.inputs,
      phone,
      locate: (rule) => ruleLocation(versionPath, rule),
      open: (rule) => {
        const where = ruleLocation(versionPath, rule);
        if (!where) return;
        onLeave?.();
        void navigate(
          packRulePath(workspaceId, where.file, {
            pointer: where.pointer,
            pane: where.form ? "form" : "source",
            from: backTo ?? packOutcomePath(workspaceId, version),
          }),
        );
      },
    };
  }, [
    inputs.data?.inputs,
    phone,
    onLeave,
    backTo,
    navigate,
    workspaceId,
    version,
  ]);

  const cancel = () => {
    setCancelled(true);
    void client.cancelQueries({
      queryKey: packOutcomeKeys.impact(workspaceId, version, {}),
    });
  };
  const retry = () => {
    if (cancelled) setCancelled(false);
    else void impact.refetch();
  };

  const title = titled ? (
    <h4 className="imp-version">
      {version.pack} / {version.template}{" "}
      <span className="po-mono">{version.version}</span>
    </h4>
  ) : null;

  let body: React.ReactNode;
  if (released) {
    body = (
      <div
        className="imp-note"
        data-tone="info"
        role="status"
        data-testid="impact-released"
      >
        <CircleMinus size="1rem" aria-hidden="true" className="imp-note-icon" />
        <div>
          <p className="imp-note-title">{t("impact.released.title")}</p>
          <p className="imp-note-lead">
            {t("impact.released.lead", { version: version.version })}
          </p>
        </div>
      </div>
    );
  } else if (isNew) {
    body = <NoBase reason="new_version" />;
  } else if (cancelled) {
    body = (
      <div
        className="imp-note"
        data-tone="info"
        role="status"
        data-testid="impact-cancelled"
      >
        <CircleMinus size="1rem" aria-hidden="true" className="imp-note-icon" />
        <div>
          <p className="imp-note-title">{t("impact.cancelled.title")}</p>
          <p className="imp-note-lead">{t("impact.cancelled.lead")}</p>
        </div>
        <button
          type="button"
          className="btn sm"
          data-testid="impact-retry"
          onClick={retry}
        >
          {t("impact.run")}
        </button>
      </div>
    );
  } else if (data === undefined && impact.isError) {
    body = <ImpactFailure error={impact.error} onRetry={retry} />;
  } else if (data === undefined) {
    const waiting = classifyOutcomeFailure(impact.failureReason);
    body = (
      <div
        className="imp-wait"
        role="status"
        aria-busy="true"
        data-testid="impact-loading"
      >
        <p className="imp-wait-text">
          {waiting.kind === "busy"
            ? t("impact.busyRetry", { seconds: waiting.retryAfterS })
            : t("impact.loading", { seconds: elapsed })}
        </p>
        <div
          className="imp-progress"
          role="progressbar"
          aria-label={t("impact.progress")}
        >
          <span className="imp-progress-bar" />
        </div>
        <div className="po-skeleton" aria-hidden="true">
          <span className="po-skeleton-row shimmer" />
          <span className="po-skeleton-row shimmer" data-short="true" />
        </div>
        <button
          type="button"
          className="btn sm"
          data-testid="impact-cancel"
          onClick={cancel}
        >
          <X size="0.75rem" aria-hidden="true" />
          {t("impact.cancel")}
        </button>
      </div>
    );
  } else {
    body = (
      <ImpactResult
        data={data}
        version={version}
        workspaceId={workspaceId}
        onCreateScenario={onCreateScenario}
        refreshing={impact.isFetching}
      />
    );
  }

  return (
    <ChangeEnvContext.Provider value={env}>
      <div className="imp-version-block" data-testid={`impact-version-${key}`}>
        {title}
        {body}
      </div>
    </ChangeEnvContext.Provider>
  );
};

const ImpactFailure = ({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) => {
  const { t } = useTranslation("packOutcome");
  const failure = classifyOutcomeFailure(error);
  if (failure.kind === "diff_base_unavailable") {
    return <NoBase reason={failure.reason} />;
  }
  let title: string;
  let lead: string;
  let testId = "impact-error";
  if (failure.kind === "busy") {
    title = t("impact.busyTitle");
    lead = t("impact.busyLead", { seconds: failure.retryAfterS });
    testId = "impact-busy";
  } else if (failure.kind === "outcome_too_large") {
    title = t("impact.tooLargeTitle");
    lead = t("impact.tooLargeLead");
    testId = "impact-too-large";
  } else if (failure.kind === "offline") {
    title = t("impact.offlineTitle");
    lead = t("impact.offlineLead");
  } else {
    title = t("impact.failedTitle");
    lead = packErrorText(error);
  }
  return (
    <div
      className="imp-note"
      data-tone="error"
      role="alert"
      data-testid={testId}
    >
      <CircleAlert size="1rem" aria-hidden="true" className="imp-note-icon" />
      <div>
        <p className="imp-note-title">{title}</p>
        <p className="imp-note-lead">{lead}</p>
        <p className="imp-note-lead">{t("impact.notBlocking")}</p>
      </div>
      <button
        type="button"
        className="btn sm"
        data-testid="impact-retry"
        onClick={onRetry}
      >
        {t("status.retry")}
      </button>
    </div>
  );
};

type ImpactResultProps = {
  data: PackOutcomeImpact;
  version: PackVersionRef;
  workspaceId: string;
  refreshing: boolean;
  onCreateScenario: ((version: PackVersionRef) => void) | undefined;
};

const ImpactResult = ({
  data,
  version,
  workspaceId,
  refreshing,
  onCreateScenario,
}: ImpactResultProps) => {
  const { t } = useTranslation("packOutcome");
  const { summary } = data;
  const verdict = impactVerdict(data);
  const delta = totalDelta(summary.sections);
  const noScenarios = summary.scenarios_total === 0;
  const touched = verdict.changed + verdict.errors;
  const headline = noScenarios
    ? t("impact.headNoScenarios")
    : touched > 0
      ? t("impact.headChanged", {
          changed: touched,
          total: summary.scenarios_total,
          count: summary.scenarios_total,
        })
      : t("impact.headSame", {
          total: summary.scenarios_total,
          count: summary.scenarios_total,
        });
  const atlas = summary.atlas;
  return (
    <div
      className="imp-result"
      aria-busy={refreshing}
      data-testid="impact-result"
    >
      <p
        className="imp-headline"
        role="status"
        data-kind={noScenarios ? "none" : touched > 0 ? "changed" : "same"}
        data-testid="impact-headline"
      >
        {touched > 0 ? (
          <TriangleAlert size="1rem" aria-hidden="true" />
        ) : (
          <CircleCheck size="1rem" aria-hidden="true" />
        )}
        <span>{headline}</span>
      </p>
      {delta.added + delta.changed + delta.removed > 0 && (
        <div className="imp-delta" data-testid="impact-sections">
          <Counts {...delta} />
          <ul className="imp-sections">
            {summary.sections
              .filter((s) => s.added + s.changed + s.removed > 0)
              .map((s) => (
                <li key={s.section}>
                  <span>{t(`sections.${s.section}`)}</span>
                  <Counts
                    added={s.added}
                    changed={s.changed}
                    removed={s.removed}
                  />
                </li>
              ))}
          </ul>
        </div>
      )}
      <p className="imp-atlas" data-testid="impact-atlas">
        {atlas === null
          ? t("impact.atlasNull")
          : atlas.rows_changed === 0
            ? t("impact.atlasSame", {
                total: atlas.rows_total,
                outcomes: atlas.outcomes_after,
              })
            : t("impact.atlas", {
                changed: atlas.rows_changed,
                total: atlas.rows_total,
                before: atlas.outcomes_before,
                after: atlas.outcomes_after,
              })}
      </p>
      {noScenarios && (
        <div
          className="imp-note"
          data-tone="info"
          role="status"
          data-testid="impact-no-scenarios"
        >
          <CircleMinus
            size="1rem"
            aria-hidden="true"
            className="imp-note-icon"
          />
          <div>
            <p className="imp-note-title">{t("impact.noScenarios.title")}</p>
            <p className="imp-note-lead">{t("impact.noScenarios.lead")}</p>
          </div>
          {onCreateScenario ? (
            <button
              type="button"
              className="btn sm"
              data-testid="impact-create-scenario"
              onClick={() => {
                onCreateScenario(version);
              }}
            >
              {t("impact.noScenarios.create")}
            </button>
          ) : (
            <Link
              className="btn sm"
              to={packOutcomePath(workspaceId, version)}
              data-testid="impact-create-scenario"
            >
              {t("impact.noScenarios.open")}
            </Link>
          )}
        </div>
      )}
      {summary.scenarios_total > 0 && (
        <ul
          className="imp-scenarios"
          aria-label={t("impact.scenarios")}
          data-testid="impact-scenarios"
        >
          {data.scenarios.map((scenario) => (
            <ScenarioRow key={scenario.scenario} scenario={scenario} />
          ))}
        </ul>
      )}
      {data.new_findings.length > 0 && (
        <section
          className="imp-findings"
          aria-label={t("impact.findings")}
          data-testid="impact-findings"
        >
          <h5 className="imp-section-title">{t("impact.findings")}</h5>
          <Link
            className="po-link"
            to={packOutcomePath(workspaceId, version, "view=lint")}
            data-testid="impact-findings-open"
          >
            {t("lint.brief.open")}
          </Link>
          <ul>
            {data.new_findings.map((finding, index) => (
              <li
                key={`${finding.rule_id}-${String(index)}`}
                data-severity={finding.severity}
              >
                <TriangleAlert size="0.8125rem" aria-hidden="true" />
                <span className="sr-only">
                  {t(`impact.severity.${finding.severity}`)}:{" "}
                </span>
                <span>{finding.message}</span>
                {finding.file && (
                  <span className="po-mono imp-finding-file">
                    {finding.file}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
};
