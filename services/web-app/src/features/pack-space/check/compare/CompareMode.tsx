import { useId, useMemo, useState } from "react";
import { ArrowLeftRight, Equal } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  OutcomeSectionSchema,
  usePackOutcomeCompare,
  type OutcomeState,
  type PackOutcomeCompare,
  type PackScenarioEntry,
} from "@entities/pack-studio";
import { EmptyState } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import {
  defaultSides,
  groupBySection,
  resolveSides,
  subjectOf,
} from "@entities/pack-studio/outcome/compare";
import {
  parseSide,
  sameSide,
  type CompareSide,
  type CompareSource,
} from "@entities/pack-studio/outcome/compareSide";
import { mergedInputs } from "@entities/pack-studio/outcome/scenarios";
import { useOutcomeModel } from "@entities/pack-studio/outcome/model";
import { ModeSkeleton } from "./ModeSkeleton";
import { useScenarioUi } from "./scenarioUi";
import { ChangeList } from "./ChangeList";
import { ModeFailure } from "./ModeFailure";

const STATES: readonly OutcomeState[] = ["work_tree", "head", "base"];
const SAME = "same";
const STATE_KEY: Record<OutcomeState, string> = {
  work_tree: "bar.stateWorkTree",
  head: "bar.stateHead",
  base: "bar.stateBase",
};

const sourceValue = (source: CompareSource): string =>
  source.kind === "scenario" ? `scenario:${source.id}` : source.kind;

/**
 * Режим «Сравнить»: две стороны (сценарий, вводные экрана, умолчания или свои вводные, каждая на
 * выбранном состоянии версии) и список изменений по разделам со знаками `+`, `~`, `-`, их словами и
 * причинами из правил. Различия считает сервер (`compare`): клиент выбирает стороны и группирует ответ.
 */
export const CompareMode = () => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const ui = useScenarioUi();
  const { url, workspaceId, ref, scenarios, workspaceKind } = model;
  const git = workspaceKind === "git";
  const entries = useMemo(
    () => ui?.entries ?? scenarios.data?.scenarios ?? [],
    [ui?.entries, scenarios.data?.scenarios],
  );
  const sides = useMemo(
    () => resolveSides(url.state.left, url.state.right, entries, git),
    [url.state.left, url.state.right, entries, git],
  );
  const [onlyDiff, setOnlyDiff] = useState(true);

  const compare = usePackOutcomeCompare(
    workspaceId,
    ref,
    {
      left: subjectOf(sides.left, url.state),
      right: subjectOf(sides.right, url.state),
    },
    // Пока список сценариев не пришёл, стороны по умолчанию неизвестны: лишний запрос не уходит.
    (url.state.left !== null && url.state.right !== null) ||
      !scenarios.isPending,
  );
  const data = compare.data;

  const setSides = (left: CompareSide, right: CompareSide) => {
    url.update({ left, right });
  };
  const scenarioName = (id: string): string => {
    const found = entries.find((entry) => entry.id === id);
    return found?.scenario
      ? pickLocalized(found.scenario.name, i18n.language, id)
      : id;
  };
  const stateWord = (state: OutcomeState | null): string =>
    state === null ? t("modes.compare.stateScreen") : t(STATE_KEY[state]);
  const sideText = (side: CompareSide): string => {
    const { source } = side;
    const what =
      source.kind === "scenario"
        ? t("modes.compare.sourceScenario", { name: scenarioName(source.id) })
        : t(`modes.compare.source_${source.kind}`);
    const state = side.state ?? url.state.state;
    return `${what}, ${stateWord(state)}`;
  };

  const twoScenarios = entries.filter((e) => e.scenario !== null).length >= 2;
  const presets: {
    id: string;
    label: string;
    disabled: boolean;
    apply: () => void;
  }[] = [
    {
      id: "scenarios",
      label: t("modes.compare.presetScenarios"),
      disabled: !twoScenarios,
      apply: () => {
        const next = defaultSides(entries, false);
        setSides(next.left, next.right);
      },
    },
    {
      id: "base",
      label: t("modes.compare.presetBase"),
      disabled: !git,
      apply: () => {
        setSides(
          { source: { kind: "screen" }, state: "base" },
          { source: { kind: "screen" }, state: "work_tree" },
        );
      },
    },
    {
      id: "head",
      label: t("modes.compare.presetHead"),
      disabled: !git,
      apply: () => {
        setSides(
          { source: { kind: "screen" }, state: "head" },
          { source: { kind: "screen" }, state: "work_tree" },
        );
      },
    },
    {
      id: "swap",
      label: t("modes.compare.swap"),
      disabled: false,
      apply: () => {
        setSides(sides.right, sides.left);
      },
    },
  ];

  const frozen = (): Record<string, string> =>
    mergedInputs(scenarios.data, url.state.scenario, url.state.inputs);

  return (
    <div className="cmp" data-testid="outcome-compare">
      <div
        className="cmp-presets"
        role="group"
        aria-label={t("modes.compare.presets")}
      >
        {presets.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className="btn sm"
            disabled={preset.disabled}
            title={
              preset.disabled
                ? t(
                    preset.id === "scenarios"
                      ? "modes.compare.needTwo"
                      : "modes.compare.needGit",
                  )
                : undefined
            }
            data-testid={`outcome-compare-preset-${preset.id}`}
            onClick={preset.apply}
          >
            {preset.id === "swap" && (
              <ArrowLeftRight size="0.875rem" aria-hidden="true" />
            )}
            {preset.label}
          </button>
        ))}
      </div>
      <div className="cmp-sides">
        {(["left", "right"] as const).map((which) => (
          <SidePicker
            key={which}
            which={which}
            side={sides[which]}
            entries={entries}
            scenarioName={scenarioName}
            git={git}
            screenState={url.state.state}
            onChange={(next) => {
              setSides(
                which === "left" ? next : sides.left,
                which === "right" ? next : sides.right,
              );
            }}
            onFreeze={() => {
              const next: CompareSide = {
                source: { kind: "inputs", inputs: frozen() },
                state: sides[which].state,
              };
              setSides(
                which === "left" ? next : sides.left,
                which === "right" ? next : sides.right,
              );
            }}
          />
        ))}
      </div>

      {compare.isError && !data ? (
        <ModeFailure
          mode="compare"
          error={compare.error}
          onRetry={() => void compare.refetch()}
          extra={{
            diff_base_unavailable: (
              <button
                type="button"
                className="btn sm"
                data-testid="outcome-compare-fallback"
                onClick={() => {
                  const next = defaultSides(
                    entries.filter((entry) => entry.scenario !== null),
                    false,
                  );
                  setSides(next.left, next.right);
                }}
              >
                {t("modes.compare.fallback")}
              </button>
            ),
          }}
        />
      ) : !data ? (
        <ModeSkeleton testId="outcome-compare-loading" rows={5} />
      ) : (
        <CompareResult
          data={data}
          sideText={sideText}
          left={sides.left}
          right={sides.right}
          onlyDiff={onlyDiff}
          onOnlyDiff={setOnlyDiff}
          fetching={compare.isFetching}
          stale={compare.isError}
        />
      )}
    </div>
  );
};

