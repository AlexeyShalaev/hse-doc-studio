import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, ShieldCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  classifyOutcomeFailure,
  packOutcomeKeys,
  usePackOutcomeLint,
  type OutcomeElementRef,
  type OutcomeRuleRef,
} from "@entities/pack-studio";
import { EmptyState } from "@shared/ui";
import { useWitnessInputs } from "../lib/applyInput";
import {
  NO_FILTER,
  SEVERITIES,
  countsOf,
  groupFindings,
  rulesOf,
  type LintFilter,
} from "../lib/lint";
import { useOutcomeModel } from "../model";
import { useLabeler } from "../ui/inputs/useLabeler";
import { ModeFailure } from "../ui/ModeFailure";
import { ModeSkeleton } from "../ui/ModeSkeleton";
import { Notice } from "../ui/Notice";
import { useOpenRule } from "../ui/rules/useOpenRule";
import { useScenarioUi } from "../ui/scenarios/context";
import { CoverageBlock } from "./CoverageBlock";
import { LintActionsContext, type LintActions } from "./context";
import { FindingList } from "./FindingList";
import "./lint.css";

/**
 * Режим «Проверка пака» (срез F11): находки линтера результата, сгруппированные по уровню и правилу,
 * с фильтрами и поиском, и покрытие правил сценариями. Всё считает сервер (`outcome/lint`), клиент
 * раскладывает ответ и ставит экран в нужное место: правило, комбинация, элемент результата.
 * Расчёт идёт только пока режим открыт; Jinja-шаблоны проверяются по кнопке (дольше, лимит 6 в минуту).
 */
