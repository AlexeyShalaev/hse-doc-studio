import { useId } from "react";
import {
  CalendarDays,
  ClipboardList,
  FileText,
  PenLine,
  TextCursorInput,
  User,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PackOutcome } from "@entities/pack-studio";
import { pickLocalized } from "@shared/lib/i18n/pickLocalized";
import {
  groupFields,
  personaLabel,
  routeSteps,
  routeText,
  sections,
  shortName,
} from "./model";
import type { Reasoner } from "./reasons";
import { GroupLabel, Missing, PickRow, type MissingRow } from "./rows";

type Props = { outcome: PackOutcome; reasoner: Reasoner };

const Hint = ({ children, testId }: { children: string; testId: string }) => (
  <p className="sp-hint" data-testid={testId}>
    {children}
  </p>
);

/** Данные проекта: поля по группам, анкеты и то, что скрыто при этих условиях. */
export const DataBody = ({ outcome, reasoner }: Props) => {
  const { t, i18n } = useTranslation("packSpace");
  const lang = i18n.language;
  const shown = outcome.meta.filter((field) => field.visible);
  const forms = outcome.forms.filter((form) => form.applies);
  const groups = groupFields(shown);
  const formsId = useId();
  const groupName = (id: string): string =>
    t(id === "" ? "result.data.groups.none" : `result.data.groups.${id}`, {
      defaultValue: t("result.data.groups.none"),
    });

  const missing: MissingRow[] = [
    ...outcome.meta
      .filter((field) => !field.visible)
      .map((field) => ({
        key: `meta:${field.id}`,
        sel: sections.field(field.id),
        icon: <TextCursorInput size="1rem" />,
        title: pickLocalized(field.label, lang, field.id),
        reason: reasoner.why(field.why),
        fallback: t("result.missing.unknownHidden"),
        testId: `sp-field-missing-${field.id}`,
      })),
    ...outcome.forms
      .filter((form) => !form.applies)
      .map((form) => ({
        key: `form:${form.id}`,
        sel: sections.form(form.id),
        icon: <ClipboardList size="1rem" />,
        title: pickLocalized(form.title, lang, form.id),
        reason: reasoner.why(form.why),
        fallback: t("result.missing.unknownForm"),
        testId: `sp-form-missing-${form.id}`,
      })),
  ];

  return (
    <div className="sp-data" data-testid="sp-data">
      {shown.length === 0 && forms.length === 0 ? (
        <Hint testId="sp-data-none">{t("result.data.empty")}</Hint>
      ) : null}
      {groups.map((group) => (
        <DataGroup
          key={group.id}
          title={groupName(group.id)}
          showTitle={groups.length > 1}
          fields={group.fields}
        />
      ))}
      {forms.length > 0 ? (
        <div className="sp-group-block">
          <GroupLabel id={formsId} count={forms.length}>
            {t("result.data.forms")}
          </GroupLabel>
          <ul className="sp-rows" aria-labelledby={formsId}>
            {forms.map((form) => (
              <PickRow
                key={form.id}
                sel={sections.form(form.id)}
                icon={<ClipboardList size="1rem" />}
                title={pickLocalized(form.title, lang, form.id)}
                badges={
                  <span className="chip subtle sp-badge">
                    {t(
                      form.per_author
                        ? "result.data.perAuthor"
                        : "result.data.common",
                    )}
                  </span>
                }
                sub={t("result.data.fieldsOf", {
                  count: form.fields.filter((field) => field.visible).length,
                })}
                testId={`sp-form-${form.id}`}
              />
            ))}
          </ul>
        </div>
      ) : null}
      <Missing
        title={t("result.missing.titleData")}
        rows={missing}
        testId="sp-data-missing"
      />
    </div>
  );
};

