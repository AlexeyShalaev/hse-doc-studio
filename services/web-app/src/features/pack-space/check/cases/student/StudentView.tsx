import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { PackOutcome } from "@entities/pack-studio";
import { personaLabel } from "@entities/pack-studio/outcome/personas";
import {
  studentDocuments,
  studentForms,
  studentMeta,
  studentRoute,
  type StudentDocument,
  type StudentField,
} from "@entities/pack-studio/outcome/studentView";
import "./student.css";

const Block = ({
  title,
  lead,
  testId,
  children,
}: {
  title: string;
  lead: string;
  testId: string;
  children: ReactNode;
}) => {
  const id = useId();
  return (
    <section className="po-st-block" aria-labelledby={id} data-testid={testId}>
      <h3 className="po-st-title" id={id}>
        {title}
      </h3>
      <p className="po-st-lead">{lead}</p>
      {children}
    </section>
  );
};

const Empty = ({ children, testId }: { children: string; testId: string }) => (
  <p className="po-st-empty" data-testid={testId}>
    {children}
  </p>
);

const DocumentsBlock = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const docs = studentDocuments(outcome, i18n.language);
  // Группа без подписи в словаре (чужой id) уходит в «Прочее»: технические id студенту не нужны.
  const label = (group: string): string =>
    group === "" ? "" : t(`documents.groups.${group}`, { defaultValue: "" });
  const groups = new Map<string, StudentDocument[]>();
  for (const doc of docs) {
    const key = label(doc.group);
    const list = groups.get(key);
    if (list) list.push(doc);
    else groups.set(key, [doc]);
  }
  return (
    <Block
      title={t("student.documents.title")}
      lead={t("student.documents.lead", { count: docs.length })}
      testId="outcome-student-documents"
    >
      {docs.length === 0 ? (
        <Empty testId="outcome-student-documents-empty">
          {t("student.documents.empty")}
        </Empty>
      ) : (
        [...groups.entries()].map(([group, items]) => (
          <DocGroup
            key={group}
            title={group === "" ? t("student.documents.other") : group}
            showTitle={groups.size > 1}
            items={items}
          />
        ))
      )}
    </Block>
  );
};

