import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  Grid3x3,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  usePackOutcomeMatrix,
  type MatrixCell,
  type MatrixCellStatus,
  type MatrixRow,
  type OutcomeSection,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { EmptyState } from "@shared/ui";
import {
  cellOf,
  countCells,
  fingerprintGroups,
  tallyRows,
} from "../lib/matrix";
import { tallyText } from "../lib/scenarios";
import { useOutcomeModel } from "../model";
import { ModeSkeleton } from "../ui/ModeSkeleton";
import { CoverageBrief } from "../ui/scenarios/CoverageBrief";
import { ScenarioStatus } from "../ui/scenarios/ScenarioStatus";
import { useScenarioUi } from "../ui/scenarios/context";
import { ChangeList } from "./ChangeList";
import { ModeFailure } from "../ui/ModeFailure";

const CELL_ICON = {
  matched: CheckCircle2,
  changed: CircleAlert,
  unchecked: CircleDashed,
  error: AlertTriangle,
} satisfies Record<MatrixCellStatus, typeof CircleAlert>;

/** Сколько сценариев показать, когда ответ матрицы больше предела («выберите меньше сценариев»). */
const SUBSET = 20;

type Chosen = { scenario: string; section: OutcomeSection };

/**
 * Режим «Матрица»: строки сценарии, столбцы разделы результата, в клетке статус (значок, слово и
 * цвет), число элементов и пометка «изменилось против базы». Статусы, отпечатки и счётчики считает
 * сервер (`matrix`); клик по клетке выбирает сценарий и раздел и показывает расхождение под таблицей.
 */