const DataGroup = ({
  title,
  showTitle,
  fields,
}: {
  title: string;
  showTitle: boolean;
  fields: PackOutcome["meta"];
}) => {
  const { t, i18n } = useTranslation("packSpace");
  const id = useId();
  return (
    <div className="sp-group-block">
      {showTitle ? (
        <GroupLabel id={id} count={fields.length}>
          {title}
        </GroupLabel>
      ) : null}
      <ul className="sp-rows" aria-labelledby={showTitle ? id : undefined}>
        {fields.map((field) => (
          <PickRow
            key={field.id}
            sel={sections.field(field.id)}
            icon={<TextCursorInput size="1rem" />}
            title={pickLocalized(field.label, i18n.language, field.id)}
            badges={
              <>
                {field.required_at === "create" ? (
                  <span className="chip accent sp-badge">
                    {t("result.data.atCreate")}
                  </span>
                ) : field.required_at === "finalize" ? (
                  <span className="chip subtle sp-badge">
                    {t("result.data.atFinish")}
                  </span>
                ) : null}
                {field.scope === "author" ? (
                  <span className="chip subtle sp-badge">
                    {t("result.data.perAuthor")}
                  </span>
                ) : null}
              </>
            }
            testId={`sp-field-${field.id}`}
          />
        ))}
      </ul>
    </div>
  );
};

/** Участники: кто будет в проекте; тех, кого нет при этих условиях, показываем с причиной. */
export const PeopleBody = ({ outcome, reasoner }: Props) => {
  const { t } = useTranslation("packSpace");
  const present = outcome.participants.filter((person) => person.present);
  const absent = outcome.participants.filter((person) => !person.present);
  const missing: MissingRow[] = absent.map((person) => {
    const fromTrace = reasoner.why(person.why);
    const value = outcome.inputs[person.role];
    const turn = reasoner.turnOn(person.role);
    const reason = fromTrace ?? {
      text:
        value === undefined
          ? t("result.missing.personAbsentPlain")
          : t("result.missing.personAbsent", {
              subject: reasoner.subject(person.role),
              value: reasoner.value(person.role, value),
            }),
      action: turn,
    };
    return {
      key: person.persona,
      sel: sections.person(person.persona),
      icon: <User size="1rem" />,
      title: personaLabel(t, person.persona),
      reason,
      fallback: t("result.missing.personAbsentPlain"),
      testId: `sp-person-missing-${person.persona}`,
    };
  });
  return (
    <div className="sp-people" data-testid="sp-people">
      {present.length === 0 ? (
        <Hint testId="sp-people-none">{t("result.people.empty")}</Hint>
      ) : (
        <ul className="sp-rows">
          {present.map((person) => (
            <PickRow
              key={person.persona}
              sel={sections.person(person.persona)}
              icon={<User size="1rem" />}
              title={personaLabel(t, person.persona)}
              badges={
                person.org ? (
                  <span className="chip subtle sp-badge">
                    {t(`result.people.org.${person.org}`)}
                  </span>
                ) : null
              }
              sub={person.name.trim() || t("result.people.noName")}
              testId={`sp-person-${person.persona}`}
            />
          ))}
        </ul>
      )}
      <Missing
        title={t("result.missing.titlePeople")}
        rows={missing}
        testId="sp-people-missing"
      />
    </div>
  );
};