export const LintPanel = () => {
  const { t } = useTranslation("packOutcome");
  const client = useQueryClient();
  const model = useOutcomeModel();
  const ui = useScenarioUi();
  const { url, workspaceId, ref, released, inputs, phone } = model;
  const state = url.state.state;
  const labeler = useLabeler(inputs.data?.inputs);
  const witnessInputs = useWitnessInputs();
  const { openPlace } = useOpenRule();
  const [filter, setFilter] = useState<LintFilter>(NO_FILTER);
  const [jinjaAsked, setJinjaAsked] = useState(false);
  // Вводные адреса на момент нажатия «Добавить как сценарий»: окно открывается, когда они сменились.
  const createAfter = useRef<Record<string, string> | null>(null);
  const openDialog = ui?.open;
  const inputsNow = url.state.inputs;
  useEffect(() => {
    if (createAfter.current === null || inputsNow === createAfter.current) {
      return;
    }
    createAfter.current = null;
    openDialog?.({ kind: "create" });
  }, [openDialog, inputsNow]);
  const searchId = useId();

  const base = usePackOutcomeLint(workspaceId, ref, { state }, true);
  const canJinja = state === "work_tree";
  // Jinja только на рабочем дереве: на другом состоянии запрос не идёт, кнопка отключена.
  const asked = jinjaAsked && canJinja;
  const jinja = usePackOutcomeLint(
    workspaceId,
    ref,
    { state, jinja: true },
    asked,
  );
  // С Jinja ответ полный (те же правила и ещё рендер): он заменяет статический, когда придёт.
  const data = asked && jinja.data ? jinja.data : base.data;
  const jinjaBusy = asked && jinja.isFetching && !jinja.data;
  const jinjaFailed = asked && jinja.isError && !jinja.data;

  const cancel = (jinjaOnly: boolean) => {
    void client.cancelQueries({
      queryKey: packOutcomeKeys.lint(workspaceId, ref, {
        state,
        jinja: jinjaOnly,
      }),
    });
  };

  const actions: LintActions = {
    labeler,
    showCombination: (witness) => {
      url.update({ inputs: witnessInputs(witness), view: "result" }, true);
    },
    showElement: (element: OutcomeElementRef) => {
      url.update(
        {
          view: "result",
          selected: element,
          ...(phone ? { tab: "rules" as const } : {}),
        },
        true,
      );
    },
    openPlace: (file, pointer) => openPlace(file, pointer),
    openRule: (rule: OutcomeRuleRef) => {
      if (rule.origin !== "manifest" || rule.file === null) return false;
      return openPlace(rule.file, rule.pointer);
    },
    addScenario: (witness) => {
      if (!witness) {
        ui?.open({ kind: "create" });
        return;
      }
      const next = witnessInputs(witness);
      if (JSON.stringify(next) === JSON.stringify(url.state.inputs)) {
        ui?.open({ kind: "create" });
        return;
      }
      // Окно читает вводные из адреса, а на телефоне открытие листа пишет запись истории с адресом
      // «на сейчас»: окно открывается, когда адрес уже обновлён (см. эффект ниже).
      createAfter.current = url.state.inputs;
      url.update({ inputs: next }, true);
    },
    canAddScenario: ui?.canWrite ?? false,
  };

  const findings = useMemo(() => data?.findings ?? [], [data?.findings]);
  const groups = useMemo(
    () => groupFindings(findings, filter, url.state.selected),
    [findings, filter, url.state.selected],
  );
  const rules = useMemo(() => rulesOf(findings), [findings]);
  const filtered =
    filter.severity !== null ||
    filter.rule !== null ||
    filter.query.trim() !== "" ||
    filter.selectedOnly;

  // Итог проверки объявляется один раз на ответ, а не на каждое нажатие в поиске.
  const counts = data ? countsOf(data) : null;
  const [announce, setAnnounce] = useState("");
  const lastRevision = useRef<string | null>(null);
  const announced = data ? `${data.revision}:${data.jinja ?? ""}` : null;
  useEffect(() => {
    if (!data || announced === lastRevision.current) return;
    lastRevision.current = announced;
    const done = countsOf(data);
    setAnnounce(
      t("lint.live", {
        errors: t("lint.counts.errors", { count: done.errors }),
        warnings: t("lint.counts.warnings", { count: done.warnings }),
        infos: t("lint.counts.infos", { count: done.infos }),
      }),
    );
  }, [data, announced, t]);

  if (!data) {
    if (base.isError) {
      return (
        <div className="ln" data-testid="outcome-lint">
          <ModeFailure
            mode="lint"
            error={base.error}
            onRetry={() => void base.refetch()}
          />
        </div>
      );
    }
    if (base.fetchStatus === "idle") {
      return (
        <div className="ln" data-testid="outcome-lint">
          <EmptyState
            framed
            icon={<ShieldCheck size="1.5rem" />}
            title={t("lint.cancelledTitle")}
            description={t("lint.cancelledLead")}
            action={
              <button
                type="button"
                className="btn sm"
                data-testid="outcome-lint-again"
                onClick={() => void base.refetch()}
              >
                {t("lint.again")}
              </button>
            }
            testId="outcome-lint-cancelled"
          />
        </div>
      );
    }
    const waiting = classifyOutcomeFailure(base.failureReason);
    return (
      <div className="ln" data-testid="outcome-lint">
        <div className="ln-loading" role="status">
          <p className="ln-loading-text">
            <RefreshCw size="0.875rem" aria-hidden="true" className="po-spin" />
            {base.failureCount > 0 && waiting.kind === "rate_limited"
              ? t("lint.rateWait", { seconds: waiting.retryAfterS })
              : base.failureCount > 0
                ? t("lint.busyRetry", { count: base.failureCount })
                : t("lint.loading")}
          </p>
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-lint-cancel"
            onClick={() => {
              cancel(false);
            }}
          >
            {t("lint.cancel")}
          </button>
        </div>
        <ModeSkeleton testId="outcome-lint-loading" />
      </div>
    );
  }

  const waitingJinja = classifyOutcomeFailure(jinja.failureReason);
  const empty = findings.length === 0;
  return (
    <LintActionsContext.Provider value={actions}>
      <div
        className="ln"
        data-testid="outcome-lint"
        aria-busy={base.isFetching || jinjaBusy || undefined}
      >
        <div className="ln-head">
          <div>
            <h2 className="ln-title">{t("lint.title")}</h2>
            <p className="ln-summary" data-testid="outcome-lint-summary">
              {counts &&
                t("lint.summary", {
                  errors: t("lint.counts.errors", { count: counts.errors }),
                  warnings: t("lint.counts.warnings", {
                    count: counts.warnings,
                  }),
                  infos: t("lint.counts.infos", { count: counts.infos }),
                })}
              {data.elapsed_ms !== undefined && (
                <span className="po-note">
                  {" "}
                  {t("lint.elapsed", {
                    seconds: (data.elapsed_ms / 1000).toFixed(1),
                  })}
                </span>
              )}
            </p>
          </div>
          <div className="ln-head-actions">
            <button
              type="button"
              className="btn sm"
              data-testid="outcome-lint-recheck"
              disabled={base.isFetching}
              onClick={() => {
                void base.refetch();
              }}
            >
              <RefreshCw
                size="0.8125rem"
                aria-hidden="true"
                className={base.isFetching ? "po-spin" : undefined}
              />
              {t("lint.recheck")}
            </button>
            <button
              type="button"
              className="btn sm"
              data-testid="outcome-lint-jinja"
              disabled={!canJinja || jinjaBusy || data.jinja === "ran"}
              title={
                !canJinja ? t("lint.jinja.notWorkTree") : t("lint.jinja.lead")
              }
              onClick={() => {
                if (jinjaFailed) void jinja.refetch();
                else setJinjaAsked(true);
              }}
            >
              {jinjaBusy ? (
                <RefreshCw
                  size="0.8125rem"
                  aria-hidden="true"
                  className="po-spin"
                />
              ) : (
                <ShieldCheck size="0.8125rem" aria-hidden="true" />
              )}
              {data.jinja === "ran"
                ? t("lint.jinja.done")
                : t("lint.jinja.run")}
            </button>
          </div>
        </div>

        {released && (
          <Notice
            tone="info"
            title={t("lint.released")}
            testId="outcome-lint-released"
          />
        )}
        {data.atlas_skipped === true && (
          <Notice
            tone="info"
            title={t("lint.atlasSkippedTitle")}
            testId="outcome-lint-atlas-skipped"
          >
            {t("lint.atlasSkippedLead")}
          </Notice>
        )}
        {base.isError && (
          <Notice
            tone="error"
            title={t("status.failed")}
            testId="outcome-lint-stale"
            actions={
              <button
                type="button"
                className="btn sm"
                onClick={() => void base.refetch()}
              >
                {t("status.retry")}
              </button>
            }
          >
            {t("lint.stale")}
          </Notice>
        )}
        {jinjaBusy && (
          <div
            className="ln-loading"
            role="status"
            data-testid="outcome-lint-jinja-busy"
          >
            <p className="ln-loading-text">
              <RefreshCw
                size="0.875rem"
                aria-hidden="true"
                className="po-spin"
              />
              {jinja.failureCount > 0 && waitingJinja.kind === "rate_limited"
                ? t("lint.rateWait", { seconds: waitingJinja.retryAfterS })
                : jinja.failureCount > 0
                  ? t("lint.busyRetry", { count: jinja.failureCount })
                  : t("lint.jinja.running")}
            </p>
            <button
              type="button"
              className="btn sm"
              data-testid="outcome-lint-jinja-cancel"
              onClick={() => {
                cancel(true);
                // Отмена оставляет запрос без данных: кнопка «Проверить» снова доступна.
                setJinjaAsked(false);
              }}
            >
              {t("lint.cancel")}
            </button>
          </div>
        )}
        {jinjaFailed && (
          <ModeFailure
            mode="lint"
            error={jinja.error}
            onRetry={() => void jinja.refetch()}
          />
        )}
        {data.jinja === "unavailable" && (
          <p className="po-note" data-testid="outcome-lint-jinja-unavailable">
            {t("lint.jinja.unavailable")}
          </p>
        )}

        <CoverageBlock coverage={data.coverage} />

        <section className="ln-findings" aria-labelledby="ln-findings-title">
          <h3 className="ln-block-title" id="ln-findings-title">
            {t("lint.findingsTitle")}
          </h3>
          <div className="ln-toolbar" role="search">
            <label className="ln-search" htmlFor={searchId}>
              <span className="sr-only">{t("lint.filters.search")}</span>
              <input
                id={searchId}
                type="search"
                className="input"
                placeholder={t("lint.filters.searchPlaceholder")}
                value={filter.query}
                data-testid="outcome-lint-search"
                onChange={(event) => {
                  setFilter({ ...filter, query: event.target.value });
                }}
              />
            </label>
            <div
              className="po-segmented"
              role="group"
              aria-label={t("lint.filters.severity")}
            >
              {([null, ...SEVERITIES] as const).map((value) => (
                <button
                  key={value ?? "all"}
                  type="button"
                  className="po-segment"
                  aria-pressed={filter.severity === value}
                  data-testid={`outcome-lint-severity-${value ?? "all"}`}
                  onClick={() => {
                    setFilter({ ...filter, severity: value });
                  }}
                >
                  {t(`lint.filters.severity_${value ?? "all"}`)}
                </button>
              ))}
            </div>
            {rules.length > 1 && (
              <label className="po-filter-select">
                <span className="po-note">{t("lint.filters.rule")}</span>
                <select
                  className="input"
                  value={filter.rule ?? ""}
                  data-testid="outcome-lint-rule-filter"
                  onChange={(event) => {
                    setFilter({
                      ...filter,
                      rule:
                        event.target.value === "" ? null : event.target.value,
                    });
                  }}
                >
                  <option value="">{t("lint.filters.ruleAll")}</option>
                  {rules.map((item) => (
                    <option key={item.rule} value={item.rule}>
                      {item.rule} ({item.count})
                    </option>
                  ))}
                </select>
              </label>
            )}
            {url.state.selected && (
              <label className="ln-check">
                <input
                  type="checkbox"
                  checked={filter.selectedOnly}
                  data-testid="outcome-lint-selected-only"
                  onChange={(event) => {
                    setFilter({
                      ...filter,
                      selectedOnly: event.target.checked,
                    });
                  }}
                />
                <span>
                  {t("lint.filters.selectedOnly", {
                    id: url.state.selected.id,
                  })}
                </span>
              </label>
            )}
          </div>
          {empty ? (
            <EmptyState
              framed
              icon={<CheckCircle2 size="1.5rem" />}
              title={t("lint.emptyTitle")}
              description={t("lint.emptyLead")}
              testId="outcome-lint-empty"
            />
          ) : groups.length === 0 && filtered ? (
            <EmptyState
              framed
              title={t("lint.noMatchTitle")}
              description={t("lint.noMatchLead")}
              action={
                <button
                  type="button"
                  className="btn sm"
                  data-testid="outcome-lint-reset"
                  onClick={() => {
                    setFilter(NO_FILTER);
                  }}
                >
                  {t("lint.filters.reset")}
                </button>
              }
              testId="outcome-lint-nomatch"
            />
          ) : (
            <FindingList groups={groups} />
          )}
        </section>

        <div
          className="sr-only"
          role="status"
          aria-live="polite"
          data-testid="outcome-lint-live"
        >
          {announce}
        </div>
      </div>
    </LintActionsContext.Provider>
  );
};