export const MatrixMode = () => {
  const { t, i18n } = useTranslation("packOutcome");
  const model = useOutcomeModel();
  const ui = useScenarioUi();
  const { url, workspaceId, ref, workspaceKind } = model;
  const git = workspaceKind === "git";
  const against = git && url.state.against === "base" ? "base" : null;
  const [subset, setSubset] = useState<string[] | null>(null);
  const [chosen, setChosen] = useState<Chosen | null>(null);

  const matrix = usePackOutcomeMatrix(
    workspaceId,
    ref,
    {
      state: url.state.state,
      scenarios: subset,
      ...(against ? { against } : {}),
    },
    true,
  );
  const data = matrix.data;
  const rows = useMemo(() => data?.rows ?? [], [data?.rows]);
  const columns = useMemo(() => data?.columns ?? [], [data?.columns]);
  const broken = ui?.tally.broken ?? 0;
  const lang = i18n.language;

  const rerun = () => {
    ui?.rerun();
    void matrix.refetch();
  };

  const nameOf = (row: MatrixRow): string =>
    pickLocalized(row.name, lang, row.scenario);

  const tally = useMemo(() => tallyRows(rows, broken), [rows, broken]);
  const cells = useMemo(() => countCells(rows), [rows]);
  const groups = useMemo(
    () =>
      new Map(
        columns.map((section) => [section, fingerprintGroups(rows, section)]),
      ),
    [columns, rows],
  );

  const choose = (row: MatrixRow, section: OutcomeSection) => {
    setChosen({ scenario: row.scenario, section });
    // Клик выбирает и сценарий на экране: результат, панель вводных и сравнение читают его же.
    if (url.state.scenario !== row.scenario) {
      url.update({ scenario: row.scenario });
    }
  };

  const modeSwitch = (
    <div className="mx-toolbar">
      <div
        className="po-field"
        role="group"
        aria-label={t("modes.matrix.against")}
      >
        <span className="po-field-label" aria-hidden="true">
          {t("modes.matrix.against")}
        </span>
        <div className="po-segmented">
          {(["expected", "base"] as const).map((value) => (
            <button
              key={value}
              type="button"
              className="po-segment"
              aria-pressed={(against ? "base" : "expected") === value}
              disabled={value === "base" && !git}
              title={
                value === "base" && !git
                  ? t("modes.matrix.againstNoGit")
                  : undefined
              }
              data-testid={`outcome-matrix-against-${value}`}
              onClick={() => {
                url.update({ against: value });
              }}
            >
              {t(`modes.matrix.against_${value}`)}
            </button>
          ))}
        </div>
      </div>
      <button
        type="button"
        className="btn sm"
        data-testid="outcome-matrix-rerun"
        disabled={matrix.isFetching}
        onClick={rerun}
      >
        <RefreshCw
          size="0.875rem"
          aria-hidden="true"
          className={matrix.isFetching ? "po-spin" : undefined}
        />
        {t("modes.matrix.rerun")}
      </button>
    </div>
  );

  if (matrix.isError && !data) {
    return (
      <div className="mx" data-testid="outcome-matrix">
        {modeSwitch}
        <ModeFailure
          mode="matrix"
          error={matrix.error}
          onRetry={() => void matrix.refetch()}
          extra={{
            outcome_too_large: (
              <button
                type="button"
                className="btn sm"
                data-testid="outcome-matrix-subset"
                onClick={() => {
                  setSubset(
                    (ui?.entries ?? [])
                      .filter((entry) => entry.scenario !== null)
                      .slice(0, SUBSET)
                      .map((entry) => entry.id),
                  );
                }}
              >
                {t("modes.matrix.firstN", { count: SUBSET })}
              </button>
            ),
            diff_base_unavailable: (
              <button
                type="button"
                className="btn sm"
                data-testid="outcome-matrix-to-expected"
                onClick={() => {
                  url.update({ against: "expected" });
                }}
              >
                {t("modes.matrix.toExpected")}
              </button>
            ),
          }}
        />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx" data-testid="outcome-matrix">
        {modeSwitch}
        <ModeSkeleton testId="outcome-matrix-loading" />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="mx" data-testid="outcome-matrix">
        {modeSwitch}
        <EmptyState
          framed
          icon={<Grid3x3 size="1.5rem" />}
          title={t("modes.matrix.emptyTitle")}
          description={
            broken > 0
              ? t("modes.matrix.emptyBroken", { count: broken })
              : t("modes.matrix.emptyLead")
          }
          action={
            ui?.canWrite ? (
              <button
                type="button"
                className="btn sm"
                data-testid="outcome-matrix-create"
                onClick={() => {
                  ui.open({ kind: "create" });
                }}
              >
                {t("modes.matrix.create")}
              </button>
            ) : undefined
          }
          testId="outcome-matrix-empty"
        />
      </div>
    );
  }

  const picked = chosen
    ? rows.find((row) => row.scenario === chosen.scenario)
    : undefined;
  const pickedCell =
    picked && chosen ? cellOf(picked, chosen.section) : undefined;

  return (
    <div className="mx" data-testid="outcome-matrix">
      {modeSwitch}
      <p
        className="mx-summary"
        data-testid="outcome-matrix-summary"
        role="status"
      >
        {tallyText(t, tally)}
        {matrix.isFetching && (
          <span className="po-note"> {t("result.updating")}</span>
        )}
      </p>
      <CoverageBrief />
      {matrix.isError && (
        <p className="po-note" role="alert" data-testid="outcome-matrix-stale">
          {t("result.stale")}
        </p>
      )}
      {subset !== null && (
        <p className="po-note" data-testid="outcome-matrix-subset-note">
          {t("modes.matrix.subset", { count: subset.length })}{" "}
          <button
            type="button"
            className="po-link"
            onClick={() => {
              setSubset(null);
            }}
          >
            {t("modes.matrix.allScenarios")}
          </button>
        </p>
      )}
      <MatrixGrid
        rows={rows}
        columns={columns}
        groups={groups}
        chosen={chosen}
        nameOf={nameOf}
        onChoose={choose}
      />
      <p className="mx-legend po-note">
        {t("modes.matrix.legend", {
          matched: cells.matched,
          changed: cells.changed,
          unchecked: cells.unchecked,
          error: cells.error,
        })}
      </p>
      {picked && pickedCell && chosen && (
        <MatrixDetail
          row={picked}
          cell={pickedCell}
          section={chosen.section}
          name={nameOf(picked)}
        />
      )}
    </div>
  );
};

