import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type {
  OutcomeBranch,
  OutcomeDocument,
  OutcomeSection,
  OutcomeSectionDelta,
  PackOutcome,
} from "@entities/pack-studio";
import { Badge, EmptyState, NoResults } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import type { OutcomeSelection } from "../../lib/urlState";
import { useOutcomePart, type PartState } from "../../lib/part";
import { useOutcomeModel } from "../../model";
import { PartStatus, RowsSkeleton } from "./PartStatus";
import { useSectionCollapse } from "../../lib/sectionCollapse";
import { SectionShell } from "./SectionShell";
import { FilterBar, GroupTitle, PickButton, Reason, Stats } from "./parts";
import { matches, onArrowNav, useIsSelected } from "./helpers";
import { useApplyInput, type ApplyInput } from "../../lib/applyInput";
import type { Explainer } from "../../lib/explain";
import { useExplain } from "./useExplain";

/** Строка с кнопкой выбора и действиями рядом: кнопка в кнопку не вкладывается. */
const PickRow = ({
  el,
  muted = false,
  testId,
  title,
  badges,
  children,
  actions,
}: {
  el: OutcomeSelection;
  muted?: boolean;
  testId: string;
  title: ReactNode;
  badges?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}) => {
  const selected = useIsSelected(el);
  return (
    <li
      className="po-item"
      data-muted={muted ? "true" : undefined}
      data-selected={selected ? "true" : undefined}
      data-testid={testId}
    >
      <PickButton el={el} title={title} badges={badges}>
        {children}
      </PickButton>
      {actions && <div className="po-actions">{actions}</div>}
    </li>
  );
};

/** Изменения по разделу: `+`, `~`, `-` значком и словами для программы экрана. */
const Delta = ({
  delta,
  testId,
}: {
  delta: OutcomeSectionDelta;
  testId: string;
}) => {
  const { t } = useTranslation("packOutcome");
  const parts = [
    ["added", "+", delta.added],
    ["changed", "~", delta.changed],
    ["removed", "-", delta.removed],
  ] as const;
  return (
    <span className="po-delta" data-testid={testId}>
      <span className="po-delta-section">{t(`sections.${delta.section}`)}</span>
      {parts
        .filter(([, , count]) => count > 0)
        .map(([kind, mark, count]) => (
          <span key={kind} className="po-delta-part" data-kind={kind}>
            <span aria-hidden="true">{`${mark}${String(count)}`}</span>
            <span className="sr-only">
              {t(`branches.delta.${kind}`, { count })}
            </span>
          </span>
        ))}
    </span>
  );
};

type Apply = ApplyInput;