/** Сроки и сдача: точки, что в них сдают, и что при этих условиях не сдаётся. */
export const DeadlinesBody = ({ outcome, reasoner }: Props) => {
  const { t, i18n } = useTranslation("packSpace");
  const lang = i18n.language;
  const docName = (id: string): string => {
    const doc = outcome.documents.find((item) => item.id === id);
    return doc ? pickLocalized(doc.name, lang, doc.id) : id;
  };
  const missing: MissingRow[] = outcome.points.flatMap((point) => {
    const pointName = shortName(pickLocalized(point.name, lang, point.id));
    return point.items
      .filter((item) => !item.active)
      .map((item) => ({
        key: `${point.id}/${item.doc_id}`,
        sel: sections.item(point.id, item.doc_id),
        icon: <FileText size="1rem" />,
        title: `${pointName}: ${docName(item.doc_id)}`,
        reason: reasoner.why(item.why),
        fallback: item.off_reason
          ? t(`result.missing.item.${item.off_reason}`)
          : t("result.missing.unknownPoint"),
        testId: `sp-item-missing-${point.id}-${item.doc_id}`,
      }));
  });
  return (
    <div className="sp-deadlines" data-testid="sp-deadlines">
      {outcome.points.length === 0 ? (
        <Hint testId="sp-deadlines-none">{t("result.deadlines.empty")}</Hint>
      ) : (
        <ul className="sp-rows">
          {outcome.points.map((point) => {
            const active = point.items.filter((item) => item.active);
            const hint = point.deadline_hint
              ? pickLocalized(point.deadline_hint, lang, "")
              : "";
            return (
              <PickRow
                key={point.id}
                sel={sections.point(point.id)}
                icon={<CalendarDays size="1rem" />}
                title={pickLocalized(point.name, lang, point.id)}
                badges={
                  <span className="chip accent sp-badge">
                    {active.length === 0
                      ? t("result.deadlines.nothing")
                      : t("result.deadlines.docs", { count: active.length })}
                  </span>
                }
                sub={
                  <>
                    {hint}
                    {active.length > 0 ? (
                      <span className="sp-row-note">
                        {active.map((item) => docName(item.doc_id)).join(", ")}
                      </span>
                    ) : null}
                  </>
                }
                testId={`sp-point-${point.id}`}
              />
            );
          })}
        </ul>
      )}
      <Missing
        title={t("result.missing.titleDeadlines")}
        rows={missing}
        testId="sp-deadlines-missing"
      />
    </div>
  );
};

/** Подписи: в какой точке кто и в каком порядке подписывает; пропущенные условием отдельно. */
export const SignaturesBody = ({ outcome, reasoner }: Props) => {
  const { t, i18n } = useTranslation("packSpace");
  const lang = i18n.language;
  const signed = outcome.points.filter(
    (point) =>
      point.route.pairs.length > 0 || routeSteps(outcome, point).length > 0,
  );
  const docName = (id: string): string => {
    const doc = outcome.documents.find((item) => item.id === id);
    return doc ? pickLocalized(doc.name, lang, doc.id) : id;
  };
  const missing: MissingRow[] = outcome.points.flatMap((point) => {
    const pointName = shortName(pickLocalized(point.name, lang, point.id));
    return point.route.skipped.map((pair) => ({
      key: `${point.id}/${pair.doc_id}/${pair.slot_id}`,
      sel: sections.skipped(point.id, pair.doc_id, pair.slot_id),
      icon: <PenLine size="1rem" />,
      title: `${pointName}: ${docName(pair.doc_id)}`,
      reason: reasoner.why(pair.why),
      fallback: t("result.signatures.skipped", {
        name: personaLabel(t, pair.slot_id),
      }),
      testId: `sp-sign-missing-${point.id}-${pair.doc_id}-${pair.slot_id}`,
    }));
  });
  return (
    <div className="sp-signatures" data-testid="sp-signatures">
      {signed.length === 0 ? (
        <Hint testId="sp-signatures-none">{t("result.signatures.empty")}</Hint>
      ) : (
        <ul className="sp-rows">
          {signed.map((point) => (
            <PickRow
              key={point.id}
              sel={sections.route(point.id)}
              icon={<PenLine size="1rem" />}
              title={pickLocalized(point.name, lang, point.id)}
              badges={
                <span className="chip accent sp-badge">
                  {t("result.signatures.count", {
                    count: point.route.pairs.length,
                  })}
                </span>
              }
              sub={routeText(t, outcome, point)}
              testId={`sp-sign-${point.id}`}
            />
          ))}
        </ul>
      )}
      <Missing
        title={t("result.missing.titleSignatures")}
        rows={missing}
        testId="sp-signatures-missing"
      />
    </div>
  );
};
