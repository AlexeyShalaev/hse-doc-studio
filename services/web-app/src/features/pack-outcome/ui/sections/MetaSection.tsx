import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  OutcomeForm,
  OutcomeMetaField,
  PackOutcome,
} from "@entities/pack-studio";
import { Badge, NoResults } from "@shared/ui";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import { summarize } from "../../lib/summary";
import { useOutcomeModel } from "../../model";
import { SectionShell } from "./SectionShell";
import {
  Disclosure,
  FilterBar,
  GroupTitle,
  PickButton,
  PickItem,
  Reason,
  Stats,
} from "./parts";
import { groupBy, matches, onArrowNav, useIsSelected } from "./helpers";
import { useExplain } from "./useExplain";

type RequiredFilter = "all" | "create" | "finalize" | "never";

const RequiredBadge = ({ at }: { at: OutcomeMetaField["required_at"] }) => {
  const { t } = useTranslation("packOutcome");
  return (
    <Badge
      variant={
        at === "create" ? "accent" : at === "finalize" ? "info" : "subtle"
      }
      data-required={at}
    >
      {t(`meta.required.${at}`)}
    </Badge>
  );
};

const MetaCard = ({
  field,
  outcome,
}: {
  field: OutcomeMetaField;
  outcome: PackOutcome;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const label = pickLocalized(field.label, i18n.language, field.id);
  const reasons = field.visible ? [] : explain.reasons(field.why);
  const value =
    field.value === null || field.value === ""
      ? null
      : field.type === "bool"
        ? explain.value(`meta.${field.id}`, field.value)
        : field.value;
  const options = field.options.slice(0, 4);
  return (
    <PickItem
      el={{ section: "meta", id: field.id }}
      muted={!field.visible}
      testId={`outcome-meta-${field.id}`}
      title={label}
      badges={
        <>
          <RequiredBadge at={field.required_at} />
          <Badge>{t(`meta.type.${field.type}`)}</Badge>
        </>
      }
    >
      <span className="po-meta-line">
        <span className="po-mono po-meta-id">{field.id}</span>
        <span className="po-note">{t(`meta.scope.${field.scope}`)}</span>
      </span>
      <span className="po-meta-line">
        <span className="po-note">{t("meta.value")}</span>
        {value === null ? (
          <span className="po-note">{t("meta.noValue")}</span>
        ) : (
          <span className="po-meta-value">{value}</span>
        )}
      </span>
      {options.length > 0 && (
        <span className="po-meta-line">
          <span className="po-note">{t("meta.options")}</span>
          <span className="po-meta-value">
            {options.join(", ")}
            {field.options.length > options.length &&
              ` +${String(field.options.length - options.length)}`}
          </span>
        </span>
      )}
      {!field.visible && (
        <Reason
          prefix={t("meta.hiddenWhy")}
          texts={reasons.length > 0 ? reasons : [t("meta.whyUnknown")]}
        />
      )}
    </PickItem>
  );
};

type OutcomeFormField = OutcomeForm["fields"][number];

const FormFieldRow = ({
  form,
  field,
  outcome,
}: {
  form: OutcomeForm;
  field: OutcomeFormField;
  outcome: PackOutcome;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const label = pickLocalized(field.label, i18n.language, field.id);
  const reasons = field.visible ? [] : explain.reasons(field.why);
  return (
    <PickItem
      el={{ section: "forms", id: `${form.id}/${field.id}` }}
      muted={!field.visible}
      testId={`outcome-field-${form.id}-${field.id}`}
      title={label}
      badges={
        <>
          {field.visible && field.required && (
            <Badge variant="accent">{t("forms.required")}</Badge>
          )}
          <Badge>{field.type}</Badge>
        </>
      }
    >
      {!field.visible && (
        <Reason
          prefix={t("forms.hiddenWhy")}
          texts={reasons.length > 0 ? reasons : [t("meta.whyUnknown")]}
        />
      )}
    </PickItem>
  );
};

const FormCard = ({
  form,
  outcome,
}: {
  form: OutcomeForm;
  outcome: PackOutcome;
}) => {
  const { t, i18n } = useTranslation("packOutcome");
  const explain = useExplain(outcome);
  const selected = useIsSelected({ section: "forms", id: form.id });
  const title = pickLocalized(form.title, i18n.language, form.id);
  const visible = form.fields.filter((f) => f.visible);
  const hidden = form.fields.filter((f) => !f.visible);
  const reasons = form.applies ? [] : explain.reasons(form.why);
  return (
    <li
      className="po-form"
      data-muted={form.applies ? undefined : "true"}
      data-selected={selected ? "true" : undefined}
      data-testid={`outcome-form-${form.id}`}
    >
      <PickButton
        el={{ section: "forms", id: form.id }}
        testId={`outcome-form-${form.id}-pick`}
        title={title}
        badges={
          <>
            <Badge>
              {form.per_author ? t("forms.perAuthor") : t("forms.shared")}
            </Badge>
            {form.required_for_pack && (
              <Badge variant="accent">{t("forms.requiredForPack")}</Badge>
            )}
            {!form.applies && (
              <Badge variant="subtle">{t("forms.notApplies")}</Badge>
            )}
          </>
        }
      >
        {!form.applies && (
          <Reason
            prefix={t("forms.notAppliesWhy")}
            texts={reasons.length > 0 ? reasons : [t("meta.whyUnknown")]}
          />
        )}
        <span className="po-note">
          {t("forms.fieldsOf", {
            visible: visible.length,
            total: form.fields.length,
          })}
        </span>
      </PickButton>
      {form.applies && visible.length > 0 && (
        <ul className="po-fields">
          {visible.map((f) => (
            <FormFieldRow key={f.id} form={form} field={f} outcome={outcome} />
          ))}
        </ul>
      )}
      {form.applies && hidden.length > 0 && (
        <Disclosure
          label={t("forms.hiddenBlock")}
          count={hidden.length}
          testId={`outcome-form-${form.id}-hidden`}
        >
          <ul className="po-fields">
            {hidden.map((f) => (
              <FormFieldRow
                key={f.id}
                form={form}
                field={f}
                outcome={outcome}
              />
            ))}
          </ul>
        </Disclosure>
      )}
    </li>
  );
};

const MetaBody = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const { stale } = useOutcomeModel();
  const [query, setQuery] = useState("");
  const [required, setRequired] = useState<RequiredFilter>("all");
  const requiredId = useId();
  const lang = i18n.language;

  const fields = outcome.meta;
  const forms = outcome.forms;
  const filtering = query.trim() !== "" || required !== "all";

  const shownFields = fields.filter(
    (f) =>
      (required === "all" || f.required_at === required) &&
      matches(query, pickLocalized(f.label, lang, f.id), f.id, f.value),
  );
  const visible = shownFields.filter((f) => f.visible);
  const hidden = shownFields.filter((f) => !f.visible);
  const groups = groupBy(visible, (f) => f.group ?? "");

  const shownForms = forms.filter(
    (f) =>
      matches(query, pickLocalized(f.title, lang, f.id), f.id) ||
      f.fields.some((x) =>
        matches(query, pickLocalized(x.label, lang, x.id), x.id),
      ),
  );
  const formsApply = shownForms.filter((f) => f.applies);
  const formsOff = shownForms.filter((f) => !f.applies);

  const stats = {
    visible: fields.filter((f) => f.visible).length,
    hidden: fields.filter((f) => !f.visible).length,
    create: fields.filter((f) => f.visible && f.required_at === "create")
      .length,
    finalize: fields.filter((f) => f.visible && f.required_at === "finalize")
      .length,
  };

  const nothing =
    visible.length === 0 &&
    hidden.length === 0 &&
    formsApply.length === 0 &&
    formsOff.length === 0;
  const reset = () => {
    setQuery("");
    setRequired("all");
  };

  return (
    <div
      className="po-sec"
      data-stale={stale ? "true" : undefined}
      data-testid="outcome-meta"
      onKeyDown={onArrowNav}
    >
      <Stats
        testId="outcome-meta-stats"
        items={[
          {
            id: "visible",
            label: t("meta.stats.visible"),
            value: stats.visible,
          },
          { id: "hidden", label: t("meta.stats.hidden"), value: stats.hidden },
          { id: "create", label: t("meta.stats.create"), value: stats.create },
          {
            id: "finalize",
            label: t("meta.stats.finalize"),
            value: stats.finalize,
          },
          { id: "forms", label: t("meta.stats.forms"), value: forms.length },
        ]}
      />
      {fields.length + forms.length === 0 ? (
        <p className="po-note" data-testid="outcome-meta-empty">
          {t("meta.empty")}
        </p>
      ) : (
        <>
          <FilterBar
            label={t("sections.meta")}
            query={query}
            onQuery={setQuery}
            testId="outcome-meta-filter"
          >
            <label className="po-filter-select" htmlFor={requiredId}>
              <span className="po-note">{t("meta.filterRequired")}</span>
              <select
                id={requiredId}
                className="input"
                value={required}
                data-testid="outcome-meta-required"
                onChange={(e) => {
                  setRequired(e.target.value as RequiredFilter);
                }}
              >
                <option value="all">{t("meta.required.all")}</option>
                <option value="create">{t("meta.required.create")}</option>
                <option value="finalize">{t("meta.required.finalize")}</option>
                <option value="never">{t("meta.required.never")}</option>
              </select>
            </label>
          </FilterBar>
          {filtering && nothing ? (
            <NoResults
              compact
              query={query}
              onReset={reset}
              testId="outcome-meta-noresults"
            />
          ) : (
            <>
              {groups.map(([group, items]) => (
                <MetaGroup
                  key={group}
                  group={group}
                  items={items}
                  outcome={outcome}
                />
              ))}
              {hidden.length > 0 && (
                <Disclosure
                  label={t("meta.hiddenBlock")}
                  count={hidden.length}
                  forceOpen={filtering}
                  testId="outcome-meta-hidden"
                >
                  <ul className="po-grid">
                    {hidden.map((f) => (
                      <MetaCard key={f.id} field={f} outcome={outcome} />
                    ))}
                  </ul>
                </Disclosure>
              )}
              {(formsApply.length > 0 || formsOff.length > 0) && (
                <div className="po-group" data-testid="outcome-forms">
                  <h4 className="po-group-title">
                    {t("sections.forms")}
                    <span className="po-group-count">
                      {formsApply.length + formsOff.length}
                    </span>
                  </h4>
                  <ul className="po-forms">
                    {formsApply.map((f) => (
                      <FormCard key={f.id} form={f} outcome={outcome} />
                    ))}
                  </ul>
                  {formsOff.length > 0 && (
                    <Disclosure
                      label={t("forms.offBlock")}
                      count={formsOff.length}
                      forceOpen={filtering}
                      testId="outcome-forms-off"
                    >
                      <ul className="po-forms">
                        {formsOff.map((f) => (
                          <FormCard key={f.id} form={f} outcome={outcome} />
                        ))}
                      </ul>
                    </Disclosure>
                  )}
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
};

const MetaGroup = ({
  group,
  items,
  outcome,
}: {
  group: string;
  items: OutcomeMetaField[];
  outcome: PackOutcome;
}) => {
  const { t } = useTranslation("packOutcome");
  const id = useId();
  return (
    <div className="po-group" data-testid={`outcome-meta-group-${group}`}>
      <GroupTitle id={id} count={items.length}>
        {group === ""
          ? t("meta.groups.none")
          : t(`meta.groups.${group}`, { defaultValue: group })}
      </GroupTitle>
      <ul className="po-grid" aria-labelledby={id}>
        {items.map((f) => (
          <MetaCard key={f.id} field={f} outcome={outcome} />
        ))}
      </ul>
    </div>
  );
};

/** Поля проекта и анкеты комбинации: видимость, обязательность, значение примера. */
export const MetaSection = () => {
  const { t } = useTranslation("packOutcome");
  const { shown } = useOutcomeModel();
  const sum = shown ? summarize(shown) : null;
  return (
    <SectionShell
      id="meta"
      title={t("sections.meta")}
      count={
        sum
          ? t("sections.count.meta", {
              visible: sum.metaVisible,
              total: sum.metaTotal,
            })
          : null
      }
      loading={!shown}
    >
      {shown && <MetaBody outcome={shown} />}
    </SectionShell>
  );
};
