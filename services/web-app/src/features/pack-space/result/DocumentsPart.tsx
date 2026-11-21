import { useId, useState } from "react";
import { Eye, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type {
  OutcomeDocument,
  OutcomeInput,
  PackOutcome,
} from "@entities/pack-studio";
import { NoResults } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { useSituation } from "../context/useSituation";
import { useSpaceNav } from "../context/useSpaceNav";
import {
  FILTER_THRESHOLD,
  fileNames,
  groupDocuments,
  isIncluded,
  matchesQuery,
  sections,
} from "./model";
import type { Reasoner } from "./reasons";
import { GroupLabel, Missing, PickRow, type MissingRow } from "./rows";

type Scope = "all" | "personal" | "shared";

/** Варианты документа: выбор условием `variant.<документ>`, если оно есть и выбирать есть из чего. */
const variantControl = (
  doc: OutcomeDocument,
  inputs: readonly OutcomeInput[] | undefined,
): OutcomeInput | null =>
  doc.variants.filter((variant) => variant.available).length >= 2
    ? (inputs?.find((input) => input.id === `variant.${doc.id}`) ?? null)
    : null;

const VariantSelect = ({
  doc,
  control,
  name,
}: {
  doc: OutcomeDocument;
  control: OutcomeInput;
  name: string;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const situation = useSituation();
  const chosen = doc.variants.find((variant) => variant.chosen);
  return (
    <select
      className="input sp-variant"
      aria-label={t("result.docs.variantFor", { name })}
      value={chosen?.id ?? ""}
      onChange={(event) => {
        situation.setInput(control.id, event.target.value);
      }}
      data-testid={`sp-doc-${doc.id}-variant`}
    >
      {doc.variants
        .filter((variant) => variant.available)
        .map((variant) => (
          <option key={variant.id} value={variant.id}>
            {pickLocalized(variant.label, i18n.language, variant.id)}
          </option>
        ))}
    </select>
  );
};

const DocRow = ({
  doc,
  outcome,
  inputs,
}: {
  doc: OutcomeDocument;
  outcome: PackOutcome;
  inputs: readonly OutcomeInput[] | undefined;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const nav = useSpaceNav();
  const name = pickLocalized(doc.name, i18n.language, doc.id);
  const files = fileNames(doc);
  const projectLang = outcome.inputs.lang ?? "";
  const control = variantControl(doc, inputs);
  const chosen = doc.variants.find((variant) => variant.chosen);
  const subs = [
    files.length === 0
      ? t("result.docs.noFile")
      : files.length === 1
        ? (files[0] ?? "")
        : `${files[0] ?? ""} ${t("result.docs.moreFiles", { count: files.length - 1 })}`,
    doc.languages.join(", "),
    // Вариантов несколько, но выбрать нечем: показываем, какой выбран.
    chosen && doc.variants.length > 1 && !control
      ? pickLocalized(chosen.label, i18n.language, chosen.id)
      : "",
  ].filter((part) => part !== "");
  return (
    <PickRow
      sel={sections.document(doc.id)}
      icon={<FileText size="1rem" />}
      title={name}
      badges={
        <>
          {!doc.required && (
            <span className="chip subtle sp-badge">
              {t("result.docs.optional")}
            </span>
          )}
          {doc.lang_state === "fallback" && (
            <span className="chip sp-badge" data-tone="warn">
              {t("result.docs.noFallback", { lang: projectLang })}
            </span>
          )}
        </>
      }
      sub={subs.join(" · ")}
      trailing={
        <>
          {control ? (
            <VariantSelect doc={doc} control={control} name={name} />
          ) : null}
          <button
            type="button"
            className="btn sm ghost sp-pdf"
            aria-label={t("result.docs.pdfFor", { name })}
            title={t("result.docs.pdfFor", { name })}
            data-testid={`sp-doc-${doc.id}-pdf`}
            onClick={() => {
              // Предпросмотр живёт в подробностях (S7, S9): выбираем документ и просим его открыть.
              nav.go({
                sel: sections.document(doc.id),
                extra: { preview: "1" },
              });
            }}
          >
            <Eye size="0.875rem" aria-hidden="true" />
            {t("result.docs.pdf")}
          </button>
        </>
      }
      testId={`sp-doc-${doc.id}`}
    />
  );
};

/** Документы комплекта по группам и «Не вошло в комплект» с причинами. */
export const DocumentsBody = ({
  outcome,
  inputs,
  reasoner,
}: {
  outcome: PackOutcome;
  inputs: readonly OutcomeInput[] | undefined;
  reasoner: Reasoner;
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<Scope>("all");
  const scopeId = useId();
  const lang = i18n.language;
  const docs = outcome.documents;
  const filterable = docs.length > FILTER_THRESHOLD;
  const filtering = filterable && (query.trim() !== "" || scope !== "all");
  const visible = docs.filter(
    (doc) =>
      (!filtering || scope === "all" || doc.scope === scope) &&
      (!filtering ||
        matchesQuery(
          query,
          pickLocalized(doc.name, lang, doc.id),
          ...fileNames(doc),
        )),
  );
  const included = visible.filter(isIncluded);
  const left = visible.filter((doc) => !isIncluded(doc));
  const groups = groupDocuments(included);
  const groupName = (id: string): string =>
    t(id === "" ? "result.docs.groups.none" : `result.docs.groups.${id}`, {
      defaultValue: t("result.docs.groups.none"),
    });

  const missing: MissingRow[] = left.map((doc) => {
    const reason = reasoner.why(doc.why);
    return {
      key: doc.id,
      sel: sections.document(doc.id),
      icon: <FileText size="1rem" />,
      title: pickLocalized(doc.name, lang, doc.id),
      reason,
      fallback: t(
        doc.state === "inactive"
          ? "result.missing.unknownDoc"
          : "result.missing.unknownAbsent",
      ),
      testId: `sp-doc-missing-${doc.id}`,
    };
  });

  return (
    <div className="sp-documents" data-testid="sp-documents">
      {filterable ? (
        <div
          className="sp-filter"
          role="search"
          aria-label={t("result.docs.searchLabel")}
        >
          <input
            type="search"
            className="input sp-filter-search"
            placeholder={t("result.docs.search")}
            aria-label={t("result.docs.searchLabel")}
            value={query}
            data-testid="sp-docs-search"
            onChange={(event) => {
              setQuery(event.target.value);
            }}
          />
          <select
            id={scopeId}
            className="input sp-filter-scope"
            aria-label={t("result.docs.scopeLabel")}
            value={scope}
            data-testid="sp-docs-scope"
            onChange={(event) => {
              setScope(event.target.value as Scope);
            }}
          >
            <option value="all">{t("result.docs.scope.all")}</option>
            <option value="personal">{t("result.docs.scope.personal")}</option>
            <option value="shared">{t("result.docs.scope.shared")}</option>
          </select>
        </div>
      ) : null}
      {filtering && included.length === 0 && left.length === 0 ? (
        <NoResults
          compact
          query={query}
          onReset={() => {
            setQuery("");
            setScope("all");
          }}
          testId="sp-docs-noresults"
        />
      ) : included.length === 0 ? (
        <p className="sp-hint" data-testid="sp-docs-none">
          {t("result.docs.empty")}
        </p>
      ) : (
        groups.map((group) => (
          <DocGroup
            key={group.id}
            title={groupName(group.id)}
            showTitle={groups.length > 1}
            docs={group.docs}
            outcome={outcome}
            inputs={inputs}
          />
        ))
      )}
      <Missing
        title={t("result.missing.title")}
        rows={missing}
        open={filtering}
        testId="sp-docs-missing"
      />
    </div>
  );
};

const DocGroup = ({
  title,
  showTitle,
  docs,
  outcome,
  inputs,
}: {
  title: string;
  showTitle: boolean;
  docs: OutcomeDocument[];
  outcome: PackOutcome;
  inputs: readonly OutcomeInput[] | undefined;
}) => {
  const id = useId();
  return (
    <div className="sp-group-block">
      {showTitle ? (
        <GroupLabel id={id} count={docs.length}>
          {title}
        </GroupLabel>
      ) : null}
      <ul className="sp-rows" aria-labelledby={showTitle ? id : undefined}>
        {docs.map((doc) => (
          <DocRow key={doc.id} doc={doc} outcome={outcome} inputs={inputs} />
        ))}
      </ul>
    </div>
  );
};
