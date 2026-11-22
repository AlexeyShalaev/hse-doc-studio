import { useId, useMemo, useState } from "react";
import { Pin, PinOff, RefreshCw, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  classifyOutcomeFailure,
  usePackOutcomeAtlas,
  usePackScenarios,
  type AtlasDimension,
  type OutcomeInput,
  type PackOutcomeAtlas,
} from "@entities/pack-studio";
import {
  EMPTY_FILTER,
  type AtlasFilter,
  applyRowInputs,
  filterRows,
  keyOfInputs,
  mergedInputs,
  miniOf,
  type Labeler,
} from "@features/pack-outcome/check";
import { Badge } from "@shared/ui";
import { useSpace } from "../context/SpaceContext";
import { useSituation } from "../context/useSituation";
import { useSpaceNav } from "../context/useSpaceNav";
import { CheckFailure } from "./CheckFailure";
import { pinParam } from "./lib";
import { useCheckEnv } from "./useCheckEnv";

/** Сколько вариантов показывать за раз: сотни строк листаются кнопкой, страница не тормозит. */
const PAGE = 60;
/** Сколько условий предлагать зафиксировать, когда вариантов слишком много. */
const FIX_CHOICES = 12;

/** Закрепления и пример данных из адреса: `p.<условие>=<значение>`, `example`. */
const useMapQuery = () => {
  const { location } = useSpace();
  return useMemo(() => {
    const params = new URLSearchParams(location.search);
    const pin: Record<string, string> = {};
    params.forEach((value, name) => {
      if (name.startsWith("p.") && value !== "") pin[name.slice(2)] = value;
    });
    return { pin, example: params.get("example") };
  }, [location.search]);
};

/**
 * «Что на что влияет»: какие условия студента меняют результат и во что (карточки условий с
 * «Меняет: ...»), сколько всего получается разных вариантов, а сами варианты за кнопкой «Показать
 * все варианты». Таблицу считает сервер (секунды, ответ кэшируется); значение условия можно
 * зафиксировать, чтобы таблица стала короче.
 */
export const MapPart = () => {
  const { t } = useTranslation("packSpace");
  const env = useCheckEnv();
  const { pin, example } = useMapQuery();
  const request = useMemo(
    () => ({ state: "work_tree" as const, example, pin }),
    [example, pin],
  );
  const atlas = usePackOutcomeAtlas(env.workspaceId, env.ref, request, true);
  const data = atlas.data;
  const nav = useSpaceNav();
  const fix = (input: string, value: string | null) => {
    nav.go({ extra: { [pinParam(input)]: value } });
  };

  if (atlas.isError && !data) {
    const tooMany =
      classifyOutcomeFailure(atlas.error).kind === "atlas_too_large";
    return (
      <div className="sp-ck-stack">
        <CheckFailure
          kind="map"
          error={atlas.error}
          noRetry={tooMany}
          onRetry={() => void atlas.refetch()}
        />
        {tooMany && (
          <FixChooser
            inputs={env.inputs.data?.inputs}
            labeler={env.labeler}
            pin={pin}
            onFix={fix}
          />
        )}
      </div>
    );
  }
  if (!data) {
    return (
      <p className="sp-ck-loading" role="status">
        <RefreshCw size="0.875rem" aria-hidden="true" className="sp-ck-spin" />
        {atlas.failureCount > 0
          ? t("check.map.busyRetry", { count: atlas.failureCount })
          : t("check.map.loading")}
      </p>
    );
  }
  return (
    <MapView
      atlas={data}
      pin={pin}
      fetching={atlas.isFetching}
      stale={atlas.isError}
      onFix={fix}
    />
  );
};