type SidePickerProps = {
  which: "left" | "right";
  side: CompareSide;
  entries: readonly PackScenarioEntry[];
  scenarioName: (id: string) => string;
  git: boolean;
  screenState: OutcomeState;
  onChange: (next: CompareSide) => void;
  onFreeze: () => void;
};

const SidePicker = ({
  which,
  side,
  entries,
  scenarioName,
  git,
  screenState,
  onChange,
  onFreeze,
}: SidePickerProps) => {
  const { t } = useTranslation("packOutcome");
  const id = useId();
  const frozen = side.source.kind === "inputs";
  const stateValue = side.state ?? SAME;
  return (
    <fieldset className="cmp-side" data-testid={`outcome-compare-${which}`}>
      <legend className="cmp-side-title">{t(`modes.compare.${which}`)}</legend>
      <label className="po-filter-select" htmlFor={`${id}-source`}>
        <span className="po-note">{t("modes.compare.source")}</span>
        <select
          id={`${id}-source`}
          className="input"
          value={sourceValue(side.source)}
          data-testid={`outcome-compare-${which}-source`}
          onChange={(event) => {
            const next = parseSide(event.target.value);
            if (next) onChange({ source: next.source, state: side.state });
          }}
        >
          <option value="screen">{t("modes.compare.source_screen")}</option>
          <option value="defaults">{t("modes.compare.source_defaults")}</option>
          {entries
            .filter((entry) => entry.scenario !== null)
            .map((entry) => (
              <option key={entry.id} value={`scenario:${entry.id}`}>
                {t("modes.compare.sourceScenario", {
                  name: scenarioName(entry.id),
                })}
              </option>
            ))}
          {frozen && (
            <option value="inputs">{t("modes.compare.source_inputs")}</option>
          )}
        </select>
      </label>
      <label className="po-filter-select" htmlFor={`${id}-state`}>
        <span className="po-note">{t("modes.compare.state")}</span>
        <select
          id={`${id}-state`}
          className="input"
          value={stateValue}
          data-testid={`outcome-compare-${which}-state`}
          onChange={(event) => {
            const raw = event.target.value;
            const state = STATES.find((item) => item === raw) ?? null;
            onChange({ source: side.source, state });
          }}
        >
          <option value={SAME}>
            {t("modes.compare.stateSame", {
              state: t(STATE_KEY[screenState]),
            })}
          </option>
          {STATES.map((state) => (
            <option
              key={state}
              value={state}
              disabled={state !== "work_tree" && !git}
            >
              {t(STATE_KEY[state])}
            </option>
          ))}
        </select>
      </label>
      {!frozen && (
        <button
          type="button"
          className="po-link"
          data-testid={`outcome-compare-${which}-freeze`}
          onClick={onFreeze}
        >
          {t("modes.compare.freeze")}
        </button>
      )}
      {frozen && side.source.kind === "inputs" && (
        <p className="po-note">
          {t("modes.compare.frozenCount", {
            count: Object.keys(side.source.inputs).length,
          })}
        </p>
      )}
    </fieldset>
  );
};

