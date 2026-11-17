import { useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { BookmarkPlus, ChevronDown, RefreshCw, Settings2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { packErrorText } from "@entities/pack-studio";
import { Popover, PopoverContent, PopoverTrigger } from "@shared/ui";
import {
  badgeOf,
  notPassing,
  scenarioName,
  tallyText,
} from "../../lib/scenarios";
import { useOutcomeModel } from "../../model";
import { Notice } from "../Notice";
import { useScenarioUi, type ScenarioUi } from "./context";
import { ScenarioStatus } from "./ScenarioStatus";

/** Значение «без сценария»: его выбор убирает сценарий из адреса. */
const NONE = "";

const Examples = () => {
  const { t } = useTranslation("packOutcome");
  return (
    <div className="po-sc-empty" data-testid="scenario-empty">
      <p className="po-sc-empty-title">{t("scenarios.empty.title")}</p>
      <p className="po-sc-empty-lead">{t("scenarios.empty.lead")}</p>
      <ul className="po-sc-examples">
        <li>{t("scenarios.empty.exampleCoursework")}</li>
        <li>{t("scenarios.empty.exampleVkr")}</li>
      </ul>
    </div>
  );
};

type ListProps = { ui: ScenarioUi; close: () => void };

/** Выбор сценария списком: значок статуса у каждого, итог прогона и «Прогнать все». */
const ScenarioList = ({ ui, close }: ListProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const chosen = url.state.scenario;
  const listRef = useRef<HTMLDivElement>(null);
  const { entries } = ui;

  const options = () =>
    Array.from(
      listRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? [],
    );
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const items = options();
    const at = items.findIndex((el) => el === document.activeElement);
    const go = (to: number) => {
      event.preventDefault();
      items[(to + items.length) % items.length]?.focus();
    };
    if (event.key === "ArrowDown") go(at + 1);
    else if (event.key === "ArrowUp") go(at <= 0 ? items.length - 1 : at - 1);
    else if (event.key === "Home") go(0);
    else if (event.key === "End") go(items.length - 1);
  };

  const select = (id: string) => {
    url.update({ scenario: id === NONE ? null : id });
    close();
  };
  const summary = tallyText(t, ui.tally);
  const missing =
    chosen !== null &&
    !ui.loading &&
    !entries.some((entry) => entry.id === chosen);

  return (
    <>
      <div className="po-sc-head">
        <p
          className="po-sc-summary"
          role="status"
          data-testid="scenario-summary"
        >
          {ui.runState === "loading" && ui.run === undefined
            ? t("scenarios.running")
            : summary}
        </p>
        <button
          type="button"
          className="btn sm"
          disabled={ui.running || ui.tally.total === 0}
          data-testid="scenario-run-all"
          onClick={ui.rerun}
        >
          <RefreshCw
            size="0.8125rem"
            aria-hidden="true"
            className={ui.running ? "po-spin" : undefined}
          />
          {t("scenarios.runAll")}
        </button>
      </div>
      {ui.runState === "failed" && (
        <Notice
          tone="error"
          title={t("scenarios.runFailed")}
          testId="scenario-run-error"
          actions={
            <button type="button" className="btn sm" onClick={ui.rerun}>
              {t("status.retry")}
            </button>
          }
        >
          {packErrorText(ui.runError)}
        </Notice>
      )}
      <div
        ref={listRef}
        className="po-sc-list"
        role="listbox"
        aria-label={t("scenarios.list")}
        onKeyDown={onKeyDown}
        data-testid="scenario-list"
      >
        <button
          type="button"
          role="option"
          aria-selected={chosen === null}
          className="po-sc-option"
          data-testid="scenario-option-none"
          onClick={() => {
            select(NONE);
          }}
        >
          <span className="po-sc-name">{t("bar.noScenario")}</span>
        </button>
        {entries.map((entry) => {
          const badge = badgeOf(entry, ui.results, ui.runState);
          const broken = badge === "broken";
          const selected = chosen === entry.id;
          const hintId = `po-sc-hint-${entry.id}`;
          return (
            <button
              key={entry.id}
              type="button"
              role="option"
              aria-selected={selected}
              aria-disabled={broken && !selected ? true : undefined}
              aria-describedby={broken ? hintId : undefined}
              className="po-sc-option"
              data-testid={`scenario-option-${entry.id}`}
              onClick={() => {
                if (!broken || selected) select(entry.id);
              }}
            >
              <ScenarioStatus status={badge} iconOnly />
              <span className="po-sc-name">
                {scenarioName(entry, i18n.language)}
              </span>
              <span className="po-sc-state">
                {t(`scenarios.status.${badge}`)}
              </span>
              {broken && (
                <span className="po-sc-reason" id={hintId}>
                  {entry.error}
                </span>
              )}
            </button>
          );
        })}
        {missing && (
          <button
            type="button"
            role="option"
            aria-selected
            className="po-sc-option"
            data-testid="scenario-option-missing"
            onClick={close}
          >
            <span className="po-sc-name">
              {t("bar.scenarioMissing", { id: chosen })}
            </span>
          </button>
        )}
      </div>
      {entries.length === 0 && !ui.loading && <Examples />}
    </>
  );
};

/**
 * «Сохранить как сценарий» и «Управление» выбранным сценарием. На телефоне живут в листе
 * «Параметры», на компьютере рядом с выбором сценария.
 */
export const ScenarioActions = () => {
  const { t } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const ui = useScenarioUi();
  if (!ui || ui.readOnlyReason === "student") return null;
  const chosen = url.state.scenario;
  const entry = ui.entries.find((item) => item.id === chosen);
  const writeHint =
    ui.readOnlyReason === "state"
      ? t("scenarios.readOnlyState")
      : t("scenarios.readOnlyStudent");
  return (
    <div className="po-sc-actions">
      <button
        type="button"
        className="btn sm"
        disabled={!ui.canWrite}
        title={ui.canWrite ? undefined : writeHint}
        data-testid="scenario-save-as"
        onClick={() => {
          ui.open({ kind: "create" });
        }}
      >
        <BookmarkPlus size="0.875rem" aria-hidden="true" />
        {t("scenarios.saveAs")}
      </button>
      {chosen !== null && entry && (
        <button
          type="button"
          className="btn sm"
          data-testid="scenario-manage"
          onClick={() => {
            ui.open({ kind: "panel", id: chosen });
          }}
        >
          <Settings2 size="0.875rem" aria-hidden="true" />
          {t("scenarios.manage")}
        </button>
      )}
    </div>
  );
};

/**
 * Выбор сценария в верхней панели. Кнопка показывает выбранный сценарий и счётчик «1 из 3»,
 * список открывается панелью (листом на телефоне): статус прогона у каждого, итог и «Прогнать
 * все». Рядом «Сохранить как сценарий» и «Управление» выбранным сценарием.
 */
export const ScenarioPicker = ({
  withActions = true,
}: {
  /** Телефон показывает действия отдельно, в листе «Параметры». */
  withActions?: boolean;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { url } = useOutcomeModel();
  const ui = useScenarioUi();
  const contentRef = useRef<HTMLDivElement>(null);
  if (!ui) return null;

  const chosen = url.state.scenario;
  const open = ui.dialog?.kind === "picker";
  const setOpen = (next: boolean) => {
    ui.open(next ? { kind: "picker" } : null);
  };
  const entry = ui.entries.find((item) => item.id === chosen);
  const bad = notPassing(ui.tally);
  const triggerName = ui.loading
    ? t("scenarios.loading")
    : ui.loadFailed !== null
      ? t("scenarios.loadFailedShort")
      : chosen === null
        ? ui.entries.length === 0
          ? t("bar.noScenarios")
          : t("bar.noScenario")
        : entry
          ? scenarioName(entry, i18n.language)
          : t("bar.scenarioMissing", { id: chosen });

  return (
    <div className="po-sc" data-testid="scenario-picker">
      <div className="po-field">
        <span className="po-field-label" aria-hidden="true">
          {t("bar.scenario")}
        </span>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              id="po-scenario"
              className="input po-sc-trigger"
              role="combobox"
              aria-haspopup="listbox"
              aria-expanded={open}
              aria-label={t("bar.scenario")}
              data-testid="scenario-trigger"
            >
              {entry && (
                <ScenarioStatus
                  status={badgeOf(entry, ui.results, ui.runState)}
                  iconOnly
                />
              )}
              <span className="po-sc-trigger-name">{triggerName}</span>
              {bad > 0 && (
                <span
                  className="po-sc-chip"
                  title={t("scenarios.chipTitle", {
                    bad,
                    total: ui.tally.total,
                  })}
                  data-testid="scenario-chip"
                >
                  {t("scenarios.chip", { bad, total: ui.tally.total })}
                </span>
              )}
              <ChevronDown size="0.875rem" aria-hidden="true" />
            </button>
          </PopoverTrigger>
          <PopoverContent
            ref={contentRef}
            width={420}
            align="start"
            aria-label={t("scenarios.panelLabel")}
            onOpenAutoFocus={(event) => {
              event.preventDefault();
              contentRef.current
                ?.querySelector<HTMLElement>(
                  '[role="option"][aria-selected="true"]',
                )
                ?.focus();
            }}
          >
            {ui.loading ? (
              <p className="po-sc-summary" data-testid="scenario-loading">
                {t("scenarios.loading")}
              </p>
            ) : ui.loadFailed !== null ? (
              <Notice
                tone="error"
                title={t("scenarios.loadFailed")}
                testId="scenario-load-error"
                actions={
                  <button type="button" className="btn sm" onClick={ui.reload}>
                    {t("status.retry")}
                  </button>
                }
              >
                {packErrorText(ui.loadFailed)}
              </Notice>
            ) : (
              <ScenarioList
                ui={ui}
                close={() => {
                  setOpen(false);
                }}
              />
            )}
          </PopoverContent>
        </Popover>
      </div>
      {withActions && <ScenarioActions />}
    </div>
  );
};