const VariantRow = ({
  doc,
  outcome,
  apply,
}: {
  doc: OutcomeDocument;
  outcome: PackOutcome;
  apply: Apply;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { inputs } = useOutcomeModel();
  const lang = i18n.language;
  const name = pickLocalized(doc.name, lang, doc.id);
  const key = `variant.${doc.id}`;
  const settable = inputs.data?.inputs.some((i) => i.id === key) === true;
  const projectLang = outcome.inputs.lang ?? "";
  return (
    <PickRow
      el={{ section: "documents", id: doc.id }}
      muted={doc.state !== "active"}
      testId={`outcome-variants-${doc.id}`}
      title={name}
      badges={
        doc.state === "inactive" ? (
          <Badge variant="warning">{t("documents.state.inactive")}</Badge>
        ) : undefined
      }
      actions={
        settable ? (
          <>
            {doc.variants
              .filter((v) => v.available && !v.chosen)
              .map((v) => {
                const label = pickLocalized(v.label, lang, v.id);
                return (
                  <button
                    key={v.id}
                    type="button"
                    className="btn sm"
                    data-testid={`outcome-variants-${doc.id}-show-${v.id}`}
                    aria-label={t("branches.showVariant", { name, label })}
                    onClick={() => {
                      apply(key, v.id);
                    }}
                  >
                    {t("branches.showThis", { label })}
                  </button>
                );
              })}
          </>
        ) : undefined
      }
    >
      <span className="po-variants">
        {doc.variants.map((v) => {
          const label = pickLocalized(v.label, lang, v.id);
          return (
            <Badge
              key={v.id}
              variant={v.chosen ? "accent" : "subtle"}
              data-testid={`outcome-variants-${doc.id}-${v.id}`}
              data-available={v.available ? "true" : "false"}
              data-chosen={v.chosen ? "true" : "false"}
            >
              {label}
              {v.chosen && (
                <span className="po-variant-off">
                  {t("branches.variantChosen")}
                </span>
              )}
              {!v.available && (
                <span className="po-variant-off">
                  {v.langs.length > 0
                    ? t("documents.variantOnly", { langs: v.langs.join(", ") })
                    : t("documents.variantOff")}
                </span>
              )}
            </Badge>
          );
        })}
      </span>
      {doc.variants.some((v) => !v.available && v.langs.length > 0) && (
        <span className="po-note">
          {t("branches.variantLang", { lang: projectLang })}
        </span>
      )}
    </PickRow>
  );
};

const FallbackRow = ({
  doc,
  lang: projectLang,
}: {
  doc: OutcomeDocument;
  lang: string;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  return (
    <PickRow
      el={{ section: "documents", id: doc.id }}
      muted={doc.state !== "active"}
      testId={`outcome-fallback-${doc.id}`}
      title={pickLocalized(doc.name, i18n.language, doc.id)}
      badges={<Badge variant="warning">{t("branches.fallbackBadge")}</Badge>}
    >
      <Reason texts={[t("documents.fallback", { lang: projectLang })]} />
      <span className="po-langs">
        <span className="po-note">{t("documents.languages")}</span>
        <span className="po-mono">{doc.languages.join(", ")}</span>
      </span>
    </PickRow>
  );
};

const BranchRow = ({
  branch,
  apply,
  explain,
}: {
  branch: OutcomeBranch;
  apply: Apply;
  explain: Explainer;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const lang = i18n.language;
  const label = branch.label
    ? pickLocalized(branch.label, lang, branch.input)
    : explain.subject(branch.input);
  const valueLabel = (value: string, dict: Record<string, string> | null) =>
    dict
      ? pickLocalized(dict, lang, value)
      : explain.value(branch.input, value);
  return (
    <PickRow
      el={{ section: "branches", id: branch.input }}
      testId={`outcome-branch-${branch.input}`}
      title={label}
      badges={
        <>
          <Badge variant="accent">
            {valueLabel(
              branch.chosen,
              branch.alternatives.find((a) => a.value === branch.chosen)
                ?.label ?? null,
            )}
          </Badge>
          {branch.affects.map((section) => (
            <Badge key={section} variant="subtle">
              {t(`sections.${section}`)}
            </Badge>
          ))}
        </>
      }
      actions={
        <ul
          className="po-alts"
          aria-label={t("branches.alternatives", { name: label })}
        >
          {branch.alternatives.map((alt) => {
            const chosen = alt.value === branch.chosen;
            const text = valueLabel(alt.value, alt.label);
            return (
              <li
                key={alt.value}
                className="po-alt"
                data-chosen={chosen ? "true" : undefined}
                data-testid={`outcome-branch-${branch.input}-${alt.value}`}
              >
                <span className="po-alt-value">{text}</span>
                {chosen ? (
                  <Badge variant="accent">{t("branches.current")}</Badge>
                ) : alt.delta.length === 0 ? (
                  <span className="po-note">{t("branches.noChange")}</span>
                ) : (
                  <span className="po-deltas">
                    {alt.delta.map((d) => (
                      <Delta
                        key={d.section}
                        delta={d}
                        testId={`outcome-branch-${branch.input}-${alt.value}-${d.section}`}
                      />
                    ))}
                  </span>
                )}
                {!chosen && (
                  <button
                    type="button"
                    className="btn sm"
                    data-testid={`outcome-branch-${branch.input}-show-${alt.value}`}
                    aria-label={t("branches.showInput", {
                      name: label,
                      value: text,
                    })}
                    onClick={() => {
                      apply(branch.input, alt.value);
                    }}
                  >
                    {t("branches.show")}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      }
    />
  );
};

const WorkspaceBlock = ({ outcome }: { outcome: PackOutcome }) => {
  const { t } = useTranslation("packOutcome");
  const { workspaceKind, git } = useOutcomeModel();
  const id = useId();
  const stateKey = {
    work_tree: "bar.stateWorkTree",
    head: "bar.stateHead",
    base: "bar.stateBase",
  } as const;
  return (
    <div className="po-group" data-testid="outcome-branches-workspace">
      <GroupTitle id={id}>{t("branches.workspace.title")}</GroupTitle>
      <dl className="po-facts" aria-labelledby={id}>
        {workspaceKind === "folder" ? (
          <div className="po-fact">
            <dt className="po-note">{t("branches.workspace.branch")}</dt>
            <dd data-testid="outcome-branches-folder">
              {t("branches.workspace.folder")}
            </dd>
          </div>
        ) : git ? (
          <>
            <div className="po-fact">
              <dt className="po-note">{t("branches.workspace.branch")}</dt>
              <dd className="po-mono" data-testid="outcome-branches-branch">
                {git.branch ?? t("branches.workspace.noBranch")}
              </dd>
            </div>
            <div className="po-fact">
              <dt className="po-note">{t("branches.workspace.base")}</dt>
              <dd className="po-mono" data-testid="outcome-branches-base">
                {git.base_branch ?? t("branches.workspace.noBranch")}
              </dd>
            </div>
            <div className="po-fact">
              <dt className="po-note">{t("branches.workspace.drift")}</dt>
              <dd data-testid="outcome-branches-drift">
                {t("branches.workspace.driftValue", {
                  ahead: git.ahead,
                  behind: git.behind,
                })}
              </dd>
            </div>
            <div className="po-fact">
              <dt className="po-note">{t("branches.workspace.uncommitted")}</dt>
              <dd data-testid="outcome-branches-uncommitted">
                {git.uncommitted.length}
              </dd>
            </div>
          </>
        ) : (
          <div className="po-fact">
            <dt className="po-note">{t("branches.workspace.branch")}</dt>
            <dd data-testid="outcome-branches-nogit">
              {t("branches.workspace.noGit")}
            </dd>
          </div>
        )}
        <div className="po-fact">
          <dt className="po-note">{t("branches.workspace.state")}</dt>
          <dd data-testid="outcome-branches-state">
            {t(stateKey[outcome.state])}
          </dd>
        </div>
        <div className="po-fact">
          <dt className="po-note">{t("branches.workspace.fingerprint")}</dt>
          <dd className="po-mono" data-testid="outcome-branches-fingerprint">
            {outcome.fingerprint}
          </dd>
        </div>
      </dl>
      <ul className="po-prints" data-testid="outcome-branches-prints">
        {outcome.digest.sections.map((print) => (
          <li
            key={print.section}
            className="po-print"
            data-testid={`outcome-branches-print-${print.section}`}
          >
            <span>{t(`sections.${print.section}`)}</span>
            <span className="po-print-count">{print.count}</span>
            <span className="po-mono po-note" title={print.fingerprint}>
              {print.fingerprint.slice(0, 7)}
            </span>
          </li>
        ))}
      </ul>
      <p className="po-note">{t("branches.workspace.compareNote")}</p>
    </div>
  );
};

const BranchesBody = ({
  outcome,
  state,
}: {
  outcome: PackOutcome;
  state: PartState<"branches">;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { stale } = useOutcomeModel();
  const apply = useApplyInput();
  const explain = useExplain(outcome);
  const [query, setQuery] = useState("");
  const [affects, setAffects] = useState<"all" | OutcomeSection>("all");
  const affectsId = useId();
  const variantsId = useId();
  const langId = useId();
  const branchesId = useId();
  const lang = i18n.language;
  const projectLang = outcome.inputs.lang ?? "";

  const branches = state.items ?? null;
  const variantDocs = outcome.documents.filter(
    (d) => d.variants.length > 0 && d.state !== "absent",
  );
  const fallbackDocs = outcome.documents.filter(
    (d) => d.state !== "absent" && d.lang_state === "fallback",
  );

  const docMatches = (d: OutcomeDocument) =>
    matches(
      query,
      pickLocalized(d.name, lang, d.id),
      d.id,
      ...d.variants.flatMap((v) => [v.id, pickLocalized(v.label, lang, v.id)]),
    );
  const branchLabel = (b: OutcomeBranch) =>
    b.label ? pickLocalized(b.label, lang, b.input) : explain.subject(b.input);
  const branchMatches = (b: OutcomeBranch) =>
    (affects === "all" || b.affects.includes(affects)) &&
    matches(
      query,
      branchLabel(b),
      b.input,
      ...b.alternatives.map((a) =>
        a.label ? pickLocalized(a.label, lang, a.value) : a.value,
      ),
    );

  const shownVariants = variantDocs.filter(docMatches);
  const shownFallbacks = fallbackDocs.filter(docMatches);
  const shownBranches = (branches ?? []).filter(branchMatches);
  const sections = [...new Set((branches ?? []).flatMap((b) => b.affects))];
  const filtering = query.trim() !== "" || affects !== "all";
  const reset = () => {
    setQuery("");
    setAffects("all");
  };
  const alternatives = (branches ?? []).flatMap((b) =>
    b.alternatives.filter((a) => a.value !== b.chosen),
  );

  return (
    <div
      className="po-sec"
      data-stale={stale || state.stale ? "true" : undefined}
      data-testid="outcome-branches"
      onKeyDown={onArrowNav}
    >
      <Stats
        testId="outcome-branches-stats"
        items={[
          ...(branches
            ? [
                {
                  id: "inputs",
                  label: t("branches.stats.inputs"),
                  value: branches.length,
                },
                {
                  id: "alternatives",
                  label: t("branches.stats.alternatives"),
                  value: alternatives.length,
                },
                {
                  id: "same",
                  label: t("branches.stats.same"),
                  value: alternatives.filter((a) => a.delta.length === 0)
                    .length,
                },
              ]
            : []),
          {
            id: "variants",
            label: t("branches.stats.variants"),
            value: variantDocs.length,
          },
          {
            id: "fallback",
            label: t("branches.stats.fallback"),
            value: fallbackDocs.length,
          },
        ]}
      />
      <PartStatus state={state} part="branches" />
      <FilterBar
        label={t("sections.branches")}
        query={query}
        onQuery={setQuery}
        testId="outcome-branches-filter"
      >
        {sections.length > 0 && (
          <label className="po-filter-select" htmlFor={affectsId}>
            <span className="po-note">{t("branches.filterAffects")}</span>
            <select
              id={affectsId}
              className="input"
              value={affects}
              data-testid="outcome-branches-affects"
              onChange={(e) => {
                setAffects(e.target.value as "all" | OutcomeSection);
              }}
            >
              <option value="all">{t("branches.filter.all")}</option>
              {sections.map((section) => (
                <option key={section} value={section}>
                  {t(`sections.${section}`)}
                </option>
              ))}
            </select>
          </label>
        )}
      </FilterBar>

      <div className="po-group" data-testid="outcome-branches-variants">
        <GroupTitle id={variantsId} count={shownVariants.length}>
          {t("branches.variantsTitle")}
        </GroupTitle>
        {variantDocs.length === 0 ? (
          <p className="po-note" data-testid="outcome-variants-empty">
            {t("branches.variantsEmpty")}
          </p>
        ) : shownVariants.length === 0 ? (
          <NoResults
            compact
            query={query}
            onReset={reset}
            testId="outcome-variants-noresults"
          />
        ) : (
          <ul className="po-grid" aria-labelledby={variantsId}>
            {shownVariants.map((doc) => (
              <VariantRow
                key={doc.id}
                doc={doc}
                outcome={outcome}
                apply={apply}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="po-group" data-testid="outcome-branches-languages">
        <GroupTitle id={langId} count={shownFallbacks.length}>
          {t("branches.languageTitle")}
        </GroupTitle>
        <p className="po-note" data-testid="outcome-branches-lang">
          {t("branches.languageLead", { lang: projectLang })}
        </p>
        {fallbackDocs.length === 0 ? (
          <p className="po-note" data-testid="outcome-fallback-empty">
            {t("branches.fallbackEmpty")}
          </p>
        ) : (
          <ul className="po-grid" aria-labelledby={langId}>
            {shownFallbacks.map((doc) => (
              <FallbackRow key={doc.id} doc={doc} lang={projectLang} />
            ))}
          </ul>
        )}
      </div>

      <div className="po-group" data-testid="outcome-branches-whatif">
        <GroupTitle id={branchesId} count={shownBranches.length}>
          {t("branches.whatIfTitle")}
        </GroupTitle>
        {state.items === undefined ? (
          state.pending ? (
            <RowsSkeleton testId="outcome-branches-skeleton" />
          ) : null
        ) : branches === null ? (
          <EmptyState
            compact
            title={t("branches.unavailableTitle")}
            description={t("branches.unavailableLead")}
            testId="outcome-branches-unavailable"
          />
        ) : branches.length === 0 ? (
          <EmptyState
            compact
            title={t("branches.emptyTitle")}
            description={t("branches.emptyLead")}
            testId="outcome-branches-empty"
          />
        ) : filtering && shownBranches.length === 0 ? (
          <NoResults
            compact
            query={query}
            onReset={reset}
            testId="outcome-branches-noresults"
          />
        ) : (
          <ul className="po-forms" aria-labelledby={branchesId}>
            {shownBranches.map((branch) => (
              <BranchRow
                key={branch.input}
                branch={branch}
                apply={apply}
                explain={explain}
              />
            ))}
          </ul>
        )}
      </div>

      <WorkspaceBlock outcome={outcome} />
    </div>
  );
};

/**
 * Что будет, если студент выберет иначе: варианты документов и язык редакций (из основного
 * ответа), вводные, которые меняют результат, и что изменится при каждом другом значении (по
 * `include=branches`, только раскрытый раздел), состояние ветки пространства. Сравнения нет:
 * показаны только сводки контракта (счётчики по разделам и отпечатки).
 */
export const BranchesSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown, url } = useOutcomeModel();
  // Раздел, в котором выбран элемент (ссылка), раскрыт: иначе выбранное не видно.
  const collapse = useSectionCollapse(
    "branches",
    url.state.selected?.section !== "branches",
  );
  const state = useOutcomePart("branches", !collapse[0]);
  const branches = state.items ?? null;
  return (
    <SectionShell
      id="branches"
      collapse={collapse}
      title={t("sections.branches")}
      count={
        !shown
          ? null
          : branches
            ? t("sections.count.branches", { count: branches.length })
            : t("sections.notRequested")
      }
      loading={!shown}
    >
      {shown && <BranchesBody outcome={shown} state={state} />}
    </SectionShell>
  );
};
