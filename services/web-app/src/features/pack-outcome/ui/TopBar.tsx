import { lazy, Suspense, useEffect, useId, useState } from "react";
import { FolderTree, Lock, RefreshCw } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  packFilesPath,
  packOutcomePath,
  type OutcomeState,
  type PackTree,
  type PackTreePack,
  type PackTreeTemplate,
  type PackTreeVersion,
} from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { Select } from "@shared/ui";
import { writeOutcomeSearch, type OutcomeMode } from "../lib/urlState";
import { useOutcomeModel } from "../model";
import { PhoneBar } from "./phone/PhoneBar";
import { ProposeAction } from "./ProposeAction";
import { ScenarioActions, ScenarioPicker } from "./scenarios/ScenarioPicker";

// Переключатель данных только для разработки: в рабочей сборке этой ветки нет.
const DevSwitch = import.meta.env.DEV
  ? lazy(() => import("./DevSwitch"))
  : null;

export type OutcomeLocation = {
  pack: PackTreePack;
  template: PackTreeTemplate;
  version: PackTreeVersion;
};

type TopBarProps = {
  tree: PackTree;
  location: OutcomeLocation;
  /** Правки после последнего коммита (git): «Есть несохранённые правки». */
  dirty: boolean;
  /** Alt удерживается в режиме «Как студент»: центр временно показывает вид автора. */
  peek: boolean;
  /** Режим выбран кнопкой панели: экран объявляет его и переводит фокус в результат. */
  onModeChange: (mode: OutcomeMode) => void;
  onOpenFiles: () => void;
};

const STATES: readonly OutcomeState[] = ["work_tree", "head", "base"];
const MODES: readonly OutcomeMode[] = ["author", "student"];

/**
 * Верхняя панель: пак, шаблон, версия, сценарий, режим, откуда считать, состояние расчёта и
 * переходы к файлам. Смена шаблона и версии это переход по адресу (в историю), остальное
 * записывается в query текущего адреса.
 */