const MapView = ({
  atlas,
  pin,
  fetching,
  stale,
  onFix,
}: {
  atlas: PackOutcomeAtlas;
  pin: Readonly<Record<string, string>>;
  fetching: boolean;
  stale: boolean;
  onFix: (input: string, value: string | null) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const { t: tOld } = useTranslation("packOutcome");
  const env = useCheckEnv();
  const nav = useSpaceNav();
  const { inputs: current, caseId } = useSituation();
  const { pack, template } = env.ref;
  const scenarios = usePackScenarios(env.workspaceId, pack, template, true);
  const labeler = env.labeler;
  const { location } = useSpace();
  const urlParams = new URLSearchParams(location.search);
  // Показ вариантов и способ группировки держатся в адресе: ссылка открывает тот же вид.
  const shown = urlParams.get("all") === "1";
  const group: "rows" | "outcomes" =
    urlParams.get("group") === "outcomes" ? "outcomes" : "rows";
  const setShown = (next: boolean) => {
    nav.go({ extra: { all: next ? "1" : null } });
  };
  const setGroup = (next: "rows" | "outcomes") => {
    nav.go({ extra: { group: next === "outcomes" ? "outcomes" : null } });
  };
  const [filter, setFilter] = useState<AtlasFilter>(EMPTY_FILTER);
  const [limit, setLimit] = useState(PAGE);
  const searchId = useId();
  const query = filter.query;
  const changeFilter = (next: AtlasFilter) => {
    setFilter(next);
    setLimit(PAGE);
  };

  const inputById = new Map(
    (env.inputs.data?.inputs ?? []).map((input) => [input.id, input]),
  );
  const outcomes = useMemo(
    () => new Map(atlas.outcomes.map((outcome) => [outcome.id, outcome])),
    [atlas.outcomes],
  );
  const rows = useMemo(
    () => filterRows(atlas, filter, labeler.value),
    [atlas, filter, labeler.value],
  );
  /** Номер варианта результата: порядок в ответе сервера, с единицы. */
  const numberOf = useMemo(
    () =>
      new Map(atlas.outcomes.map((outcome, index) => [outcome.id, index + 1])),
    [atlas.outcomes],
  );
  const outcomeList = useMemo(() => {
    const list = [...atlas.outcomes];
    if (filter.sort === "rows") list.sort((a, b) => b.rows - a.rows);
    return list;
  }, [atlas.outcomes, filter.sort]);
  const currentKey = keyOfInputs(
    atlas.dimensions,
    mergedInputs(scenarios.data, caseId, current),
  );
  const pinned = Object.entries(pin);
  const currentRow = atlas.rows.find((row) => row.key === currentKey);
  const currentOutcome = currentRow
    ? outcomes.get(currentRow.outcome)
    : undefined;
  const filterActive =
    filter.query !== "" ||
    filter.outcome !== null ||
    Object.values(filter.dims).some((value) => value !== "");

  return (
    <div className="sp-ck-stack" aria-busy={fetching || undefined}>
      <p className="sp-ck-summary-line" role="status">
        {t("check.map.summary", {
          variants: atlas.outcomes_distinct,
          combinations: atlas.combinations_total,
        })}
      </p>
      {stale && (
        <p className="sp-ck-note" role="alert">
          {t("check.map.stale")}
        </p>
      )}

      <section
        className="sp-ck-now"
        aria-label={t("check.map.nowLabel")}
        data-testid="map-now"
      >
        <p className="sp-ck-note">{t("check.map.nowTitle")}</p>
        {currentOutcome ? (
          <p className="sp-ck-now-line">
            <span className="sp-ck-current">
              {t("check.map.outcomeLabel", {
                n: numberOf.get(currentOutcome.id) ?? 0,
              })}
            </span>{" "}
            <span className="sp-ck-note">
              {t("check.map.mini", miniOf(currentOutcome.digest))}
            </span>
          </p>
        ) : (
          <p className="sp-ck-note" data-testid="map-now-none">
            {t("check.map.nowNone")}
          </p>
        )}
      </section>

      {atlas.dimensions.length === 0 ? (
        <p className="sp-ck-note">{t("check.map.noDimensions")}</p>
      ) : (
        <ul className="sp-ck-dims" aria-label={t("check.map.dimsLabel")}>
          {atlas.dimensions.map((dim) => (
            <DimensionCard
              key={dim.input}
              dim={dim}
              input={inputById.get(dim.input)}
              labeler={labeler}
              fixed={pin[dim.input]}
              onFix={(value) => {
                onFix(dim.input, value);
              }}
            />
          ))}
        </ul>
      )}

      {pinned.length > 0 && (
        <p className="sp-ck-fixed">
          <Pin size="0.875rem" aria-hidden="true" />
          <span>{t("check.map.fixed")}</span>
          {pinned.map(([input, value]) => (
            <button
              key={input}
              type="button"
              className="sp-ck-chip"
              aria-label={t("check.map.unfix", {
                name: labeler.input(input),
                value: labeler.value(input, value),
              })}
              onClick={() => {
                onFix(input, null);
              }}
            >
              {labeler.input(input)}: {labeler.value(input, value)}
              <X size="0.75rem" aria-hidden="true" />
            </button>
          ))}
        </p>
      )}

      {atlas.ignored.length > 0 && (
        <details className="sp-ck-tech">
          <summary>
            {t("check.map.ignored", { count: atlas.ignored.length })}
          </summary>
          <ul className="sp-ck-plain">
            {atlas.ignored.map((item) => (
              <li key={item.input}>
                {labeler.input(item.input)}{" "}
                <span className="sp-ck-note">
                  {tOld(`modes.atlas.reason.${item.reason}`)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div>
        <button
          type="button"
          className="btn sm"
          aria-expanded={shown}
          onClick={() => {
            setShown(!shown);
          }}
        >
          {shown ? t("check.map.hideVariants") : t("check.map.showVariants")}
        </button>
      </div>

      {shown && (
        <section
          aria-label={t("check.map.variantsLabel")}
          className="sp-ck-stack"
        >
          <div className="sp-ck-toolbar" role="search">
            <label className="sp-ck-search" htmlFor={searchId}>
              <span className="sr-only">{t("check.map.search")}</span>
              <input
                id={searchId}
                type="search"
                className="input"
                placeholder={t("check.map.searchPlaceholder")}
                value={query}
                onChange={(event) => {
                  changeFilter({ ...filter, query: event.target.value });
                }}
              />
            </label>
            <div
              className="sp-ck-seg"
              role="group"
              aria-label={t("check.map.group.label")}
            >
              {(["rows", "outcomes"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={group === value}
                  data-testid={`map-group-${value}`}
                  onClick={() => {
                    setGroup(value);
                    setLimit(PAGE);
                  }}
                >
                  {t(`check.map.group.${value}`)}
                </button>
              ))}
            </div>
            <label className="sp-ck-field sp-ck-inline">
              <span className="sp-ck-note">{t("check.map.sort.label")}</span>
              <select
                className="input"
                value={filter.sort}
                data-testid="map-sort"
                onChange={(event) => {
                  changeFilter({
                    ...filter,
                    sort: event.target.value === "rows" ? "rows" : "table",
                  });
                }}
              >
                <option value="table">{t("check.map.sort.table")}</option>
                <option value="rows">{t("check.map.sort.rows")}</option>
              </select>
            </label>
          </div>
          <details className="sp-ck-filters" data-testid="map-filters">
            <summary>{t("check.map.filters")}</summary>
            <div className="sp-ck-dims">
              {atlas.dimensions
                .filter((dim) => dim.values.length > 1)
                .map((dim) => (
                  <label key={dim.input} className="sp-ck-field">
                    <span className="sp-ck-note">
                      {labeler.input(dim.input)}
                    </span>
                    <select
                      className="input"
                      value={filter.dims[dim.input] ?? ""}
                      data-testid={`map-filter-${dim.input}`}
                      onChange={(event) => {
                        changeFilter({
                          ...filter,
                          dims: {
                            ...filter.dims,
                            [dim.input]: event.target.value,
                          },
                        });
                      }}
                    >
                      <option value="">{t("check.map.filterAll")}</option>
                      {dim.values.map((value) => (
                        <option key={value} value={value}>
                          {labeler.value(dim.input, value)}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
            </div>
          </details>
          {filter.outcome !== null && (
            <p className="sp-ck-note" data-testid="map-outcome-filter">
              {t("check.map.onlyOutcome", {
                n: numberOf.get(filter.outcome) ?? 0,
              })}{" "}
              <button
                type="button"
                className="btn sm"
                onClick={() => {
                  changeFilter({ ...filter, outcome: null });
                }}
              >
                {t("check.map.allOutcomes")}
              </button>
            </p>
          )}
          <p className="sp-ck-note" role="status">
            {group === "rows"
              ? t("check.map.shownCount", {
                  shown: Math.min(limit, rows.length),
                  total: rows.length,
                })
              : t("check.map.outcomesCount", { count: outcomeList.length })}
            {filterActive && (
              <>
                {" "}
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => {
                    changeFilter({ ...EMPTY_FILTER, sort: filter.sort });
                  }}
                >
                  {t("check.map.resetFilter")}
                </button>
              </>
            )}
          </p>
          {group === "outcomes" ? (
            <ul className="sp-ck-variants" data-testid="map-outcomes">
              {outcomeList.slice(0, limit).map((outcome) => {
                const isCurrent = outcome.id === currentOutcome?.id;
                return (
                  <li
                    key={outcome.id}
                    className="sp-ck-variant"
                    data-current={isCurrent || undefined}
                  >
                    <span className="sp-ck-message">
                      {t("check.map.outcomeLabel", {
                        n: numberOf.get(outcome.id) ?? 0,
                      })}
                    </span>
                    <span className="sp-ck-note">
                      {t("check.map.outcomeRows", { count: outcome.rows })}
                    </span>
                    <span className="sp-ck-note">
                      {t("check.map.mini", miniOf(outcome.digest))}
                    </span>
                    {isCurrent && (
                      <span className="sp-ck-current">
                        {t("check.map.current")}
                      </span>
                    )}
                    <button
                      type="button"
                      className="btn sm"
                      data-testid={`map-show-rows-${outcome.id}`}
                      onClick={() => {
                        changeFilter({ ...filter, outcome: outcome.id });
                        setGroup("rows");
                      }}
                    >
                      {t("check.map.showRows")}
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : rows.length === 0 ? (
            <p className="sp-ck-note">{t("check.map.noResults")}</p>
          ) : (
            <ul className="sp-ck-variants">
              {rows.slice(0, limit).map((view) => {
                const outcome = outcomes.get(view.row.outcome);
                const isCurrent = view.row.key === currentKey;
                return (
                  <li
                    key={view.row.key}
                    className="sp-ck-variant"
                    data-current={isCurrent || undefined}
                  >
                    <span className="sp-ck-chips">
                      {atlas.dimensions.map((dim) => {
                        const value = view.values[dim.input] ?? dim.default;
                        return (
                          <span
                            key={dim.input}
                            className="sp-ck-chip"
                            data-default={value === dim.default || undefined}
                          >
                            <span className="sp-ck-note">
                              {labeler.input(dim.input)}:
                            </span>{" "}
                            {labeler.value(dim.input, value)}
                          </span>
                        );
                      })}
                    </span>
                    {outcome && (
                      <span className="sp-ck-note">
                        {t("check.map.mini", miniOf(outcome.digest))}
                      </span>
                    )}
                    {isCurrent ? (
                      <span className="sp-ck-current">
                        {t("check.map.current")}
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="btn sm"
                        onClick={() => {
                          nav.go({
                            tab: "result",
                            inputs: applyRowInputs(
                              atlas,
                              view.row,
                              current,
                              caseId,
                            ),
                          });
                        }}
                      >
                        {t("check.map.showResult")}
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {(group === "rows" ? rows.length : outcomeList.length) > limit && (
            <div>
              <button
                type="button"
                className="btn sm"
                onClick={() => {
                  setLimit(limit + PAGE);
                }}
              >
                {t("check.map.more", { count: PAGE })}
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
};

const DimensionCard = ({
  dim,
  input,
  labeler,
  fixed,
  onFix,
}: {
  dim: AtlasDimension;
  input: OutcomeInput | undefined;
  labeler: Labeler;
  fixed: string | undefined;
  onFix: (value: string | null) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const id = useId();
  // У зафиксированного условия в ответе одно значение: список для выбора берётся у самого условия.
  const values = input ? input.values.map((item) => item.value) : dim.values;
  return (
    <li className="sp-ck-dim" data-fixed={fixed !== undefined || undefined}>
      <p className="sp-ck-dim-name">{labeler.input(dim.input)}</p>
      <p className="sp-ck-note">
        {t("check.map.valuesCount", { count: values.length })}
        {", "}
        {t("check.map.defaultValue", {
          value: labeler.value(dim.input, dim.default),
        })}
      </p>
      {dim.affects.length > 0 && (
        <p className="sp-ck-affects">
          <span className="sp-ck-note">{t("check.map.affects")}</span>{" "}
          {dim.affects.map((section) => (
            <Badge key={section} variant="subtle">
              {t(`check.sections.${section}`)}
            </Badge>
          ))}
        </p>
      )}
      <label className="sp-ck-field" htmlFor={id}>
        <span className="sp-ck-note">
          {fixed !== undefined ? (
            <PinOff size="0.75rem" aria-hidden="true" />
          ) : (
            <Pin size="0.75rem" aria-hidden="true" />
          )}{" "}
          {t("check.map.fix")}
        </span>
        <select
          id={id}
          className="input"
          value={fixed ?? ""}
          onChange={(event) => {
            onFix(event.target.value === "" ? null : event.target.value);
          }}
        >
          <option value="">{t("check.map.fixNone")}</option>
          {values.map((value) => (
            <option key={value} value={value}>
              {labeler.value(dim.input, value)}
            </option>
          ))}
        </select>
      </label>
    </li>
  );
};

/** Какие условия зафиксировать, когда вариантов слишком много: самые «широкие» первыми. */
const FixChooser = ({
  inputs,
  labeler,
  pin,
  onFix,
}: {
  inputs: readonly OutcomeInput[] | undefined;
  labeler: Labeler;
  pin: Readonly<Record<string, string>>;
  onFix: (input: string, value: string | null) => void;
}) => {
  const { t } = useTranslation("packSpace");
  const base = useId();
  const choices = [...(inputs ?? [])]
    .filter((input) => input.values.length > 1)
    .sort((a, b) => b.values.length - a.values.length)
    .slice(0, FIX_CHOICES);
  if (choices.length === 0) return null;
  return (
    <section className="sp-ck-card">
      <h3 className="sp-ck-h3">{t("check.map.chooseTitle")}</h3>
      <p className="sp-ck-note">{t("check.map.chooseLead")}</p>
      <div className="sp-ck-dims">
        {choices.map((input) => {
          const selectId = `${base}-${input.id}`;
          return (
            <label key={input.id} className="sp-ck-field" htmlFor={selectId}>
              <span className="sp-ck-note">{labeler.input(input.id)}</span>
              <select
                id={selectId}
                className="input"
                value={pin[input.id] ?? ""}
                onChange={(event) => {
                  onFix(
                    input.id,
                    event.target.value === "" ? null : event.target.value,
                  );
                }}
              >
                <option value="">{t("check.map.fixNone")}</option>
                {input.values.map((item) => (
                  <option key={item.value} value={item.value}>
                    {labeler.value(input.id, item.value)}
                  </option>
                ))}
              </select>
            </label>
          );
        })}
      </div>
    </section>
  );
};
