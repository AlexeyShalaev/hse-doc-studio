import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  OutcomeElementRef,
  OutcomeInput,
  PackOutcomeInputs,
} from "@entities/pack-studio";
import { packErrorText } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { EmptyState, Select } from "@shared/ui";
import {
  INPUT_GROUPS,
  baseValue,
  baselineOf,
  exampleDefaultsOf,
  isInert,
  linkedElements,
  withValue,
} from "../lib/inputs";
import { useStoredFlag } from "../lib/panels";
import { useDraftInputs } from "../lib/useDraftInputs";
import { useOutcomeModel } from "../model";
import { InputRow } from "./inputs/InputRow";
import { Notice } from "./Notice";
import { useScenarioUi } from "./scenarios/context";

/** Значение «без сценария»: у выпадающего списка значение не бывает пустым. */
const NO_SCENARIO = "__none__";
const NO_LINKS: OutcomeElementRef[] = [];

const Loading = () => {
  const { t } = useTranslation("packOutcome");
  return (
    <div
      className="po-skeleton"
      aria-busy="true"
      aria-label={t("loading")}
      data-testid="outcome-inputs-loading"
    >
      <div className="shimmer po-skeleton-row" />
      <div className="shimmer po-skeleton-row" data-short="true" />
      <div className="shimmer po-skeleton-row" />
      <div className="shimmer po-skeleton-row" data-short="true" />
    </div>
  );
};

type GroupProps = {
  id: string;
  title: string;
  children: ReactNode;
};

/** Группа вводных: сворачивается, состояние запоминается. */
const Group = ({ id, title, children }: GroupProps) => {
  const [collapsed, setCollapsed] = useStoredFlag(
    `hse-studio.packOutcome.inputs.group.${id}`,
  );
  const uid = useId();
  const Chevron = collapsed ? ChevronRight : ChevronDown;
  return (
    <section
      className="po-inputs-group"
      aria-labelledby={`${uid}-h`}
      data-testid={`outcome-inputs-group-${id}`}
    >
      <h3 className="po-inputs-group-title" id={`${uid}-h`}>
        <button
          type="button"
          className="po-inputs-group-toggle"
          aria-expanded={!collapsed}
          aria-controls={uid}
          onClick={() => {
            setCollapsed(!collapsed);
          }}
        >
          <Chevron size="0.8125rem" aria-hidden="true" />
          {title}
        </button>
      </h3>
      <div id={uid} className="po-inputs-list" hidden={collapsed}>
        {children}
      </div>
    </section>
  );
};

/**
 * Панель «Вводные» (template-studio-outcome.md, раздел 3.3). Строится из ответа сервера `inputs`
 * и записывает выбор в адрес; условий пака в клиенте нет. Контролы живут от черновика, запись в
 * адрес и запрос расчёта идут по паузе (250 мс), прежний запрос отменяется хуком расчёта.
 */