export const TopBar = ({
  tree,
  location,
  dirty,
  peek,
  onModeChange,
  onOpenFiles,
}: TopBarProps) => {
  const { t, i18n } = useTranslation("packOutcome");
  const navigate = useNavigate();
  const model = useOutcomeModel();
  const { workspaceId, url, outcome, ref, released } = model;
  const lang = i18n.language;
  const hintId = useId();

  const nameOf = (
    dict: Record<string, string> | null | undefined,
    fallback: string,
  ) => pickLocalized(dict ?? undefined, lang, fallback);

  const templates = tree.packs.flatMap((pack) =>
    pack.templates
      .filter((template) => template.versions.length > 0)
      .map((template) => ({
        value: `${pack.id}/${template.id}`,
        label: `${nameOf(pack.name, pack.id)} / ${nameOf(template.name, template.id)}`,
        pack,
        template,
      })),
  );

  const go = (target: { pack: string; template: string; version: string }) => {
    // Вводные, набор данных и выбор привязаны к словарю версии: при переходе не переносятся.
    // Сценарий живёт у шаблона, поэтому остаётся, пока шаблон тот же.
    const sameTemplate =
      target.pack === ref.pack && target.template === ref.template;
    const search = writeOutcomeSearch(new URLSearchParams(), {
      state: url.state.state,
      mode: url.state.mode,
      tab: url.state.tab,
      view: url.state.view,
      scenario: sameTemplate ? url.state.scenario : null,
    }).toString();
    void navigate(packOutcomePath(workspaceId, target, search));
  };

  const onTemplate = (value: string) => {
    const found = templates.find((item) => item.value === value);
    if (!found) return;
    const versions = found.template.versions;
    const version =
      versions.find((v) => v.version === found.template.default_version) ??
      versions[versions.length - 1];
    if (!version) return;
    go({
      pack: found.pack.id,
      template: found.template.id,
      version: version.version,
    });
  };

  const versionLabel = (v: PackTreeVersion) =>
    v.status ? `${v.version} (${v.status})` : v.version;

  const stateLabel: Record<OutcomeState, string> = {
    work_tree: t("bar.stateWorkTree"),
    head: t("bar.stateHead"),
    base: t("bar.stateBase"),
  };

  const templateSelect = (
    <Select
      id="po-template"
      ariaLabel={t("bar.template")}
      className="po-select"
      value={`${ref.pack}/${ref.template}`}
      options={templates.map(({ value, label }) => ({ value, label }))}
      onValueChange={onTemplate}
    />
  );
  const versionSelect = (
    <Select
      id="po-version"
      ariaLabel={t("bar.version")}
      className="po-select"
      value={ref.version}
      options={location.template.versions.map((v) => ({
        value: v.version,
        label: versionLabel(v),
      }))}
      onValueChange={(version) => {
        go({ ...ref, version });
      }}
    />
  );
  const modeSwitch = (
    <div
      className="po-field"
      role="group"
      aria-label={t("bar.mode")}
      aria-describedby={url.state.mode === "student" ? hintId : undefined}
    >
      <span className="po-field-label" aria-hidden="true">
        {t("bar.mode")}
      </span>
      <div className="po-segmented">
        {MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            className="po-segment"
            aria-pressed={url.state.mode === mode}
            data-testid={`outcome-mode-${mode}`}
            onClick={() => {
              if (url.state.mode === mode) return;
              url.update({ mode });
              onModeChange(mode);
            }}
          >
            {t(mode === "author" ? "bar.modeAuthor" : "bar.modeStudent")}
          </button>
        ))}
      </div>
      {url.state.mode === "student" && (
        <span
          id={hintId}
          className="po-note po-mode-hint po-hide-phone"
          data-peek={peek ? "true" : undefined}
          data-testid="outcome-mode-hint"
        >
          {t(peek ? "bar.modePeek" : "bar.modeHint")}
        </span>
      )}
    </div>
  );
  const stateSelect = (
    <label className="po-field" htmlFor="po-state">
      <span className="po-field-label">{t("bar.state")}</span>
      <Select
        id="po-state"
        ariaLabel={t("bar.state")}
        className="po-select"
        value={url.state.state}
        options={STATES.map((value) => ({
          value,
          label: stateLabel[value],
        }))}
        onValueChange={(next) => {
          url.update({ state: next as OutcomeState });
        }}
      />
    </label>
  );
  const lock = released && (
    <span
      className="ps-mark ps-mark-lock po-lock"
      title={t("bar.releasedMark")}
      data-testid="outcome-released-mark"
    >
      <Lock size="0.75rem" aria-hidden="true" />
      <span className="sr-only">{t("bar.releasedMark")}</span>
    </span>
  );
  const status = (quiet: boolean) => (
    <SaveStatus
      dirty={dirty}
      fetching={outcome.isFetching}
      failed={outcome.isError}
      quiet={quiet}
      onRetry={() => void outcome.refetch()}
    />
  );
  const dev = DevSwitch && (
    <Suspense fallback={null}>
      <DevSwitch workspaceId={workspaceId} />
    </Suspense>
  );

  if (model.phone) {
    const templateName = nameOf(location.template.name, ref.template);
    return (
      <PhoneBar
        title={templateName}
        version={ref.version}
        lock={lock}
        status={status(true)}
        studentMode={url.state.mode === "student"}
        optionsActive={
          url.state.state !== "work_tree" || url.state.mode === "student"
        }
        notice={released ? t("bar.released") : null}
        controls={
          <>
            <div className="po-phone-field">
              <span className="po-field-label">{t("bar.template")}</span>
              {templateSelect}
            </div>
            <div className="po-phone-field">
              <span className="po-field-label">{t("bar.version")}</span>
              {versionSelect}
            </div>
            {modeSwitch}
            {stateSelect}
            <ScenarioActions />
            <button
              type="button"
              className="btn"
              data-testid="outcome-files-open"
              onClick={onOpenFiles}
            >
              <FolderTree size="0.875rem" aria-hidden="true" />
              {t("bar.files")}
            </button>
            <Link
              className="btn"
              to={packFilesPath(workspaceId)}
              data-testid="outcome-files-mode"
            >
              {t("bar.filesMode")}
            </Link>
            {status(false)}
            {dev}
          </>
        }
      />
    );
  }

  return (
    <div className="po-bar" role="group" aria-label={t("bar.label")}>
      <div className="po-bar-row">
        <div className="po-crumbs" data-testid="outcome-crumbs">
          {templateSelect}
          {versionSelect}
          {lock}
        </div>
        <div className="po-bar-actions">
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-files-open"
            onClick={onOpenFiles}
          >
            <FolderTree size="0.875rem" aria-hidden="true" />
            {t("bar.files")}
          </button>
          <Link
            className="btn sm po-hide-phone"
            to={packFilesPath(workspaceId)}
            title={t("bar.filesModeHint")}
            data-testid="outcome-files-mode"
          >
            {t("bar.filesMode")}
          </Link>
          <ProposeAction />
        </div>
      </div>
      <div className="po-bar-row">
        <ScenarioPicker />
        {modeSwitch}
        {stateSelect}
        {status(false)}
        {dev}
      </div>
    </div>
  );
};

type SaveStatusProps = {
  /** Тихий вид (телефон): пока всё в порядке, статус слышат программы экрана, но не рисуется. */
  quiet?: boolean;
  dirty: boolean;
  fetching: boolean;
  failed: boolean;
  onRetry: () => void;
};

/** Состояние сохранения и пересчёта: объявляется программам экрана (role="status"). */
const SaveStatus = ({
  quiet = false,
  dirty,
  fetching,
  failed,
  onRetry,
}: SaveStatusProps) => {
  const { t } = useTranslation("packOutcome");
  const slow = useSlow(fetching && !failed);
  const text = failed
    ? t("status.failed")
    : fetching
      ? t(slow ? "status.slow" : "status.recalculating")
      : dirty
        ? t("status.dirty")
        : t("status.saved");
  const calm = quiet && !failed && !fetching && !dirty;
  return (
    <div
      className={calm ? "po-status sr-only" : "po-status"}
      role="status"
      data-state={
        failed ? "failed" : fetching ? "busy" : dirty ? "dirty" : "ok"
      }
      data-testid="outcome-status"
    >
      {fetching && !failed && (
        <RefreshCw size="0.75rem" aria-hidden="true" className="po-spin" />
      )}
      <span>{text}</span>
      {failed && (
        <button
          type="button"
          className="po-link"
          data-testid="outcome-status-retry"
          onClick={onRetry}
        >
          {t("status.retry")}
        </button>
      )}
    </div>
  );
};

/** Пересчёт дольше двух секунд: подпись меняется на «идёт долго» (раздел 3.10). */
const useSlow = (active: boolean): boolean => {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) return undefined;
    const timer = setTimeout(() => {
      setSlow(true);
    }, 2000);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [active]);
  return active && slow;
};