type ResultProps = {
  data: PackOutcomeCompare;
  sideText: (side: CompareSide) => string;
  left: CompareSide;
  right: CompareSide;
  onlyDiff: boolean;
  onOnlyDiff: (next: boolean) => void;
  fetching: boolean;
  stale: boolean;
};

const CompareResult = ({
  data,
  sideText,
  left,
  right,
  onlyDiff,
  onOnlyDiff,
  fetching,
  stale,
}: ResultProps) => {
  const { t } = useTranslation("packOutcome");
  const toggleId = useId();
  const groups = useMemo(() => groupBySection(data.changes), [data.changes]);
  const deltas = new Map(data.summary.map((delta) => [delta.section, delta]));
  const same = sameSide(left, right);

  if (data.identical) {
    return (
      <div aria-busy={fetching || undefined}>
        <EmptyState
          framed
          icon={<Equal size="1.5rem" />}
          title={t("modes.compare.identicalTitle")}
          description={
            same
              ? t("modes.compare.identicalSame")
              : t("modes.compare.identicalLead", {
                  left: sideText(left),
                  right: sideText(right),
                })
          }
          testId="outcome-compare-identical"
        />
      </div>
    );
  }

  const shown = onlyDiff
    ? groups
    : OutcomeSectionSchema.options.map((section) => ({
        section,
        changes: data.changes.filter((change) => change.section === section),
      }));
  const total = data.changes.length;
  const sections = groups.length;

  return (
    <div className="cmp-result" aria-busy={fetching || undefined}>
      <div className="cmp-head">
        <p
          className="cmp-summary"
          role="status"
          data-testid="outcome-compare-summary"
        >
          {t("modes.compare.summary", { total, sections })}
        </p>
        <label className="cmp-only" htmlFor={toggleId}>
          <input
            id={toggleId}
            type="checkbox"
            checked={onlyDiff}
            data-testid="outcome-compare-only"
            onChange={(event) => {
              onOnlyDiff(event.target.checked);
            }}
          />
          {t("modes.compare.onlyDiff")}
        </label>
      </div>
      {stale && (
        <p className="po-note" role="alert">
          {t("result.stale")}
        </p>
      )}
      <p className="po-note cmp-sides-text">
        {t("modes.compare.left")}: {sideText(left)}. {t("modes.compare.right")}:{" "}
        {sideText(right)}.
      </p>
      {shown.map(({ section, changes }) => {
        const delta = deltas.get(section);
        return (
          <section
            key={section}
            className="cmp-section"
            aria-label={t(`sections.${section}`)}
            data-testid={`outcome-compare-section-${section}`}
          >
            <h3 className="cmp-section-title">
              {t(`sections.${section}`)}
              {delta && (
                <span className="cmp-counts">
                  {delta.added > 0 && (
                    <span data-symbol="added">
                      {`+${String(delta.added)} ${t("scenarios.diff.added").toLowerCase()}`}
                    </span>
                  )}
                  {delta.changed > 0 && (
                    <span data-symbol="changed">
                      {`~${String(delta.changed)} ${t("scenarios.diff.changed").toLowerCase()}`}
                    </span>
                  )}
                  {delta.removed > 0 && (
                    <span data-symbol="removed">
                      {`−${String(delta.removed)} ${t("scenarios.diff.removed").toLowerCase()}`}
                    </span>
                  )}
                </span>
              )}
            </h3>
            {changes.length > 0 ? (
              <ChangeList
                changes={changes}
                withWhy
                testId={`outcome-compare-changes-${section}`}
              />
            ) : (
              <p className="po-note">{t("modes.compare.sectionSame")}</p>
            )}
          </section>
        );
      })}
    </div>
  );
};
