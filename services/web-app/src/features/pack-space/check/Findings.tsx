import { Fragment } from "react";
import { CircleAlert, Eye, Info, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeFinding } from "@entities/pack-studio";
import {
  MAX_WITNESSES,
  type IndexedFinding,
  type Severity,
} from "@entities/pack-studio/outcome/lint";
import { plainFinding } from "../plain/findings";
import type { CheckEnv } from "./useCheckEnv";

const ICON = {
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
} satisfies Record<Severity, typeof Info>;

/** Сколько элементов результата показывать у находки, остальное числом. */
const MAX_ELEMENTS = 6;

/** Условия одной строкой: «Вид работы: исследование; Состав: один». */
export const SituationText = ({
  situation,
  env,
}: {
  situation: Readonly<Record<string, string>>;
  env: CheckEnv;
}) => (
  <>
    {Object.entries(situation)
      .map(
        ([input, value]) =>
          `${env.labeler.input(input)}: ${env.labeler.value(input, value)}`,
      )
      .join("; ")}
  </>
);

/** Ситуация-свидетель одной строкой и кнопка «Показать такую ситуацию». */
export const Witness = ({
  witness,
  env,
}: {
  witness: Readonly<Record<string, string>>;
  env: CheckEnv;
}) => {
  const { t } = useTranslation("packSpace");
  return (
    <div className="sp-ck-witness">
      <span className="sp-ck-witness-text">
        <SituationText situation={witness} env={env} />
      </span>
      <button
        type="button"
        className="btn sm"
        onClick={() => {
          env.showSituation(witness);
        }}
      >
        <Eye size="0.8125rem" aria-hidden="true" />
        {t("check.showSituation")}
      </button>
    </div>
  );
};

/**
 * Одна находка: что не так (уровень значком и словом), как исправить, где видно, что затронуто.
 * Файл, указатель и номер правила спрятаны в «Технические подробности».
 */
const Finding = ({ item, env }: { item: IndexedFinding; env: CheckEnv }) => {
  const { t } = useTranslation("packSpace");
  const finding: OutcomeFinding = item.finding;
  const plain = plainFinding(finding, env.naming, t);
  const Icon = ICON[finding.severity];
  const elements = finding.elements.slice(0, MAX_ELEMENTS);
  const witnesses = finding.witnesses.slice(0, MAX_WITNESSES);
  const first = finding.elements[0];
  return (
    <li
      className="sp-ck-finding"
      data-severity={finding.severity}
      data-testid="check-finding"
    >
      <p className="sp-ck-finding-head">
        <span className="sp-ck-sev" data-severity={finding.severity}>
          <Icon size="0.875rem" aria-hidden="true" />
          {t(`check.issues.severity.${finding.severity}`)}
        </span>
        {finding.line !== null && (
          <span className="sp-ck-note">
            {t("check.issues.line", { line: finding.line })}
          </span>
        )}
      </p>
      <p className="sp-ck-message">{plain.title}</p>
      {plain.extra ? <p className="sp-ck-note">{plain.extra}</p> : null}
      <p className="sp-ck-hint">
        <strong>{t("check.issues.hint")}</strong> {plain.how}
      </p>
      {elements.length > 0 && (
        <div className="sp-ck-chips">
          <span className="sp-ck-note">{t("check.issues.elements")}</span>
          {elements.map((element) => (
            <button
              key={`${element.section}:${element.id}`}
              type="button"
              className="sp-ck-chip"
              aria-label={t("check.issues.showElement", {
                section: t(`check.sections.${element.section}`),
                name: env.naming.element(element.section, element.id),
              })}
              onClick={() => {
                env.showElement(element);
              }}
            >
              {t(`check.sections.${element.section}`)}
              <span className="sp-ck-chip-id">
                {env.naming.element(element.section, element.id)}
              </span>
            </button>
          ))}
          {finding.elements.length > elements.length && (
            <span className="sp-ck-note">
              {t("check.issues.moreElements", {
                count: finding.elements.length - elements.length,
              })}
            </span>
          )}
        </div>
      )}
      {witnesses.length > 0 && (
        <div className="sp-ck-witnesses">
          <span className="sp-ck-note">{t("check.issues.witnesses")}</span>
          {witnesses.map((witness, index) => (
            <Witness key={index} witness={witness} env={env} />
          ))}
        </div>
      )}
      <div className="sp-ck-actions">
        {finding.file ? (
          <button
            type="button"
            className="btn sm"
            onClick={() => {
              env.openFile(finding.file ?? "", finding.pointer);
            }}
          >
            {t("check.issues.openPlace")}
          </button>
        ) : null}
        {first ? (
          <button
            type="button"
            className="btn sm"
            onClick={() => {
              env.showElement(first);
            }}
          >
            {t("check.issues.showInResult")}
          </button>
        ) : null}
      </div>
      <details className="sp-ck-tech">
        <summary>{t("check.tech")}</summary>
        <dl>
          {plain.tech.map((row) => (
            <Fragment key={row.label}>
              <dt>{row.label}</dt>
              <dd>{row.value}</dd>
            </Fragment>
          ))}
        </dl>
      </details>
    </li>
  );
};

/** Находки по уровням: ошибки, замечания, подсказки. Каждая группа это заголовок и список. */
export const FindingGroups = ({
  groups,
  env,
}: {
  groups: readonly { severity: Severity; items: IndexedFinding[] }[];
  env: CheckEnv;
}) => {
  const { t } = useTranslation("packSpace");
  return (
    <div className="sp-ck-groups">
      {groups.map((group) => (
        <section
          key={group.severity}
          aria-labelledby={`sp-ck-group-${group.severity}`}
        >
          <h4 className="sp-ck-h4" id={`sp-ck-group-${group.severity}`}>
            {t(`check.issues.group.${group.severity}`)}
            <span className="sp-ck-count">{group.items.length}</span>
          </h4>
          <ul className="sp-ck-list">
            {group.items.map((item) => (
              <Finding key={item.id} item={item} env={env} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
};