export const InputsPanel = () => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { inputs, url, scenarios, outcome, shown, phone, highlight, select } =
    model;
  const { update } = url;
  const urlInputs = url.state.inputs;
  const scenarioUi = useScenarioUi();

  const commit = useCallback(
    (next: Record<string, string>) => {
      update({ inputs: next, ...(phone ? { tab: "result" as const } : {}) });
    },
    [phone, update],
  );
  const draft = useDraftInputs({
    source: urlInputs,
    at: JSON.stringify([url.state.scenario, url.state.example, urlInputs]),
    commit,
    auto: !phone,
  });
  const overrides = draft.value;

  const data: PackOutcomeInputs | undefined = inputs.data;
  const baseline = useMemo(
    () => (data ? baselineOf(data, scenarios.data, url.state.scenario) : null),
    [data, scenarios.data, url.state.scenario],
  );
  const exampleId = url.state.example ?? baseline?.example ?? "";
  const exampleDefaults = useMemo(
    () => (data ? exampleDefaultsOf(data, exampleId) : {}),
    [data, exampleId],
  );
  // Связи вводных с элементами результата: из трассы показанного ответа, один раз на ответ.
  const links = useMemo(() => {
    const map = new Map<string, OutcomeElementRef[]>();
    for (const input of data?.inputs ?? []) {
      const found = linkedElements(shown, input.id);
      if (found.length > 0) map.set(input.id, found);
    }
    return map;
  }, [data, shown]);

  const bases = useMemo(() => {
    const map = new Map<string, string>();
    if (data && baseline) {
      for (const input of data.inputs) {
        map.set(input.id, baseValue(input, baseline, exampleDefaults));
      }
    }
    return map;
  }, [data, baseline, exampleDefaults]);

  // Обработчики держат последние значения в ссылке: строки не перерисовываются зря.
  const handlers = useRef({ overrides, bases, draft });
  useEffect(() => {
    handlers.current = { overrides, bases, draft };
  });
  const onChange = useCallback((id: string, value: string) => {
    const { overrides: current, bases: base, draft: d } = handlers.current;
    d.set(withValue(current, id, value, base.get(id) ?? ""));
  }, []);
  const onReset = useCallback((id: string) => {
    const { overrides: current, bases: base, draft: d } = handlers.current;
    d.set(withValue(current, id, base.get(id) ?? "", base.get(id) ?? ""), true);
  }, []);

  const [inertOpen, setInertOpen] = useStoredFlag(
    "hse-studio.packOutcome.inputs.inert.open",
  );
  const inertId = useId();

  if (inputs.isPending) return <Loading />;
  if (inputs.isError) {
    return (
      <Notice
        tone="error"
        title={t("inputs.loadFailed")}
        testId="outcome-inputs-error"
        actions={
          <button
            type="button"
            className="btn sm"
            onClick={() => void inputs.refetch()}
          >
            {t("status.retry")}
          </button>
        }
      >
        {packErrorText(inputs.error)}
      </Notice>
    );
  }
  const list = inputs.data.inputs;
  if (list.length === 0) {
    return (
      <EmptyState
        compact
        title={t("inputs.emptyTitle")}
        description={t("inputs.emptyLead")}
        testId="outcome-inputs-empty"
      />
    );
  }

  const lang = i18n.language;
  const changedCount = list.filter(
    (input) =>
      input.id in overrides && overrides[input.id] !== bases.get(input.id),
  ).length;
  const exampleChanged =
    url.state.example !== null && url.state.example !== baseline?.example;
  const anyOverride =
    Object.keys(overrides).length > 0 || url.state.example !== null;
  const scenario = url.state.scenario;

  const resetAll = () => {
    draft.discard();
    update({ inputs: {}, example: null });
  };

  const entries = scenarios.data?.scenarios ?? [];
  const scenarioOptions = [
    { value: NO_SCENARIO, label: t("bar.noScenario") },
    ...entries.map((entry) => {
      const name = pickLocalized(entry.scenario?.name, lang, entry.id);
      return {
        value: entry.id,
        label: entry.error ? t("bar.scenarioBroken", { name }) : name,
        isDisabled: entry.error !== null && entry.id !== scenario,
      };
    }),
    ...(scenario !== null && !entries.some((entry) => entry.id === scenario)
      ? [{ value: scenario, label: t("bar.scenarioMissing", { id: scenario }) }]
      : []),
  ];
  const exampleOptions = [
    ...inputs.data.examples.map((example) => ({
      value: example.id,
      label: pickLocalized(example.label ?? undefined, lang, example.id),
      isDisabled: example.error !== null && example.id !== exampleId,
    })),
    ...(inputs.data.examples.some((example) => example.id === exampleId)
      ? []
      : [{ value: exampleId, label: exampleId }]),
  ];

  const row = (input: OutcomeInput, inert: boolean) => {
    const base = bases.get(input.id) ?? input.default;
    return (
      <InputRow
        key={input.id}
        input={input}
        value={overrides[input.id] ?? base}
        base={base}
        fromScenario={
          baseline !== null &&
          input.id in baseline.scenario &&
          base !== input.default
        }
        inert={inert}
        linked={links.get(input.id) ?? NO_LINKS}
        highlighted={highlight.input === input.id}
        impactOpen={
          url.state.selected?.section === "branches" &&
          url.state.selected.id === input.id
        }
        onChange={onChange}
        onReset={onReset}
        onHighlight={highlight.setInput}
        onSelect={select}
      />
    );
  };

  const active = list.filter((input) => !isInert(input));
  const inert = list.filter(isInert);
  const inertChanged = inert.filter(
    (input) =>
      overrides[input.id] !== undefined &&
      overrides[input.id] !== bases.get(input.id),
  ).length;
  const InertChevron = inertOpen ? ChevronDown : ChevronRight;
  const recalculating = draft.pending || outcome.isFetching;

  return (
    <div className="po-inputs" data-testid="outcome-inputs">
      <div className="po-inputs-meta">
        <span>{t("inputs.total", { count: list.length })}</span>
        <button
          type="button"
          className="po-link"
          disabled={!anyOverride}
          data-testid="outcome-inputs-reset"
          onClick={resetAll}
        >
          {t("inputs.resetAll")}
        </button>
      </div>

      {(entries.length > 0 || scenario !== null) && (
        <div className="po-in-scenario" data-testid="outcome-inputs-scenario">
          <label className="po-in-set-label" htmlFor="po-inputs-scenario">
            {t("inputs.scenario.label")}
          </label>
          <Select
            id="po-inputs-scenario"
            ariaLabel={t("inputs.scenario.quick")}
            className="po-in-select"
            value={scenario ?? NO_SCENARIO}
            options={scenarioOptions}
            onValueChange={(next) => {
              update({ scenario: next === NO_SCENARIO ? null : next });
            }}
          />
          {scenario !== null && changedCount > 0 && (
            <p
              className="po-in-dirty"
              role="status"
              data-testid="outcome-inputs-dirty"
            >
              <span>
                {t("inputs.scenario.changed", { count: changedCount })}
              </span>
              <button
                type="button"
                className="po-link"
                data-testid="outcome-inputs-restore"
                onClick={resetAll}
              >
                {t("inputs.scenario.restore")}
              </button>
              {scenarioUi?.canWrite && (
                <button
                  type="button"
                  className="po-link"
                  data-testid="outcome-inputs-save-into"
                  onClick={() => {
                    scenarioUi.open({ kind: "saveInputs", id: scenario });
                  }}
                >
                  {t("inputs.scenario.saveInto")}
                </button>
              )}
            </p>
          )}
        </div>
      )}

      {INPUT_GROUPS.map((group) => {
        const items = active.filter((input) => input.group === group);
        if (items.length === 0) return null;
        return (
          <Group key={group} id={group} title={t(`inputs.groups.${group}`)}>
            {items.map((input) => row(input, false))}
          </Group>
        );
      })}
      {active.length === 0 && (
        <p className="po-stub" data-testid="outcome-inputs-all-inert">
          {t("inputs.allInert")}
        </p>
      )}

      {inert.length > 0 && (
        <section
          className="po-inputs-group po-inputs-inert"
          aria-labelledby={`${inertId}-h`}
          data-testid="outcome-inputs-inert"
        >
          <h3 className="po-inputs-group-title" id={`${inertId}-h`}>
            <button
              type="button"
              className="po-inputs-group-toggle"
              aria-expanded={inertOpen}
              aria-controls={inertId}
              data-testid="outcome-inputs-inert-toggle"
              onClick={() => {
                setInertOpen(!inertOpen);
              }}
            >
              <InertChevron size="0.8125rem" aria-hidden="true" />
              {t("inputs.inert.title")}
              <span className="po-inputs-count">{inert.length}</span>
              {inertChanged > 0 && !inertOpen && (
                <span className="po-badge" title={t("inputs.inert.changed")}>
                  {inertChanged}
                </span>
              )}
            </button>
          </h3>
          <div id={inertId} className="po-inputs-list" hidden={!inertOpen}>
            <p className="po-stub">{t("inputs.inert.lead")}</p>
            {inertOpen && inert.map((input) => row(input, true))}
          </div>
        </section>
      )}

      {inputs.data.examples.length > 0 && (
        <div className="po-in-example" data-testid="outcome-inputs-example">
          <label className="po-in-set-label" htmlFor="po-inputs-example">
            {t("inputs.example.label")}
          </label>
          <Select
            id="po-inputs-example"
            ariaLabel={t("inputs.example.label")}
            className="po-in-select"
            value={exampleId}
            options={exampleOptions}
            onValueChange={(next) => {
              update({ example: next === baseline?.example ? null : next });
            }}
          />
          <p className="po-in-hint">{t("inputs.example.hint")}</p>
          {exampleChanged && (
            <button
              type="button"
              className="po-link"
              data-testid="outcome-inputs-example-reset"
              onClick={() => {
                update({ example: null });
              }}
            >
              {t("inputs.resetOne", { name: t("inputs.example.label") })}
            </button>
          )}
        </div>
      )}

      {phone && (
        <button
          type="button"
          className="btn primary"
          data-testid="outcome-inputs-apply"
          onClick={() => {
            if (draft.pending) draft.flush();
            else update({ tab: "result" });
          }}
        >
          {t("inputs.apply")}
        </button>
      )}

      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        data-testid="outcome-inputs-live"
      >
        {recalculating ? t("inputs.recalculating") : ""}
      </div>
    </div>
  );
};
