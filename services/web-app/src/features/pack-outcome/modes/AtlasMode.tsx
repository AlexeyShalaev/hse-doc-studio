import {
  useCallback,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Layers, Pin, PinOff, RefreshCw, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  classifyOutcomeFailure,
  packOutcomeKeys,
  usePackOutcomeAtlas,
  type AtlasDimension,
  type AtlasOutcome,
  type OutcomeInput,
  type PackOutcome,
  type PackOutcomeAtlas,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { Badge, EmptyState } from "@shared/ui";
import {
  EMPTY_FILTER,
  applyRowInputs,
  filterRows,
  keyOfInputs,
  miniOf,
  withPin,
  type AtlasFilter,
  type AtlasRowView,
  type OutcomeMini,
} from "../lib/atlas";
import { personaLabel } from "../lib/personas";
import { mergedInputs } from "../lib/scenarios";
import { useOutcomeModel } from "../model";
import { ModeSkeleton } from "../ui/ModeSkeleton";
import { useLabeler, type Labeler } from "../ui/inputs/useLabeler";
import { ModeFailure } from "../ui/ModeFailure";

/** Сколько строк показывать за раз: сотни строк ВКР листаются кнопкой, страница не тормозит. */
const PAGE = 60;
/** Сколько вводных предлагать закрепить, когда атлас слишком большой. */
const PIN_CHOICES = 12;

/**
 * Режим «Атлас»: таблица исходов по вводным, которые реально что-то меняют (template-studio-outcome.md,
 * разделы 3.6 и 4.4). Сервер считает таблицу за секунды (ответ кэшируется по ETag); клиент раскладывает
 * ключ строки по измерениям, группирует одинаковые исходы, ищет и фильтрует. Выбор строки пишет её
 * вводные в адрес: результат показывает обычный расчёт, а сам исход строки сразу виден из сжатого
 * результата атласа (`digest`), без запроса.
 */
export const AtlasMode = () => {
  const { t } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const client = useQueryClient();
  const { url, workspaceId, ref } = model;
  const request = useMemo(
    () => ({
      state: url.state.state,
      example: url.state.example,
      pin: url.state.pin,
    }),
    [url.state.state, url.state.example, url.state.pin],
  );
  const atlas = usePackOutcomeAtlas(workspaceId, ref, request, true);
  const labeler = useLabeler(model.inputs.data?.inputs);
  const data = atlas.data;

  const cancel = () => {
    void client.cancelQueries({
      queryKey: packOutcomeKeys.atlas(workspaceId, ref, request),
    });
  };

  if (atlas.isError && !data) {
    return (
      <div className="at" data-testid="outcome-atlas">
        <ModeFailure
          mode="atlas"
          error={atlas.error}
          onRetry={() => void atlas.refetch()}
          noRetry={["atlas_too_large"]}
        />
        <PinChooser
          inputs={model.inputs.data?.inputs}
          labeler={labeler}
          pin={url.state.pin}
          onPin={(pin) => {
            url.update({ pin });
          }}
          tooLarge={
            classifyOutcomeFailure(atlas.error).kind === "atlas_too_large"
          }
        />
      </div>
    );
  }

  if (!data) {
    // Отмена оставляет запрос без данных и без загрузки: предлагаем посчитать снова.
    if (atlas.fetchStatus === "idle") {
      return (
        <div className="at" data-testid="outcome-atlas">
          <EmptyState
            framed
            icon={<Layers size="1.5rem" />}
            title={t("modes.atlas.cancelledTitle")}
            description={t("modes.atlas.cancelledLead")}
            action={
              <button
                type="button"
                className="btn sm"
                data-testid="outcome-atlas-again"
                onClick={() => void atlas.refetch()}
              >
                {t("modes.atlas.again")}
              </button>
            }
            testId="outcome-atlas-cancelled"
          />
        </div>
      );
    }
    return (
      <div className="at" data-testid="outcome-atlas">
        <div className="at-loading" role="status">
          <p className="at-loading-text">
            <RefreshCw size="0.875rem" aria-hidden="true" className="po-spin" />
            {atlas.failureCount > 0
              ? t("modes.atlas.busyRetry", { count: atlas.failureCount })
              : t("modes.atlas.loading")}
          </p>
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-atlas-cancel"
            onClick={cancel}
          >
            {t("modes.atlas.cancel")}
          </button>
        </div>
        <ModeSkeleton testId="outcome-atlas-loading" />
      </div>
    );
  }

  return (
    <AtlasView
      atlas={data}
      labeler={labeler}
      stale={atlas.isError}
      fetching={atlas.isFetching}
      shown={model.shown}
    />
  );
};

type ViewProps = {
  atlas: PackOutcomeAtlas;
  labeler: Labeler;
  stale: boolean;
  fetching: boolean;
  shown: PackOutcome | undefined;
};

const AtlasView = ({ atlas, labeler, stale, fetching, shown }: ViewProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const { url, scenarios, inputs } = model;
  const searchRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState<AtlasFilter>(EMPTY_FILTER);
  const [group, setGroup] = useState<"rows" | "outcomes">("rows");
  const [limit, setLimit] = useState(PAGE);
  const [seen, setSeen] = useState(atlas);
  const [announce, setAnnounce] = useState("");
  const searchId = useId();

  const outcomes = useMemo(
    () => new Map(atlas.outcomes.map((outcome) => [outcome.id, outcome])),
    [atlas.outcomes],
  );
  const rows = useMemo(
    () => filterRows(atlas, filter, labeler.value),
    [atlas, filter, labeler.value],
  );
  // Страница сбрасывается вместе с поиском, фильтрами и самим атласом (новый ответ).
  if (seen !== atlas) {
    setSeen(atlas);
    setLimit(PAGE);
  }
  const changeFilter = (next: AtlasFilter) => {
    setFilter(next);
    setLimit(PAGE);
  };

  // Текущая строка: по вводным адреса и сценария, без запроса: переключение сразу видно в таблице.
  const current = mergedInputs(
    scenarios.data,
    url.state.scenario,
    url.state.inputs,
  );
  const currentKey = keyOfInputs(atlas.dimensions, current);
  const currentRow = atlas.rows.find((row) => row.key === currentKey);
  const currentOutcome = currentRow
    ? outcomes.get(currentRow.outcome)
    : undefined;

  const apply = useCallback(
    (view: AtlasRowView) => {
      url.update(
        {
          inputs: applyRowInputs(
            atlas,
            view.row,
            url.state.inputs,
            url.state.scenario,
          ),
        },
        true,
      );
      setAnnounce(t("modes.atlas.applied", { outcome: view.row.outcome }));
    },
    [atlas, url, t],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
    if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      searchRef.current?.focus();
    }
  };

  const pinned = Object.entries(url.state.pin);
  const dimensions = atlas.dimensions;
  const inputById = new Map((inputs.data?.inputs ?? []).map((i) => [i.id, i]));
  const filterActive =
    filter.query !== "" ||
    filter.outcome !== null ||
    Object.values(filter.dims).some((value) => value !== "");

  const listed = group === "rows" ? rows.slice(0, limit) : [];
  const outcomeList = useMemo(() => {
    const list = [...atlas.outcomes];
    if (filter.sort === "rows") list.sort((a, b) => b.rows - a.rows);
    return list;
  }, [atlas.outcomes, filter.sort]);

  return (
    <div
      className="at"
      data-testid="outcome-atlas"
      aria-busy={fetching || undefined}
      onKeyDown={onKeyDown}
    >
      <p className="at-summary" data-testid="outcome-atlas-summary">
        {t("modes.atlas.summary", {
          outcomes: t("modes.atlas.outcomes", {
            count: atlas.outcomes_distinct,
          }),
          rows: t("modes.atlas.rows", { count: atlas.rows_total }),
          combinations: t("modes.atlas.combinations", {
            count: atlas.combinations_total,
          }),
        })}
        <span className="po-note">
          {" "}
          {t("modes.atlas.elapsed", {
            seconds: (atlas.elapsed_ms / 1000).toFixed(1),
          })}
        </span>
      </p>
      {stale && (
        <p className="po-note" role="alert" data-testid="outcome-atlas-stale">
          {t("result.stale")}
        </p>
      )}

      {dimensions.length === 0 ? (
        <p className="po-note" data-testid="outcome-atlas-no-dimensions">
          {t("modes.atlas.noDimensions")}
        </p>
      ) : (
        // На телефоне восемь карточек занимают экран: блок свёрнут, раскрывается заголовком.
        <details
          open={model.phone ? undefined : true}
          className="at-block at-dimblock"
          data-testid="outcome-atlas-dimensions"
        >
          <summary className="at-h at-summary-h">
            {t("modes.atlas.dimensions", { count: dimensions.length })}
          </summary>
          <p className="po-note">{t("modes.atlas.dimensionsLead")}</p>
          <ul className="at-dims">
            {dimensions.map((dim) => (
              <DimensionCard
                key={dim.input}
                dim={dim}
                input={inputById.get(dim.input)}
                labeler={labeler}
                pinnedValue={url.state.pin[dim.input]}
                onPin={(value) => {
                  url.update({ pin: withPin(url.state.pin, dim.input, value) });
                }}
              />
            ))}
          </ul>
        </details>
      )}

      {pinned.length > 0 && (
        <p className="at-pins" data-testid="outcome-atlas-pins">
          <Pin size="0.875rem" aria-hidden="true" />
          <span>{t("modes.atlas.pinned")}</span>
          {pinned.map(([input, value]) => (
            <button
              key={input}
              type="button"
              className="at-chip at-chip-pin"
              aria-label={t("modes.atlas.unpin", {
                input: labeler.input(input),
                value: labeler.value(input, value),
              })}
              onClick={() => {
                url.update({ pin: withPin(url.state.pin, input, null) });
              }}
            >
              {labeler.input(input)}: {labeler.value(input, value)}
              <X size="0.75rem" aria-hidden="true" />
            </button>
          ))}
        </p>
      )}

      {atlas.ignored.length > 0 && (
        <details className="at-ignored" data-testid="outcome-atlas-ignored">
          <summary>
            {t("modes.atlas.ignored", { count: atlas.ignored.length })}
          </summary>
          <ul className="at-ignored-list">
            {atlas.ignored.map((item) => (
              <li key={item.input} data-reason={item.reason}>
                <span className="po-mono">{labeler.input(item.input)}</span>
                <span className="po-note">
                  {t(`modes.atlas.reason.${item.reason}`)}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="at-toolbar" role="search">
        <label className="at-search" htmlFor={searchId}>
          <span className="sr-only">{t("modes.atlas.search")}</span>
          <input
            id={searchId}
            ref={searchRef}
            type="search"
            className="input"
            placeholder={t("modes.atlas.searchPlaceholder")}
            value={filter.query}
            data-testid="outcome-atlas-search"
            onChange={(event) => {
              changeFilter({ ...filter, query: event.target.value });
            }}
          />
        </label>
        <div
          className="po-segmented"
          role="group"
          aria-label={t("modes.atlas.group")}
        >
          {(["rows", "outcomes"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className="po-segment"
              aria-pressed={group === value}
              data-testid={`outcome-atlas-group-${value}`}
              onClick={() => {
                setGroup(value);
                setLimit(PAGE);
              }}
            >
              {t(`modes.atlas.group_${value}`)}
            </button>
          ))}
        </div>
        <label className="po-filter-select">
          <span className="po-note">{t("modes.atlas.sort")}</span>
          <select
            className="input"
            value={filter.sort}
            data-testid="outcome-atlas-sort"
            onChange={(event) => {
              changeFilter({
                ...filter,
                sort: event.target.value === "rows" ? "rows" : "table",
              });
            }}
          >
            <option value="table">{t("modes.atlas.sort_table")}</option>
            <option value="rows">{t("modes.atlas.sort_rows")}</option>
          </select>
        </label>
      </div>

      {dimensions.some((dim) => dim.values.length > 1) && (
        <details className="at-filters">
          <summary>{t("modes.atlas.filters")}</summary>
          <div className="at-filter-grid">
            {dimensions
              .filter((dim) => dim.values.length > 1)
              .map((dim) => (
                <label key={dim.input} className="po-filter-select">
                  <span className="po-note">{labeler.input(dim.input)}</span>
                  <select
                    className="input"
                    value={filter.dims[dim.input] ?? ""}
                    data-testid={`outcome-atlas-filter-${dim.input}`}
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
                    <option value="">{t("modes.atlas.filterAll")}</option>
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
      )}

      {filter.outcome !== null && (
        <p className="po-note" data-testid="outcome-atlas-outcome-filter">
          {t("modes.atlas.onlyOutcome", { outcome: filter.outcome })}{" "}
          <button
            type="button"
            className="po-link"
            onClick={() => {
              changeFilter({ ...filter, outcome: null });
            }}
          >
            {t("modes.atlas.resetOutcome")}
          </button>
        </p>
      )}

      <p className="po-note" role="status" data-testid="outcome-atlas-count">
        {group === "rows"
          ? t("modes.atlas.shownRows", {
              shown: listed.length,
              total: rows.length,
            })
          : t("modes.atlas.shownOutcomes", {
              shown: Math.min(limit, outcomeList.length),
              total: outcomeList.length,
            })}
        {filterActive && (
          <>
            {" "}
            <button
              type="button"
              className="po-link"
              data-testid="outcome-atlas-reset"
              onClick={() => {
                changeFilter(EMPTY_FILTER);
              }}
            >
              {t("modes.atlas.reset")}
            </button>
          </>
        )}
      </p>

      {group === "rows" ? (
        rows.length === 0 ? (
          <p className="po-note" data-testid="outcome-atlas-noresults">
            {t("modes.atlas.noResults")}
          </p>
        ) : (
          <ul className="at-list" data-testid="outcome-atlas-rows">
            {listed.map((view) => (
              <AtlasRowItem
                key={view.row.key}
                view={view}
                dimensions={dimensions}
                outcome={outcomes.get(view.row.outcome)}
                labeler={labeler}
                current={view.row.key === currentKey}
                onApply={apply}
                onOutcome={(id) => {
                  changeFilter({ ...filter, outcome: id });
                }}
              />
            ))}
          </ul>
        )
      ) : (
        <ul className="at-list" data-testid="outcome-atlas-outcomes">
          {outcomeList.slice(0, limit).map((outcome) => (
            <li key={outcome.id}>
              <div
                className="at-outcome"
                data-current={
                  outcome.id === currentOutcome?.id ? "true" : undefined
                }
              >
                <span className="at-o">{outcome.id}</span>
                <span className="at-o-rows">
                  {t("modes.atlas.outcomeRows", { count: outcome.rows })}
                </span>
                <Mini mini={miniOf(outcome.digest)} />
                <button
                  type="button"
                  className="btn sm"
                  data-testid={`outcome-atlas-show-${outcome.id}`}
                  onClick={() => {
                    changeFilter({ ...filter, outcome: outcome.id });
                    setGroup("rows");
                  }}
                >
                  {t("modes.atlas.showRows")}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {(group === "rows" ? rows.length : outcomeList.length) > limit && (
        <button
          type="button"
          className="btn sm"
          data-testid="outcome-atlas-more"
          onClick={() => {
            setLimit(limit + PAGE);
          }}
        >
          {t("modes.atlas.more", { count: PAGE })}
        </button>
      )}

      <OutcomeDetail
        outcome={currentOutcome}
        shown={shown}
        lang={i18n.language}
        rowsInTable={atlas.rows.length > 0}
        onResult={() => {
          url.update({ view: "result" }, true);
        }}
      />
      <div className="sr-only" role="status" data-testid="outcome-atlas-live">
        {announce}
      </div>
    </div>
  );
};

type DimensionCardProps = {
  dim: AtlasDimension;
  input: OutcomeInput | undefined;
  labeler: Labeler;
  pinnedValue: string | undefined;
  onPin: (value: string | null) => void;
};

const DimensionCard = ({
  dim,
  input,
  labeler,
  pinnedValue,
  onPin,
}: DimensionCardProps) => {
  const { t } = useTranslation("packOutcome");
  const id = useId();
  // Закреплённое измерение в ответе уже с одним значением: список для выбора берётся у вводной.
  const values = input ? input.values.map((item) => item.value) : dim.values;
  return (
    <li
      className="at-dim"
      data-pinned={pinnedValue !== undefined ? "true" : undefined}
    >
      <p className="at-dim-name">{labeler.input(dim.input)}</p>
      <p className="po-note">
        {t("modes.atlas.valuesCount", { count: values.length })}
        {", "}
        {t("modes.atlas.defaultValue", {
          value: labeler.value(dim.input, dim.default),
        })}
      </p>
      {dim.affects.length > 0 && (
        <p className="at-affects">
          <span className="po-note">{t("modes.atlas.affects")}</span>{" "}
          {dim.affects.map((section) => (
            <Badge key={section} variant="subtle">
              {t(`sections.${section}`)}
            </Badge>
          ))}
        </p>
      )}
      <label className="po-filter-select" htmlFor={id}>
        <span className="po-note">
          {pinnedValue !== undefined ? (
            <PinOff size="0.75rem" aria-hidden="true" />
          ) : (
            <Pin size="0.75rem" aria-hidden="true" />
          )}{" "}
          {t("modes.atlas.pin")}
        </span>
        <select
          id={id}
          className="input"
          value={pinnedValue ?? ""}
          data-testid={`outcome-atlas-pin-${dim.input}`}
          onChange={(event) => {
            onPin(event.target.value === "" ? null : event.target.value);
          }}
        >
          <option value="">{t("modes.atlas.pinNone")}</option>
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

type RowItemProps = {
  view: AtlasRowView;
  dimensions: readonly AtlasDimension[];
  outcome: AtlasOutcome | undefined;
  labeler: Labeler;
  current: boolean;
  onApply: (view: AtlasRowView) => void;
  onOutcome: (id: string) => void;
};

const AtlasRowItem = ({
  view,
  dimensions,
  outcome,
  labeler,
  current,
  onApply,
  onOutcome,
}: RowItemProps) => {
  const { t } = useTranslation("packOutcome");
  return (
    <li className="at-item">
      <button
        type="button"
        className="at-row"
        aria-pressed={current}
        data-current={current ? "true" : undefined}
        data-testid="outcome-atlas-row"
        data-key={view.row.key}
        onClick={() => {
          onApply(view);
        }}
      >
        <span className="at-chips">
          {dimensions.map((dim) => {
            const value = view.values[dim.input] ?? dim.default;
            return (
              <span
                key={dim.input}
                className="at-chip"
                data-default={value === dim.default ? "true" : undefined}
              >
                <span className="at-chip-name">
                  {labeler.input(dim.input)}:
                </span>{" "}
                {labeler.value(dim.input, value)}
              </span>
            );
          })}
        </span>
        {outcome && <Mini mini={miniOf(outcome.digest)} />}
        {current && (
          <span className="at-current">{t("modes.atlas.current")}</span>
        )}
      </button>
      <button
        type="button"
        className="at-o at-o-btn"
        title={t("modes.atlas.outcomeFilter", { outcome: view.row.outcome })}
        aria-label={t("modes.atlas.outcomeFilter", {
          outcome: view.row.outcome,
        })}
        data-testid="outcome-atlas-outcome"
        onClick={() => {
          onOutcome(view.row.outcome);
        }}
      >
        {view.row.outcome}
        {outcome && (
          <span className="at-o-rows">{`×${String(outcome.rows)}`}</span>
        )}
      </button>
    </li>
  );
};

const Mini = ({ mini }: { mini: OutcomeMini }) => {
  const { t } = useTranslation("packOutcome");
  return <span className="at-mini">{t("modes.atlas.mini", mini)}</span>;
};

type DetailProps = {
  outcome: AtlasOutcome | undefined;
  shown: PackOutcome | undefined;
  lang: string;
  rowsInTable: boolean;
  onResult: () => void;
};

/** Исход текущих вводных из сжатого результата атласа: документы, участники, точки, без запроса. */
const OutcomeDetail = ({
  outcome,
  shown,
  lang,
  rowsInTable,
  onResult,
}: DetailProps) => {
  const { t } = useTranslation("packOutcome");
  if (!outcome) {
    return rowsInTable ? (
      <p
        className="po-note at-detail-none"
        data-testid="outcome-atlas-detail-none"
      >
        {t("modes.atlas.detailNone")}
      </p>
    ) : null;
  }
  const names = new Map(
    (shown?.documents ?? []).map((doc) => [
      doc.id,
      pickLocalized(doc.name, lang, doc.id),
    ]),
  );
  const pointNames = new Map(
    (shown?.points ?? []).map((point) => [
      point.id,
      pickLocalized(point.name, lang, point.id),
    ]),
  );
  const docs = Object.entries(outcome.digest.documents);
  const active = docs.filter(([, state]) => state === "active");
  const inactive = docs.filter(([, state]) => state === "inactive");
  return (
    <section
      className="at-detail"
      aria-label={t("modes.atlas.detail", { outcome: outcome.id })}
      data-testid="outcome-atlas-detail"
    >
      <h3 className="at-h">
        {t("modes.atlas.detail", { outcome: outcome.id })}{" "}
        <span className="po-note">
          {t("modes.atlas.outcomeRows", { count: outcome.rows })}
        </span>
      </h3>
      <dl className="at-detail-grid">
        <div>
          <dt>{t("modes.atlas.detailDocs", { count: active.length })}</dt>
          <dd>
            {active.map(([id]) => names.get(id) ?? id).join(", ") ||
              t("modes.atlas.none")}
          </dd>
        </div>
        {inactive.length > 0 && (
          <div>
            <dt>{t("modes.atlas.detailOff", { count: inactive.length })}</dt>
            <dd>{inactive.map(([id]) => names.get(id) ?? id).join(", ")}</dd>
          </div>
        )}
        <div>
          <dt>
            {t("modes.atlas.detailPeople", {
              count: outcome.digest.participants.length,
            })}
          </dt>
          <dd>
            {outcome.digest.participants
              .map((persona) => personaLabel(t, persona))
              .join(", ") || t("modes.atlas.none")}
          </dd>
        </div>
        <div>
          <dt>
            {t("modes.atlas.detailPoints", {
              count: outcome.digest.points.length,
            })}
          </dt>
          <dd>
            {outcome.digest.points
              .map((point) =>
                t("modes.atlas.pointLine", {
                  name: pointNames.get(point.id) ?? point.id,
                  items: point.items.length,
                  steps: point.steps.length,
                }),
              )
              .join("; ") || t("modes.atlas.none")}
          </dd>
        </div>
      </dl>
      <button
        type="button"
        className="btn sm"
        data-testid="outcome-atlas-open-result"
        onClick={onResult}
      >
        {t("modes.atlas.openResult")}
      </button>
    </section>
  );
};

type PinChooserProps = {
  inputs: readonly OutcomeInput[] | undefined;
  labeler: Labeler;
  pin: Readonly<Record<string, string>>;
  onPin: (pin: Record<string, string>) => void;
  tooLarge: boolean;
};

/** Какие вводные закрепить, когда атласа нет: самые «широкие» первыми. Только при `atlas_too_large`. */
const PinChooser = ({
  inputs,
  labeler,
  pin,
  onPin,
  tooLarge,
}: PinChooserProps) => {
  const { t } = useTranslation("packOutcome");
  const base = useId();
  if (!tooLarge) return null;
  const choices = [...(inputs ?? [])]
    .filter((input) => input.values.length > 1)
    .sort((a, b) => b.values.length - a.values.length)
    .slice(0, PIN_CHOICES);
  if (choices.length === 0) return null;
  return (
    <section
      className="at-block at-pinchoose"
      data-testid="outcome-atlas-pinchoose"
    >
      <h3 className="at-h">{t("modes.atlas.pinChoose")}</h3>
      <p className="po-note">{t("modes.atlas.pinChooseLead")}</p>
      <div className="at-filter-grid">
        {choices.map((input) => {
          const selectId = `${base}-${input.id}`;
          return (
            <label
              key={input.id}
              className="po-filter-select"
              htmlFor={selectId}
            >
              <span className="po-note">{labeler.input(input.id)}</span>
              <select
                id={selectId}
                className="input"
                value={pin[input.id] ?? ""}
                data-testid={`outcome-atlas-pin-${input.id}`}
                onChange={(event) => {
                  onPin(
                    withPin(
                      pin,
                      input.id,
                      event.target.value === "" ? null : event.target.value,
                    ),
                  );
                }}
              >
                <option value="">{t("modes.atlas.pinNone")}</option>
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