const DocGroup = ({
  title,
  showTitle,
  items,
}: {
  title: string;
  showTitle: boolean;
  items: StudentDocument[];
}) => {
  const { t } = useTranslation("packOutcome");
  const id = useId();
  return (
    <div className="po-st-group">
      {showTitle && (
        <h4 className="po-st-sub" id={id}>
          {title}
        </h4>
      )}
      <ul className="po-st-list" aria-labelledby={showTitle ? id : undefined}>
        {items.map((doc) => (
          <li
            key={doc.id}
            className="po-st-item"
            data-testid={`outcome-student-doc-${doc.id}`}
          >
            <span className="po-st-name">
              {doc.name}
              {!doc.required && (
                <span className="po-st-tag">{t("student.optional")}</span>
              )}
            </span>
            {doc.files.length > 0 && (
              <span className="po-st-files">
                {doc.files.map((file) => (
                  <span
                    key={`${file.owner ?? ""}/${file.name}`}
                    className="po-st-file"
                  >
                    {file.owner && (
                      <span className="po-st-owner">{file.owner}</span>
                    )}
                    <span className="po-mono">{file.name}</span>
                  </span>
                ))}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

const FieldList = ({
  title,
  fields,
  testId,
}: {
  title: string;
  fields: StudentField[];
  testId: string;
}) => {
  const { t } = useTranslation("packOutcome");
  const id = useId();
  if (fields.length === 0) return null;
  return (
    <div className="po-st-group" data-testid={testId}>
      <h4 className="po-st-sub" id={id}>
        {title}
      </h4>
      <ul className="po-st-list" aria-labelledby={id}>
        {fields.map((field) => (
          <li key={field.id} className="po-st-item">
            <span className="po-st-name">
              {field.label}
              {field.perAuthor && (
                <span className="po-st-tag">{t("student.perAuthor")}</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
};

const FieldsBlock = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const meta = studentMeta(outcome, i18n.language);
  const forms = studentForms(outcome, i18n.language);
  const none =
    meta.create.length + meta.finalize.length === 0 && forms.length === 0;
  const formsId = useId();
  return (
    <Block
      title={t("student.fields.title")}
      lead={t("student.fields.lead")}
      testId="outcome-student-fields"
    >
      {none ? (
        <Empty testId="outcome-student-fields-empty">
          {t("student.fields.empty")}
        </Empty>
      ) : (
        <>
          <FieldList
            title={t("student.fields.create")}
            fields={meta.create}
            testId="outcome-student-fields-create"
          />
          <FieldList
            title={t("student.fields.finalize")}
            fields={meta.finalize}
            testId="outcome-student-fields-finalize"
          />
          {forms.length > 0 && (
            <div className="po-st-group" data-testid="outcome-student-forms">
              <h4 className="po-st-sub" id={formsId}>
                {t("student.forms.title")}
              </h4>
              <ul className="po-st-list" aria-labelledby={formsId}>
                {forms.map((form) => (
                  <li
                    key={form.id}
                    className="po-st-item"
                    data-testid={`outcome-student-form-${form.id}`}
                  >
                    <span className="po-st-name">
                      {form.title}
                      {form.required && (
                        <span className="po-st-tag">
                          {t("student.forms.required")}
                        </span>
                      )}
                      {form.perAuthor && (
                        <span className="po-st-tag">
                          {t("student.perAuthor")}
                        </span>
                      )}
                    </span>
                    {form.fields.length > 0 && (
                      <ul className="po-st-sublist">
                        {form.fields.map((field) => (
                          <li key={field.id}>
                            {field.label}
                            {field.required && (
                              <span className="po-st-tag">
                                {t("student.forms.fieldRequired")}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Block>
  );
};

const RouteBlock = ({ outcome }: { outcome: PackOutcome }) => {
  const { t, i18n } = useTranslation("packOutcome");
  const points = studentRoute(outcome, i18n.language);
  return (
    <Block
      title={t("student.route.title")}
      lead={t("student.route.lead")}
      testId="outcome-student-route"
    >
      {points.length === 0 ? (
        <Empty testId="outcome-student-route-empty">
          {t("student.route.empty")}
        </Empty>
      ) : (
        points.map((point) => (
          <div
            key={point.id}
            className="po-st-group"
            data-testid={`outcome-student-point-${point.id}`}
          >
            <h4 className="po-st-sub">{point.name}</h4>
            {point.deadline !== "" && (
              <p className="po-st-deadline">
                {t("student.route.deadline", { hint: point.deadline })}
              </p>
            )}
            <ol className="po-st-steps">
              {point.steps.map((step, index) => (
                <li
                  key={String(index)}
                  className="po-st-step"
                  data-testid={`outcome-student-step-${point.id}-${String(index + 1)}`}
                >
                  <span className="po-st-stepno">
                    {t("student.route.step", { n: index + 1 })}
                    {step.length > 1 && (
                      <span className="po-st-tag">
                        {t("student.route.parallel")}
                      </span>
                    )}
                  </span>
                  <ul className="po-st-people">
                    {step.map((person) => (
                      <li key={person.persona} className="po-st-person">
                        <span className="po-st-name">
                          {personaLabel(t, person.persona)}
                          {person.name !== "" && (
                            <span className="po-st-who">{person.name}</span>
                          )}
                        </span>
                        {person.documents.length > 0 && (
                          <ul className="po-st-sublist">
                            {person.documents.map((doc) => (
                              <li key={doc.id}>
                                {doc.name}
                                {doc.optional && (
                                  <span className="po-st-tag">
                                    {t("student.route.optional")}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          </div>
        ))
      )}
    </Block>
  );
};

/**
 * «Как студент»: упрощённая копия трёх блоков проекта студента (документы, поля, порядок
 * подписания) из того же ответа сервера, без служебных меток, причин, идентификаторов и
 * оверлеев. Это не настоящие компоненты проекта (решение владельца для среза F13).
 */
export const StudentView = ({ outcome }: { outcome: PackOutcome }) => {
  const { t } = useTranslation("packOutcome");
  return (
    <div
      className="po-student"
      role="group"
      aria-label={t("student.label")}
      data-testid="outcome-student"
    >
      <DocumentsBlock outcome={outcome} />
      <FieldsBlock outcome={outcome} />
      <RouteBlock outcome={outcome} />
    </div>
  );
};
