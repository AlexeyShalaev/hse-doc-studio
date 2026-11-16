import { useId, useState } from "react";
import {
  Braces,
  Code,
  FileSearch,
  Link2,
  LayoutList,
  Regex,
  ScrollText,
  Settings2,
  Type,
  type LucideIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeCheckRule, PackOutcome } from "@entities/pack-studio";
import { Badge, EmptyState, NoResults } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { useOutcomePart, type PartState } from "../../lib/part";
import { useOutcomeModel } from "../../model";
import { Notice } from "../Notice";
import { PartStatus, RowsSkeleton } from "./PartStatus";
import { useSectionCollapse } from "../../lib/sectionCollapse";
import { SectionShell } from "./SectionShell";
import {
  Disclosure,
  FilterBar,
  GroupTitle,
  PickItem,
  Reason,
  Stats,
} from "./parts";
import { groupBy, matches, onArrowNav } from "./helpers";

type Severity = OutcomeCheckRule["severity"];
type SeverityFilter = "all" | Severity;

const ENGINE_ICONS: Record<string, LucideIcon> = {
  regex: Regex,
  python: Code,
  structural: LayoutList,
  log_parse: ScrollText,
  reference_check: Link2,
  typography: Type,
  pdf_text: FileSearch,
  schema: Braces,
};

const SEVERITY_VARIANT = {
  err: "error",
  warn: "warning",
  info: "info",
} as const;

const OFF_REASONS = [
  "disabled",
  "category_disabled",
  "no_active_document",
] as const;

/** Слой правила: файл правил в начале идентификатора (`gost-7.32-2017/page-margins`). */
const layerOf = (rule: OutcomeCheckRule): string => {
  const cut = rule.id.indexOf("/");
  return cut > 0 ? rule.id.slice(0, cut) : "";
};

const EngineBadge = ({ rule }: { rule: OutcomeCheckRule }) => {
  const { t } = useTranslation("packOutcome");
  const Icon = ENGINE_ICONS[rule.engine] ?? Settings2;
  return (
    <Badge
      variant="subtle"
      data-testid={`outcome-check-${rule.id}-engine`}
      data-engine={rule.engine}
      title={rule.engine === "python" ? t("checks.pythonHint") : undefined}
    >
      <Icon size="0.75rem" aria-hidden="true" />
      <span className="sr-only">{t("checks.engine")}</span>
      {rule.engine}
    </Badge>
  );
};