type GridProps = {
  rows: readonly MatrixRow[];
  columns: readonly OutcomeSection[];
  groups: ReadonlyMap<OutcomeSection, ReadonlyMap<string, string>>;
  chosen: Chosen | null;
  nameOf: (row: MatrixRow) => string;
  onChoose: (row: MatrixRow, section: OutcomeSection) => void;
};

/** Таблица: `grid` с одной точкой входа в Tab и стрелками между клетками (раздел 3.11). */
const MatrixGrid = ({
  rows,
  columns,
  groups,
  chosen,
  nameOf,
  onChoose,
}: GridProps) => {
  const { t } = useTranslation("packOutcome");
  const gridRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState({ r: 0, c: 0 });
  const at = {
    r: Math.min(active.r, rows.length - 1),
    c: Math.min(active.c, columns.length - 1),
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    let next: { r: number; c: number } | null = null;
    const move = step[event.key];
    if (move) {
      next = {
        r: Math.max(0, Math.min(rows.length - 1, at.r + move[0])),
        c: Math.max(0, Math.min(columns.length - 1, at.c + move[1])),
      };
    } else if (event.key === "Home") {
      next = { r: event.ctrlKey ? 0 : at.r, c: 0 };
    } else if (event.key === "End") {
      next = {
        r: event.ctrlKey ? rows.length - 1 : at.r,
        c: columns.length - 1,
      };
    }
    if (!next) return;
    event.preventDefault();
    setActive(next);
    gridRef.current
      ?.querySelector<HTMLElement>(
        `[data-r="${String(next.r)}"][data-c="${String(next.c)}"]`,
      )
      ?.focus();
  };

  return (
    <div
      ref={gridRef}
      className="mx-grid"
      role="grid"
      aria-label={t("modes.matrix.gridLabel")}
      aria-rowcount={rows.length + 1}
      aria-colcount={columns.length + 1}
      style={{ "--mx-cols": columns.length } as React.CSSProperties}
      onKeyDown={onKeyDown}
    >
      <div className="mx-row mx-head" role="row">
        <div className="mx-corner" role="columnheader">
          {t("modes.matrix.scenario")}
        </div>
        {columns.map((section) => (
          <div key={section} className="mx-colhead" role="columnheader">
            {t(`sections.${section}`)}
          </div>
        ))}
      </div>
      {rows.map((row, r) => (
        <div
          key={row.scenario}
          className="mx-row"
          role="row"
          data-status={row.status}
        >
          <div className="mx-rowhead" role="rowheader">
            <span className="mx-name">{nameOf(row)}</span>
            <ScenarioStatus status={row.status} />
            {row.message !== null && (
              <span
                className="mx-message"
                data-testid={`outcome-matrix-message-${row.scenario}`}
              >
                {row.message}
              </span>
            )}
          </div>
          {columns.map((section, c) => {
            const cell = cellOf(row, section);
            return (
              <div key={section} className="mx-cellwrap" role="gridcell">
                {cell ? (
                  <CellButton
                    cell={cell}
                    section={section}
                    scenario={nameOf(row)}
                    letter={groups.get(section)?.get(cell.fingerprint) ?? null}
                    selected={
                      chosen?.scenario === row.scenario &&
                      chosen.section === section
                    }
                    tabbable={at.r === r && at.c === c}
                    r={r}
                    c={c}
                    testId={`outcome-matrix-cell-${row.scenario}-${section}`}
                    onFocus={() => {
                      setActive({ r, c });
                    }}
                    onClick={() => {
                      onChoose(row, section);
                    }}
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
};

type CellButtonProps = {
  cell: MatrixCell;
  section: OutcomeSection;
  scenario: string;
  letter: string | null;
  selected: boolean;
  tabbable: boolean;
  r: number;
  c: number;
  testId: string;
  onFocus: () => void;
  onClick: () => void;
};

const CellButton = ({
  cell,
  section,
  scenario,
  letter,
  selected,
  tabbable,
  r,
  c,
  testId,
  onFocus,
  onClick,
}: CellButtonProps) => {
  const { t } = useTranslation("packOutcome");
  const Icon = CELL_ICON[cell.status];
  const word = t(`modes.matrix.cell.${cell.status}`);
  const sectionName = t(`sections.${section}`);
  const hasResult = cell.status !== "error";
  const label = [
    `${scenario}, ${sectionName}`,
    word,
    hasResult ? t("modes.matrix.count", { count: cell.count }) : null,
    cell.changed === true ? t("modes.matrix.changedBase") : null,
    letter ? t("modes.matrix.group", { letter }) : null,
  ]
    .filter((part) => part !== null)
    .join(". ");
  return (
    <button
      type="button"
      className="mx-cell"
      data-status={cell.status}
      data-r={r}
      data-c={c}
      data-testid={testId}
      aria-label={label}
      aria-pressed={selected}
      tabIndex={tabbable ? 0 : -1}
      onFocus={onFocus}
      onClick={onClick}
    >
      <span className="mx-cell-section" aria-hidden="true">
        {sectionName}
      </span>
      <span className="mx-cell-main" aria-hidden="true">
        <Icon size="0.875rem" />
        <span className="mx-cell-count">{hasResult ? cell.count : "–"}</span>
        {cell.changed === true && <span className="mx-base">~</span>}
        {letter && (
          <span className="mx-group" data-letter={letter}>
            {letter}
          </span>
        )}
      </span>
      <span className="mx-cell-word" aria-hidden="true">
        {word}
      </span>
    </button>
  );
};

type DetailProps = {
  row: MatrixRow;
  cell: MatrixCell;
  section: OutcomeSection;
  name: string;
};

/** Расхождение выбранной клетки: что изменилось в разделе у сценария и куда перейти дальше. */
const MatrixDetail = ({ row, cell, section, name }: DetailProps) => {
  const { t } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const ui = useScenarioUi();
  const result = ui?.results.get(row.scenario);
  const changes = (result?.changes ?? []).filter(
    (change) => change.section === section,
  );
  const left = {
    source: { kind: "scenario", id: row.scenario },
    state: null,
  } as const;
  return (
    <section
      className="mx-detail"
      aria-label={t("modes.matrix.detail", {
        name,
        section: t(`sections.${section}`),
      })}
      data-testid="outcome-matrix-detail"
    >
      <h3 className="mx-detail-title">
        {name}
        <span className="mx-detail-section">{t(`sections.${section}`)}</span>
      </h3>
      <p className="mx-detail-status">
        <ScenarioStatus status={row.status} />
        <span>{t(`modes.matrix.cell.${cell.status}`)}</span>
        {cell.status !== "error" && (
          <span>{t("modes.matrix.count", { count: cell.count })}</span>
        )}
        {cell.changed === true && <span>{t("modes.matrix.changedBase")}</span>}
      </p>
      {row.message !== null && <p className="mx-message">{row.message}</p>}
      {changes.length > 0 ? (
        <ChangeList changes={changes} testId="outcome-matrix-changes" />
      ) : (
        <p className="po-note" data-testid="outcome-matrix-no-changes">
          {cell.status === "matched" || cell.status === "unchecked"
            ? t("modes.matrix.noDiff")
            : t("modes.matrix.noDiffList")}
        </p>
      )}
      <div className="mx-detail-actions">
        <button
          type="button"
          className="btn sm"
          data-testid="outcome-matrix-show"
          onClick={() => {
            url.update(
              { view: "result", scenario: row.scenario, inputs: {} },
              true,
            );
          }}
        >
          {t("modes.matrix.show")}
        </button>
        <button
          type="button"
          className="btn sm"
          data-testid="outcome-matrix-compare"
          onClick={() => {
            url.update({ view: "compare", left, right: null }, true);
          }}
        >
          {t("modes.matrix.compare")}
        </button>
        {ui && (
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-matrix-open-scenario"
            onClick={() => {
              ui.open({ kind: "panel", id: row.scenario });
            }}
          >
            {t("modes.matrix.openScenario")}
          </button>
        )}
      </div>
    </section>
  );
};
