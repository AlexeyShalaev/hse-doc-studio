import { useId, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { OutcomeDocument, PackOutcome } from "@entities/pack-studio";
import { Badge, NoResults } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { PaleSlot } from "./PaleSlot";
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
import { useExplain } from "./useExplain";

type ScopeFilter = "all" | "personal" | "shared";

const DocumentCard = ({
  doc,
  outcome,
}: {
  doc: OutcomeDocument;
  outcome: PackOutcome;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const lang = i18n.language;
  const name = pickLocalized(doc.name, lang, doc.id);
  const projectLang = outcome.inputs.lang ?? "";
  const reasons = doc.state === "active" ? [] : explain.reasons(doc.why);
  const personal = doc.instances.filter((i) => i.owner !== null);
  const showVariants = doc.variants.length > 0 && doc.state !== "absent";
  const stateBadge =
    doc.state === "active" ? (
      <Badge variant="success">{t("documents.state.active")}</Badge>
    ) : doc.state === "inactive" ? (
      <Badge variant="warning">{t("documents.state.inactive")}</Badge>
    ) : (
      <Badge variant="subtle">{t("documents.state.absent")}</Badge>
    );

  const el = { section: "documents", id: doc.id } as const;
  const badges = (
    <>
      {stateBadge}
      <Badge>{t(`documents.scope.${doc.scope}`)}</Badge>
      {!doc.required && (
        <Badge variant="subtle">{t("documents.optional")}</Badge>
      )}
    </>
  );
  const testId = `outcome-doc-${doc.id}`;
  // Документ, которого нет в комплекте, это бледный слот: причина и «Добавить во вводных».
  const card = (children: ReactNode) =>
    doc.state === "active" ? (
      <PickItem el={el} testId={testId} title={name} badges={badges}>
        {children}
      </PickItem>
    ) : (
      <PaleSlot el={el} name={name} testId={testId} badges={badges}>
        {children}
      </PaleSlot>
    );

  return card(
    <>
      {doc.state !== "active" && (
        <Reason
          prefix={t(`documents.why.${doc.state}`)}
          texts={reasons.length > 0 ? reasons : [t("documents.whyUnknown")]}
        />
      )}
      {doc.instances.length > 0 && (
        <span className="po-files">
          {doc.instances.map((inst) => (
            <span key={inst.id} className="po-file">
              {inst.owner_name && (
                <span className="po-file-owner">{inst.owner_name}</span>
              )}
              <span className="po-mono po-file-name">
                {inst.file_name ?? t("documents.noFileName")}
              </span>
            </span>
          ))}
          {personal.length > 1 && (
            <span className="po-note">
              {t("documents.copies", { count: personal.length })}
            </span>
          )}
        </span>
      )}
      {showVariants && (
        <span className="po-variants">
          <span className="po-note">{t("documents.variant")}</span>
          {doc.variants.map((variant) => {
            const label = pickLocalized(variant.label, lang, variant.id);
            return (
              <Badge
                key={variant.id}
                variant={variant.chosen ? "accent" : "subtle"}
                data-testid={`outcome-doc-${doc.id}-variant-${variant.id}`}
                data-available={variant.available ? "true" : "false"}
                title={
                  variant.available
                    ? undefined
                    : t("documents.variantOnly", {
                        langs: variant.langs.join(", "),
                      })
                }
              >
                {label}
                {!variant.available && (
                  <span className="po-variant-off">
                    {variant.langs.length > 0
                      ? t("documents.variantOnly", {
                          langs: variant.langs.join(", "),
                        })
                      : t("documents.variantOff")}
                  </span>
                )}
              </Badge>
            );
          })}
        </span>
      )}
      {doc.state !== "absent" && (
        <span className="po-langs">
          <span className="po-note">{t("documents.languages")}</span>
          <span className="po-mono">{doc.languages.join(", ")}</span>
          {doc.lang_state === "fallback" && (
            <Badge
              variant="warning"
              data-testid={`outcome-doc-${doc.id}-fallback`}
            >
              {t("documents.fallback", { lang: projectLang })}
            </Badge>
          )}
        </span>
      )}
    </>,
  );
};

const DocumentsBody = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { stale } = useOutcomeModel();
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<ScopeFilter>("all");
  const scopeId = useId();
  const lang = i18n.language;

  const docs = outcome.documents;
  const stats = {
    active: docs.filter((d) => d.state === "active").length,
    inactive: docs.filter((d) => d.state === "inactive").length,
    absent: docs.filter((d) => d.state === "absent").length,
    shared: docs.filter((d) => d.state !== "absent" && d.scope === "shared")
      .length,
    personal: docs.filter((d) => d.state !== "absent" && d.scope === "personal")
      .length,
  };

  const filtered = docs.filter(
    (d) =>
      (scope === "all" || d.scope === scope) &&
      matches(
        query,
        pickLocalized(d.name, lang, d.id),
        d.id,
        ...d.instances.map((i) => i.file_name),
      ),
  );
  const present = filtered.filter((d) => d.state !== "absent");
  const absent = filtered.filter((d) => d.state === "absent");
  const groups = groupBy(present, (d) => d.group ?? "");

  const filtering = query.trim() !== "" || scope !== "all";
  const reset = () => {
    setQuery("");
    setScope("all");
  };

  return (
    <div
      className="po-sec"
      data-stale={stale ? "true" : undefined}
      data-testid="outcome-documents"
      onKeyDown={onArrowNav}
    >
      <Stats
        testId="outcome-documents-stats"
        items={[
          {
            id: "active",
            label: t("documents.stats.active"),
            value: stats.active,
          },
          {
            id: "inactive",
            label: t("documents.stats.inactive"),
            value: stats.inactive,
          },
          {
            id: "absent",
            label: t("documents.stats.absent"),
            value: stats.absent,
          },
          {
            id: "shared",
            label: t("documents.stats.shared"),
            value: stats.shared,
          },
          {
            id: "personal",
            label: t("documents.stats.personal"),
            value: stats.personal,
          },
        ]}
      />
      <FilterBar
        label={t("sections.documents")}
        query={query}
        onQuery={setQuery}
        testId="outcome-documents-filter"
      >
        <label className="po-filter-select" htmlFor={scopeId}>
          <span className="po-note">{t("documents.filterScope")}</span>
          <select
            id={scopeId}
            className="input"
            value={scope}
            data-testid="outcome-documents-scope"
            onChange={(e) => {
              setScope(e.target.value as ScopeFilter);
            }}
          >
            <option value="all">{t("documents.filter.all")}</option>
            <option value="personal">{t("documents.filter.personal")}</option>
            <option value="shared">{t("documents.filter.shared")}</option>
          </select>
        </label>
      </FilterBar>

      {filtering && present.length === 0 && absent.length === 0 ? (
        <NoResults
          compact
          query={query}
          onReset={reset}
          testId="outcome-documents-noresults"
        />
      ) : (
        <>
          {groups.map(([group, items]) => (
            <GroupedDocs
              key={group}
              group={group}
              items={items}
              outcome={outcome}
            />
          ))}
          {absent.length > 0 && (
            <Disclosure
              label={t("documents.absentBlock")}
              count={absent.length}
              forceOpen={filtering}
              testId="outcome-documents-absent"
            >
              <ul
                className="po-grid"
                data-testid="outcome-documents-absent-list"
              >
                {absent.map((d) => (
                  <DocumentCard key={d.id} doc={d} outcome={outcome} />
                ))}
              </ul>
            </Disclosure>
          )}
        </>
      )}
    </div>
  );
};

const GroupedDocs = ({
  group,
  items,
  outcome,
}: {
  group: string;
  items: OutcomeDocument[];
  outcome: PackOutcome;
}) => {
  const { t } = useTranslation("packOutcome");
  const id = useId();
  return (
    <div className="po-group" data-testid={`outcome-documents-group-${group}`}>
      <GroupTitle id={id} count={items.length}>
        {group === ""
          ? t("documents.groups.none")
          : t(`documents.groups.${group}`, { defaultValue: group })}
      </GroupTitle>
      <ul className="po-grid" aria-labelledby={id}>
        {items.map((d) => (
          <DocumentCard key={d.id} doc={d} outcome={outcome} />
        ))}
      </ul>
    </div>
  );
};

/** Документы комбинации: карточки по группам, итоговые имена файлов, варианты и язык. */
export const DocumentsSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="documents"
      title={t("sections.documents")}
      count={
        sum
          ? t("sections.count.documents", {
              active: sum.documentsActive,
              total: sum.documentsTotal,
            })
          : null
      }
      loading={!shown}
    >
      {shown && <DocumentsBody outcome={shown} />}
    </SectionShell>
  );
};