const CheckItem = ({
  rule,
  docNames,
}: {
  rule: OutcomeCheckRule;
  docNames: (ids: readonly string[]) => string;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const title = pickLocalized(rule.title, i18n.language, rule.id);
  const off = rule.off_reason;
  return (
    <PickItem
      el={{ section: "checks", id: rule.id }}
      muted={!rule.enabled}
      testId={`outcome-check-${rule.id}`}
      title={title}
      badges={
        <>
          <Badge variant={SEVERITY_VARIANT[rule.severity]}>
            {t(`checks.severity.${rule.severity}`)}
          </Badge>
          <EngineBadge rule={rule} />
        </>
      }
    >
      <span className="po-meta-line">
        <span className="po-mono po-meta-id">{rule.id}</span>
        {rule.category && <span className="po-note">{rule.category}</span>}
      </span>
      {off && (
        <Reason
          prefix={t("checks.off.prefix")}
          texts={[
            t(`checks.off.${off}`, {
              category: rule.category ?? "",
              documents: docNames(rule.applies_to),
            }),
          ]}
        />
      )}
    </PickItem>
  );
};

const CheckList = ({
  labelId,
  rules,
  docNames,
}: {
  labelId: string;
  rules: OutcomeCheckRule[];
  docNames: (ids: readonly string[]) => string;
}) => (
  <ul className="po-grid" aria-labelledby={labelId}>
    {rules.map((rule) => (
      <CheckItem key={rule.id} rule={rule} docNames={docNames} />
    ))}
  </ul>
);

const DocumentChecks = ({
  doc,
  rules,
  title,
}: {
  doc: string;
  rules: OutcomeCheckRule[];
  title: string;
}) => {
  const { t } = useTranslation("packOutcome");
  const id = useId();
  const layers = groupBy(rules, layerOf);
  return (
    <div className="po-group" data-testid={`outcome-checks-doc-${doc}`}>
      <GroupTitle id={id} count={rules.length}>
        {title}
      </GroupTitle>
      {layers.map(([layer, items], at) => (
        <div
          key={layer}
          className="po-layer"
          data-testid={`outcome-checks-layer-${doc}-${layer}`}
        >
          <p className="po-layer-title" id={`${id}-${String(at)}`}>
            <span className="po-note">{t("checks.layer")}</span>
            <span className="po-mono">{layer || t("checks.layerNone")}</span>
            <span className="po-group-count">{items.length}</span>
          </p>
          <ul className="po-grid" aria-labelledby={`${id}-${String(at)}`}>
            {items.map((rule) => (
              <CheckItem key={rule.id} rule={rule} docNames={() => ""} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
};

const ChecksBody = ({
  outcome,
  rules,
  state,
}: {
  outcome: PackOutcome;
  rules: OutcomeCheckRule[];
  state: PartState<"checks">;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { stale } = useOutcomeModel();
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [engine, setEngine] = useState("all");
  const severityId = useId();
  const engineId = useId();
  const offId = useId();
  const lang = i18n.language;

  const docName = (id: string): string => {
    const doc = outcome.documents.find((d) => d.id === id);
    return doc ? pickLocalized(doc.name, lang, id) : id;
  };
  const docNames = (ids: readonly string[]) => ids.map(docName).join(", ");

  const engines = [...new Set(rules.map((r) => r.engine))].sort();
  const enabled = rules.filter((r) => r.enabled);
  const off = rules.filter((r) => !r.enabled);
  const python = enabled.filter((r) => r.engine === "python").length;
  const scope = outcome.out_of_scope.filter(
    (item) => item === "python_checks" || item === "signature_anchors",
  );

  const shows = (rule: OutcomeCheckRule) =>
    (severity === "all" || rule.severity === severity) &&
    (engine === "all" || rule.engine === engine) &&
    matches(
      query,
      pickLocalized(rule.title, lang, rule.id),
      rule.id,
      rule.category,
      docNames(rule.applies_to),
    );
  const shownOn = enabled.filter(shows);
  const shownOff = off.filter(shows);
  const filtering =
    query.trim() !== "" || severity !== "all" || engine !== "all";
  const reset = () => {
    setQuery("");
    setSeverity("all");
    setEngine("all");
  };

  // Правило с несколькими документами стоит в группе каждого; без документа: общая группа.
  const byDoc = new Map<string, OutcomeCheckRule[]>();
  for (const rule of shownOn) {
    const docs = rule.applies_to.length > 0 ? rule.applies_to : [""];
    for (const doc of docs) byDoc.set(doc, [...(byDoc.get(doc) ?? []), rule]);
  }
  const order = [
    ...outcome.documents.map((d) => d.id),
    ...[...byDoc.keys()].filter(
      (id) => id !== "" && !outcome.documents.some((d) => d.id === id),
    ),
    "",
  ].filter((id) => byDoc.has(id));

  return (
    <div
      className="po-sec"
      data-stale={stale || state.stale ? "true" : undefined}
      data-testid="outcome-checks"
      onKeyDown={onArrowNav}
    >
      <Notice
        tone="info"
        title={t("checks.scopeTitle")}
        testId="outcome-checks-scope"
      >
        {[
          t("checks.scopeLead"),
          ...(scope.length > 0
            ? [
                t("checks.scopeMissing", {
                  items: scope
                    .map((item) => t(`footer.scope.${item}`))
                    .join(", "),
                }),
              ]
            : []),
        ].join(" ")}
      </Notice>
      <PartStatus state={state} part="checks" />
      <Stats
        testId="outcome-checks-stats"
        items={[
          {
            id: "enabled",
            label: t("checks.stats.enabled"),
            value: enabled.length,
          },
          { id: "off", label: t("checks.stats.off"), value: off.length },
          { id: "python", label: t("checks.stats.python"), value: python },
        ]}
      />
      <FilterBar
        label={t("sections.checks")}
        query={query}
        onQuery={setQuery}
        testId="outcome-checks-filter"
      >
        <label className="po-filter-select" htmlFor={severityId}>
          <span className="po-note">{t("checks.filterSeverity")}</span>
          <select
            id={severityId}
            className="input"
            value={severity}
            data-testid="outcome-checks-severity"
            onChange={(e) => {
              setSeverity(e.target.value as SeverityFilter);
            }}
          >
            <option value="all">{t("checks.filter.all")}</option>
            {(["err", "warn", "info"] as const).map((item) => (
              <option key={item} value={item}>
                {t(`checks.severity.${item}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="po-filter-select" htmlFor={engineId}>
          <span className="po-note">{t("checks.filterEngine")}</span>
          <select
            id={engineId}
            className="input"
            value={engine}
            data-testid="outcome-checks-engine"
            onChange={(e) => {
              setEngine(e.target.value);
            }}
          >
            <option value="all">{t("checks.filter.all")}</option>
            {engines.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
      </FilterBar>

      {filtering && shownOn.length === 0 && shownOff.length === 0 ? (
        <NoResults
          compact
          query={query}
          onReset={reset}
          testId="outcome-checks-noresults"
        />
      ) : (
        <>
          {enabled.length === 0 ? (
            <p className="po-note" data-testid="outcome-checks-none">
              {t("checks.noneApplicable")}
            </p>
          ) : (
            order.map((doc) => (
              <DocumentChecks
                key={doc}
                doc={doc}
                rules={byDoc.get(doc) ?? []}
                title={doc === "" ? t("checks.noDocument") : docName(doc)}
              />
            ))
          )}
          {shownOff.length > 0 && (
            <Disclosure
              label={t("checks.offBlock")}
              count={shownOff.length}
              forceOpen={filtering}
              testId="outcome-checks-off"
            >
              {OFF_REASONS.map((reason) => {
                const items = shownOff.filter((r) => r.off_reason === reason);
                return items.length === 0 ? null : (
                  <div
                    key={reason}
                    className="po-group"
                    data-testid={`outcome-checks-off-${reason}`}
                  >
                    <GroupTitle id={`${offId}-${reason}`} count={items.length}>
                      {t(`checks.offGroup.${reason}`)}
                    </GroupTitle>
                    <CheckList
                      labelId={`${offId}-${reason}`}
                      rules={items}
                      docNames={docNames}
                    />
                  </div>
                );
              })}
            </Disclosure>
          )}
        </>
      )}
    </div>
  );
};

const ChecksContent = ({
  outcome,
  state,
}: {
  outcome: PackOutcome;
  state: PartState<"checks">;
}) => {
  const { t } = useTranslation("packOutcome");
  const rules = state.items;
  if (rules === undefined) {
    if (state.failed) return <PartStatus state={state} part="checks" />;
    // Раздел свёрнут и ничего не просил: нечего рисовать.
    return state.pending ? (
      <>
        <PartStatus state={state} part="checks" />
        <RowsSkeleton testId="outcome-checks-skeleton" />
      </>
    ) : null;
  }
  if (rules === null) {
    return (
      <EmptyState
        compact
        title={t("checks.unavailableTitle")}
        description={t("checks.unavailableLead")}
        testId="outcome-checks-unavailable"
      />
    );
  }
  if (rules.length === 0) {
    return (
      <EmptyState
        compact
        title={t("checks.emptyTitle")}
        description={t("checks.emptyLead")}
        testId="outcome-checks-empty"
      />
    );
  }
  return <ChecksBody outcome={outcome} rules={rules} state={state} />;
};

/**
 * Какие правила проверок применимы к комплекту при этой комбинации: по документам и слоям, с
 * движком и серьёзностью; выключенные в свёрнутом блоке с причиной. Результат прогона сюда не
 * входит, только применимость. Раздел запрашивает правила (`include=checks`), лишь когда раскрыт.
 */
export const ChecksSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown, url } = useOutcomeModel();
  // Раздел, в котором выбран элемент (ссылка), раскрыт: иначе выбранное не видно.
  const collapse = useSectionCollapse(
    "checks",
    url.state.selected?.section !== "checks",
  );
  const state = useOutcomePart("checks", !collapse[0]);
  const rules = state.items ?? null;
  return (
    <SectionShell
      id="checks"
      collapse={collapse}
      title={t("sections.checks")}
      count={
        !shown
          ? null
          : rules
            ? t("sections.count.checks", {
                enabled: rules.filter((r) => r.enabled).length,
                total: rules.length,
              })
            : t("sections.notRequested")
      }
      loading={!shown}
    >
      {shown && <ChecksContent outcome={shown} state={state} />}
    </SectionShell>
  );
};
