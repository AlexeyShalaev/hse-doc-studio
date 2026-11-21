import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  RefreshCw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  usePackOutcomeMatrix,
  usePackScenarioRun,
  type MatrixCell,
  type MatrixCellStatus,
  type MatrixRow,
  type OutcomeSection,
} from "@entities/pack-studio";
import {
  cellOf,
  countCells,
  fingerprintGroups,
  resultsById,
  tallyRows,
} from "@features/pack-outcome/check";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { EmptyState } from "@shared/ui";
import { useSpace } from "../context/SpaceContext";
import { useSpaceNav } from "../context/useSpaceNav";
import { ChangeList } from "@features/pack-outcome/check";
import { CheckChangeEnv } from "./ChangeEnv";
import { CheckFailure } from "./CheckFailure";
import { useCheckEnv } from "./useCheckEnv";

const CELL_ICON = {
  matched: CheckCircle2,
  changed: CircleAlert,
  unchecked: CircleDashed,
  error: AlertTriangle,
} satisfies Record<MatrixCellStatus, typeof CircleAlert>;

type Chosen = { scenario: string; section: OutcomeSection };

/**
 * «Типовые случаи»: строки это готовые случаи, столбцы части результата, в клетке статус (значок,
 * слово и цвет) и число элементов. Статусы и счётчики считает сервер (`matrix`); клик по клетке
 * показывает, что изменилось в этой части, и куда перейти дальше.
 */
