import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { PanelLeftOpen, PanelRightOpen } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import {
  packErrorText,
  packFilesPath,
  packWorkspacePath,
  usePackGit,
  usePackOutcome,
  usePackOutcomeInputs,
  usePackScenarios,
  usePackTree,
  type OutcomeElementRef,
  type PackOutcomeRequest,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import { useIsPhoneWidth } from "@shared/lib";
import { EmptyState, ErrorState, Modal, Spinner } from "@shared/ui";
import { elementKey, linkedElements } from "./lib/inputs";
import { useLastDefined } from "./lib/lastDefined";
import { useOutcomePanels } from "./lib/panels";
import { useOutcomeUrlState } from "./lib/urlState";
import { summarize } from "./lib/summary";
import { OutcomeModelContext, type OutcomeModel } from "./model";
import { FilesDrawer } from "./ui/FilesDrawer";
import { Footer } from "./ui/Footer";
import { InputsPanel } from "./ui/InputsPanel";
import { Notice } from "./ui/Notice";
import { PanelShell } from "./ui/PanelShell";
import { ResultCenter } from "./ui/ResultCenter";
import { RulesPanel } from "./ui/RulesPanel";
import { Splitter } from "./ui/Splitter";
import { TopBar, type OutcomeLocation } from "./ui/TopBar";
import "./outcome.css";

export type OutcomeBodyProps = {
  workspace: PackWorkspace;
  /** Версия из адреса экрана: имена папок пака, шаблона и версии. */
  version: PackVersionRef;
};

const findLocation = (
  tree: PackTree | undefined,
  version: PackVersionRef,
): OutcomeLocation | null => {
  for (const pack of tree?.packs ?? []) {
    if (pack.id !== version.pack) continue;
    for (const template of pack.templates) {
      if (template.id !== version.template) continue;
      const found = template.versions.find(
        (v) => v.version === version.version,
      );
      if (found) return { pack, template, version: found };
    }
  }
  return null;
};

const sameElement = (a: OutcomeElementRef | null, b: OutcomeElementRef) =>
  a !== null && a.section === b.section && a.id === b.id;

/**
 * Экран «Результат» (template-studio-outcome.md, срез F1): что получит студент при выбранных
 * вводных. Каркас из верхней панели и трёх колонок «Вводные | Результат | Правила и причины».
 * Состояние живёт в адресе, данные приходят хуками контракта (на эталонах, пока нет сервера),
 * наполнение панелей и секций делают срезы F2 до F7. Клиент условий не считает.
 */
export const OutcomeBody = ({ workspace, version }: OutcomeBodyProps) => {
  const { t } = useTranslation("packOutcome");
  const navigate = useNavigate();
  const phone = useIsPhoneWidth();
  const url = useOutcomeUrlState();
  const panels = useOutcomePanels();
  const tree = usePackTree(workspace.id);
  const git = usePackGit(workspace.id, workspace.kind === "git");
  const [filesOpen, setFilesOpen] = useState(false);
  const inputsRef = useRef<HTMLElement>(null);
  const resultRef = useRef<HTMLElement>(null);
  const rulesRef = useRef<HTMLElement>(null);

  const location = findLocation(tree.data, version);
  const found = location !== null;
  const request: PackOutcomeRequest = {
    state: url.state.state,
    scenario: url.state.scenario,
    example: url.state.example,
    inputs: url.state.inputs,
  };
  const outcome = usePackOutcome(workspace.id, version, request, found);
  const inputs = usePackOutcomeInputs(
    workspace.id,
    version,
    url.state.state,
    found,
  );
  const scenarios = usePackScenarios(
    workspace.id,
    version.pack,
    version.template,
    found,
  );
  const shown = useLastDefined(outcome.data);
  const stale = outcome.isPlaceholderData || outcome.isError;

  // Подсветка связанных с вводной элементов: связи берутся из трассы показанного результата.
  const [highlightInput, setHighlightInput] = useState<string | null>(null);
  const highlightElements = useMemo(
    () =>
      new Set(
        highlightInput === null
          ? []
          : linkedElements(shown, highlightInput).map(elementKey),
      ),
    [shown, highlightInput],
  );

  const { update } = url;
  const select = useCallback(
    (element: OutcomeElementRef | null) => {
      const next =
        element !== null && sameElement(url.state.selected, element)
          ? null
          : element;
      // На телефоне «Почему?» отдельная вкладка: выбор открывает её.
      update({ selected: next, ...(phone && next ? { tab: "rules" } : {}) });
    },
    [phone, update, url.state.selected],
  );

  const model: OutcomeModel = {
    workspaceId: workspace.id,
    ref: version,
    released: location?.version.released ?? false,
    phone,
    url,
    request,
    outcome,
    shown,
    stale,
    inputs,
    scenarios,
    select,
    highlight: {
      input: highlightInput,
      elements: highlightElements,
      setInput: setHighlightInput,
    },
  };

  // F6 и Shift+F6 переводят фокус между тремя областями, Alt+Z показывает и прячет «Почему?».
  const student = url.state.mode === "student";
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "F6") {
      const regions = [inputsRef, resultRef, rulesRef]
        .map((r) => r.current)
        .filter((el): el is HTMLElement => el !== null);
      if (regions.length === 0) return;
      event.preventDefault();
      const at = regions.findIndex((el) => el.contains(document.activeElement));
      const step = event.shiftKey ? -1 : 1;
      const next = regions[(at + step + regions.length) % regions.length];
      next?.focus();
    } else if (event.altKey && event.code === "KeyZ" && !student) {
      event.preventDefault();
      if (phone)
        update({ tab: url.state.tab === "rules" ? "result" : "rules" });
      else panels.setRightCollapsed(!panels.rightCollapsed);
    }
  };

  const openFile = (path: string) => {
    setFilesOpen(false);
    void navigate(packWorkspacePath(workspace.id, path));
  };

  if (tree.isPending) {
    return (
      <div className="po-gate" data-testid="outcome-tree-loading">
        <Spinner size="md" />
      </div>
    );
  }
  if (tree.data === undefined) {
    return (
      <div className="po-state">
        <ErrorState
          framed
          title={t("errors.treeFailed")}
          description={packErrorText(tree.error)}
          onRetry={() => void tree.refetch()}
          testId="outcome-tree-error"
        />
      </div>
    );
  }
  if (!location) {
    return (
      <div className="po-state">
        <EmptyState
          framed
          title={t("errors.versionMissingTitle")}
          description={t("errors.versionMissingLead", {
            version: version.version,
            template: version.template,
          })}
          action={
            <Link className="btn sm" to={packFilesPath(workspace.id)}>
              {t("errors.openFiles")}
            </Link>
          }
          testId="outcome-version-missing"
        />
      </div>
    );
  }

  const summary = shown ? summarize(shown) : null;
  const announce = summary
    ? t("result.announce", {
        active: summary.documentsActive,
        total: summary.documentsTotal,
        signers: summary.signers,
      })
    : "";
  const changedInputs = Object.keys(url.state.inputs).length;
  const inputsTitle = t("regions.inputs");
  const resultTitle = t("regions.result");
  const rulesTitle = t("regions.rules");

  const center = (
    <section
      ref={resultRef}
      id="po-result"
      tabIndex={-1}
      aria-label={resultTitle}
      className="po-center"
      data-testid="outcome-center"
    >
      <ResultCenter />
    </section>
  );

  return (
    <OutcomeModelContext.Provider value={model}>
      <div
        className="po-screen"
        data-testid="outcome-screen"
        data-mode={url.state.mode}
        data-phone={phone ? "true" : undefined}
        onKeyDown={onKeyDown}
      >
        <a
          className="po-skip"
          href="#po-result"
          onClick={(event) => {
            event.preventDefault();
            resultRef.current?.focus();
          }}
        >
          {t("skip")}
        </a>
        <TopBar
          tree={tree.data}
          location={location}
          dirty={git.data?.dirty ?? false}
          onOpenFiles={() => {
            setFilesOpen(true);
          }}
        />
        {model.released && (
          <Notice
            tone="info"
            title={t("bar.released")}
            testId="outcome-released"
          />
        )}
        {phone ? (
          <>
            <div className="po-body po-body-phone">{center}</div>
            <nav className="po-tabs" aria-label={t("phone.tabs")}>
              {(
                [
                  ["inputs", t("phone.inputs")],
                  ["result", t("phone.result")],
                  ["rules", t("phone.rules")],
                ] as const
              )
                .filter(([tab]) => !(student && tab === "rules"))
                .map(([tab, label]) => (
                  <button
                    key={tab}
                    type="button"
                    className="po-tab"
                    aria-pressed={url.state.tab === tab}
                    data-testid={`outcome-tab-${tab}`}
                    onClick={() => {
                      update({ tab });
                    }}
                  >
                    {label}
                    {tab === "inputs" && changedInputs > 0 && (
                      <span className="po-badge">{changedInputs}</span>
                    )}
                  </button>
                ))}
            </nav>
            <Modal
              isOpen={url.state.tab === "inputs"}
              onClose={() => {
                update({ tab: "result" });
              }}
              title={inputsTitle}
            >
              <InputsPanel />
            </Modal>
            <Modal
              isOpen={url.state.tab === "rules" && !student}
              onClose={() => {
                update({ tab: "result" });
              }}
              title={rulesTitle}
            >
              <RulesPanel />
              <p className="po-stub">{t("phone.readOnly")}</p>
            </Modal>
          </>
        ) : (
          <div className="po-body">
            {panels.leftCollapsed ? (
              <aside className="po-rail" data-side="left">
                <button
                  type="button"
                  className="icon-btn sm"
                  aria-label={t("panels.expand", { name: inputsTitle })}
                  title={t("panels.expand", { name: inputsTitle })}
                  data-testid="outcome-inputs-expand"
                  onClick={() => {
                    panels.setLeftCollapsed(false);
                  }}
                >
                  <PanelLeftOpen size="0.9375rem" aria-hidden="true" />
                </button>
                {changedInputs > 0 && (
                  <span
                    className="po-badge"
                    title={t("panels.changed", { count: changedInputs })}
                    data-testid="outcome-inputs-badge"
                  >
                    {changedInputs}
                  </span>
                )}
              </aside>
            ) : (
              <>
                <PanelShell
                  ref={inputsRef}
                  side="left"
                  title={inputsTitle}
                  testId="outcome-inputs-panel"
                  width={panels.left.width}
                  controls={{
                    collapse: () => {
                      panels.setLeftCollapsed(true);
                    },
                    nudge: panels.left.nudge,
                  }}
                >
                  <InputsPanel />
                </PanelShell>
                <Splitter
                  resize={panels.left}
                  min={232}
                  max={440}
                  name={inputsTitle}
                  testId="outcome-inputs-splitter"
                />
              </>
            )}
            {center}
            {student ? null : panels.rightCollapsed ? (
              <aside className="po-rail" data-side="right">
                <button
                  type="button"
                  className="icon-btn sm"
                  aria-label={t("panels.expand", { name: rulesTitle })}
                  title={t("panels.expand", { name: rulesTitle })}
                  data-testid="outcome-rules-expand"
                  onClick={() => {
                    panels.setRightCollapsed(false);
                  }}
                >
                  <PanelRightOpen size="0.9375rem" aria-hidden="true" />
                </button>
                {url.state.selected && (
                  <button
                    type="button"
                    className="btn sm po-rail-why"
                    data-testid="outcome-rail-why"
                    onClick={() => {
                      panels.setRightCollapsed(false);
                    }}
                  >
                    {t("panels.why")}
                  </button>
                )}
              </aside>
            ) : (
              <>
                <Splitter
                  resize={panels.right}
                  min={264}
                  max={560}
                  name={rulesTitle}
                  testId="outcome-rules-splitter"
                />
                <PanelShell
                  ref={rulesRef}
                  side="right"
                  title={rulesTitle}
                  testId="outcome-rules-panel"
                  width={panels.right.width}
                  controls={{
                    collapse: () => {
                      panels.setRightCollapsed(true);
                    },
                    nudge: panels.right.nudge,
                  }}
                >
                  <RulesPanel />
                </PanelShell>
              </>
            )}
          </div>
        )}
        <Footer />
        <div
          className="sr-only"
          role="status"
          aria-live="polite"
          data-testid="outcome-live"
        >
          {announce}
        </div>
        <FilesDrawer
          workspaceId={workspace.id}
          open={filesOpen}
          onClose={() => {
            setFilesOpen(false);
          }}
          onSelect={openFile}
        />
      </div>
    </OutcomeModelContext.Provider>
  );
};