export const CasesPart = () => {
  const { t, i18n } = useTranslation("packSpace");
  const env = useCheckEnv();
  const { workspace, location } = useSpace();
  const nav = useSpaceNav();
  const git = workspace.kind === "git";
  const params = new URLSearchParams(location.search);
  const against = git && params.get("against") === "base" ? "base" : null;
  const [chosen, setChosen] = useState<Chosen | null>(null);

  const matrix = usePackOutcomeMatrix(
    env.workspaceId,
    env.ref,
    { state: "work_tree", ...(against ? { against } : {}) },
    true,
  );
  const data = matrix.data;
  const rows = useMemo(() => data?.rows ?? [], [data?.rows]);
  const columns = useMemo(() => data?.columns ?? [], [data?.columns]);
  // Подробности клетки (что изменилось) берутся из прогона: он нужен, только когда клетку выбрали.
  const run = usePackScenarioRun(
    env.workspaceId,
    env.ref,
    "work_tree",
    env.inputs.data?.revision,
    chosen !== null && env.inputs.data !== undefined,
  );
  const results = useMemo(() => resultsById(run.data), [run.data]);
  const tally = useMemo(() => tallyRows(rows, 0), [rows]);
  const cells = useMemo(() => countCells(rows), [rows]);
  const letters = useMemo(
    () =>
      new Map(
        columns.map((section) => [section, fingerprintGroups(rows, section)]),
      ),
    [columns, rows],
  );
  const nameOf = (row: MatrixRow): string =>
    pickLocalized(row.name, i18n.language, row.scenario);

  const toResult = (
    <button
      type="button"
      className="btn sm primary"
      onClick={() => {
        nav.go({ tab: "result" });
      }}
    >
      {t("check.cases.toResult")}
    </button>
  );

  const toolbar = (
    <div className="sp-ck-toolbar">
      <span className="sp-ck-note">{t("check.cases.againstShort")}</span>
      <div
        className="sp-ck-seg"
        role="group"
        aria-label={t("check.cases.against")}
      >
        {(["expected", "base"] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={(against ? "base" : "expected") === value}
            disabled={value === "base" && !git}
            title={
              value === "base" && !git
                ? t("check.cases.againstNoGit")
                : undefined
            }
            onClick={() => {
              nav.go({ extra: { against: value === "base" ? "base" : null } });
            }}
          >
            {t(`check.cases.against_${value}`)}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="btn sm"
        disabled={matrix.isFetching}
        onClick={() => {
          void matrix.refetch();
          if (chosen) void run.refetch();
        }}
      >
        <RefreshCw
          size="0.8125rem"
          aria-hidden="true"
          className={matrix.isFetching ? "sp-ck-spin" : undefined}
        />
        {t("check.cases.rerun")}
      </button>
    </div>
  );

  if (matrix.isError && !data) {
    return (
      <div className="sp-ck-stack">
        {toolbar}
        <CheckFailure
          kind="cases"
          error={matrix.error}
          onRetry={() => void matrix.refetch()}
          extra={{
            diff_base_unavailable: (
              <button
                type="button"
                className="btn sm"
                onClick={() => {
                  nav.go({ extra: { against: null } });
                }}
              >
                {t("check.cases.toExpected")}
              </button>
            ),
          }}
        />
      </div>
    );
  }
  if (!data) {
    return (
      <p className="sp-ck-loading" role="status">
        <RefreshCw size="0.875rem" aria-hidden="true" className="sp-ck-spin" />
        {t("check.cases.loading")}
      </p>
    );
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        framed
        icon={<CircleDashed size="1.5rem" />}
        title={t("check.cases.emptyTitle")}
        description={t("check.cases.emptyLead")}
        action={toResult}
      />
    );
  }

  const picked = chosen
    ? rows.find((row) => row.scenario === chosen.scenario)
    : undefined;
  const pickedCell =
    picked && chosen ? cellOf(picked, chosen.section) : undefined;
  const changes =
    picked && chosen
      ? (results.get(picked.scenario)?.changes ?? []).filter(
          (change) => change.section === chosen.section,
        )
      : [];

  return (
    <div className="sp-ck-stack" aria-busy={matrix.isFetching || undefined}>
      {toolbar}
      <p className="sp-ck-summary-line" role="status">
        {t("check.cases.summary", {
          total: tally.total,
          passed: tally.passed,
          failed: tally.failed,
          unchecked: tally.unchecked,
          errors: tally.errors,
        })}
      </p>
      {matrix.isError && (
        <p className="sp-ck-note" role="alert">
          {t("check.cases.stale")}
        </p>
      )}
      <div className="sp-ck-table-wrap">
        <table className="sp-ck-table">
          <caption className="sr-only">{t("check.cases.tableLabel")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("check.cases.caseColumn")}</th>
              {columns.map((section) => (
                <th key={section} scope="col">
                  {t(`check.sections.${section}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.scenario} data-status={row.status}>
                <th scope="row">
                  <span className="sp-ck-case-name">{nameOf(row)}</span>
                  {row.message !== null && (
                    <span className="sp-ck-note">{row.message}</span>
                  )}
                </th>
                {columns.map((section) => {
                  const cell = cellOf(row, section);
                  return (
                    <td key={section}>
                      {cell ? (
                        <CellButton
                          cell={cell}
                          letter={
                            letters.get(section)?.get(cell.fingerprint) ?? null
                          }
                          selected={
                            chosen?.scenario === row.scenario &&
                            chosen.section === section
                          }
                          label={`${nameOf(row)}, ${t(`check.sections.${section}`)}`}
                          onClick={() => {
                            setChosen({ scenario: row.scenario, section });
                          }}
                        />
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="sp-ck-note">
        {t("check.cases.legend", {
          matched: cells.matched,
          changed: cells.changed,
          unchecked: cells.unchecked,
          error: cells.error,
        })}{" "}
        <span title={t("check.cases.lettersHint")}>
          {t("check.cases.lettersShort")}
        </span>
      </p>
      {picked && pickedCell && chosen && (
        <section className="sp-ck-card" aria-label={t("check.cases.detail")}>
          <h3 className="sp-ck-h3">
            {nameOf(picked)}
            <span className="sp-ck-count">
              {t(`check.sections.${chosen.section}`)}
            </span>
          </h3>
          <p className="sp-ck-note">
            {t(`check.cases.cell.${pickedCell.status}`)}
            {pickedCell.status !== "error" &&
              `, ${t("check.cases.count", { count: pickedCell.count })}`}
            {pickedCell.changed === true &&
              `, ${t("check.cases.changedBefore")}`}
          </p>
          {picked.message !== null && <p>{picked.message}</p>}
          {changes.length > 0 ? (
            <CheckChangeEnv env={env}>
              <ChangeList changes={changes} />
            </CheckChangeEnv>
          ) : (
            <p className="sp-ck-note">
              {run.isFetching
                ? t("check.cases.loading")
                : pickedCell.status === "matched" ||
                    pickedCell.status === "unchecked"
                  ? t("check.cases.noDiff")
                  : t("check.cases.noDiffList")}
            </p>
          )}
          <div className="sp-ck-actions">
            <button
              type="button"
              className="btn sm primary"
              onClick={() => {
                env.showCase(picked.scenario);
              }}
            >
              {t("check.cases.show")}
            </button>
            <button
              type="button"
              className="btn sm"
              onClick={() => {
                nav.go({
                  extra: {
                    compare: "1",
                    left: `scenario:${picked.scenario}`,
                    right: null,
                  },
                });
              }}
            >
              {t("check.cases.compare")}
            </button>
          </div>
        </section>
      )}
    </div>
  );
};

const CellButton = ({
  cell,
  letter,
  selected,
  label,
  onClick,
}: {
  cell: MatrixCell;
  letter: string | null;
  selected: boolean;
  label: string;
  onClick: () => void;
}) => {
  const { t } = useTranslation("packSpace");
  const Icon = CELL_ICON[cell.status];
  const word = t(`check.cases.cell.${cell.status}`);
  return (
    <button
      type="button"
      className="sp-ck-cell"
      data-status={cell.status}
      aria-pressed={selected}
      aria-label={[
        label,
        word,
        cell.status !== "error"
          ? t("check.cases.count", { count: cell.count })
          : null,
        cell.changed === true ? t("check.cases.changedBefore") : null,
        letter ? t("check.cases.group", { letter }) : null,
      ]
        .filter((part) => part !== null)
        .join(". ")}
      onClick={onClick}
    >
      <span className="sp-ck-cell-word" aria-hidden="true">
        <Icon size="0.875rem" />
        {word}
      </span>
      <span className="sp-ck-cell-count" aria-hidden="true">
        {cell.status === "error" ? "–" : cell.count}
        {cell.changed === true ? " ~" : ""}
        {letter ? ` ${letter}` : ""}
      </span>
    </button>
  );
};
