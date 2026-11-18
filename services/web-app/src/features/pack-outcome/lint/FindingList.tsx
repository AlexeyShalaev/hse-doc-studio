import { CircleAlert, FileCode2, Info, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { OutcomeFinding } from "@entities/pack-studio";
import {
  MAX_WITNESSES,
  type IndexedFinding,
  type Severity,
  type SeverityGroup,
} from "../lib/lint";
import { useLintActions } from "./context";
import { WitnessLine } from "./WitnessLine";

const ICON = {
  error: CircleAlert,
  warning: TriangleAlert,
  info: Info,
} satisfies Record<Severity, typeof Info>;

/** Сколько элементов результата показывать у находки, остальное числом. */
const MAX_ELEMENTS = 6;

type FindingProps = { item: IndexedFinding };

/**
 * Одна находка: уровень значком и словом, сообщение и подсказка «Как исправить» от сервера (как
 * есть), место (файл, строка), затронутые элементы и до трёх комбинаций-свидетелей. Действия:
 * «Открыть правило», «Показать в результате» (по элементу), «Показать комбинацию» (по свидетелю).
 */
const FindingItem = ({ item }: FindingProps) => {
  const { t } = useTranslation("packOutcome");
  const { showElement, openPlace } = useLintActions();
  const finding: OutcomeFinding = item.finding;
  const Icon = ICON[finding.severity];
  const elements = finding.elements.slice(0, MAX_ELEMENTS);
  const witnesses = finding.witnesses.slice(0, MAX_WITNESSES);
  return (
    <li
      className="ln-finding"
      data-severity={finding.severity}
      data-testid="outcome-lint-finding"
      data-rule={finding.rule_id}
    >
      <div className="ln-finding-head">
        <span className="ln-sev" data-severity={finding.severity}>
          <Icon size="0.875rem" aria-hidden="true" />
          <span>{t(`lint.severity.${finding.severity}`)}</span>
        </span>
        <span className="po-mono ln-rule">{finding.rule_id}</span>
      </div>
      <p className="ln-message">{finding.message}</p>
      {finding.hint ? (
        <p className="ln-hint" data-testid="outcome-lint-hint">
          <span className="ln-hint-label">{t("lint.finding.hint")}</span>{" "}
          {finding.hint}
        </p>
      ) : null}
      {finding.file ? (
        <p className="ln-place" data-testid="outcome-lint-place">
          <FileCode2 size="0.8125rem" aria-hidden="true" />
          <span className="po-mono">
            {finding.file}
            {finding.line !== null
              ? ` ${t("lint.finding.line", { line: finding.line })}`
              : ""}
          </span>
        </p>
      ) : null}
      {elements.length > 0 ? (
        <div className="ln-elements">
          <span className="po-note">{t("lint.finding.elements")}</span>
          <ul className="ln-chips">
            {elements.map((element) => (
              <li key={`${element.section}:${element.id}`}>
                <button
                  type="button"
                  className="ln-chip"
                  data-testid="outcome-lint-show-element"
                  aria-label={t("lint.finding.showInResultOf", {
                    section: t(`sections.${element.section}`),
                    id: element.id,
                  })}
                  onClick={() => {
                    showElement(element);
                  }}
                >
                  <span className="ln-chip-section">
                    {t(`sections.${element.section}`)}
                  </span>
                  <span className="po-mono">{element.id}</span>
                </button>
              </li>
            ))}
          </ul>
          {finding.elements.length > elements.length ? (
            <span className="po-note">
              {t("lint.finding.moreElements", {
                count: finding.elements.length - elements.length,
              })}
            </span>
          ) : null}
        </div>
      ) : null}
      {witnesses.length > 0 ? (
        <div className="ln-witnesses">
          <span className="po-note">{t("lint.finding.witnesses")}</span>
          {witnesses.map((witness, index) => (
            <WitnessLine key={index} witness={witness} />
          ))}
        </div>
      ) : null}
      <div className="ln-actions">
        {finding.file ? (
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-lint-open-rule"
            onClick={() => {
              openPlace(finding.file ?? "", finding.pointer);
            }}
          >
            {t("lint.finding.openRule")}
          </button>
        ) : null}
        {finding.elements[0] ? (
          <button
            type="button"
            className="btn sm"
            data-testid="outcome-lint-show-result"
            onClick={() => {
              const first = finding.elements[0];
              if (first) showElement(first);
            }}
          >
            {t("lint.finding.showInResult")}
          </button>
        ) : null}
      </div>
    </li>
  );
};

type FindingListProps = { groups: readonly SeverityGroup[] };

/**
 * Находки по уровням (ошибки, предупреждения, информация) и правилам. Каждая группа это заголовок
 * и список (`ul`), так что программа экрана читает число находок и переходит по заголовкам.
 */
export const FindingList = ({ groups }: FindingListProps) => {
  const { t } = useTranslation("packOutcome");
  return (
    <div className="ln-groups" data-testid="outcome-lint-groups">
      {groups.map((group) => (
        <section
          key={group.severity}
          className="ln-group"
          data-severity={group.severity}
          aria-labelledby={`ln-group-${group.severity}`}
          data-testid={`outcome-lint-group-${group.severity}`}
        >
          <h3 className="ln-group-title" id={`ln-group-${group.severity}`}>
            {t(`lint.group.${group.severity}`)}
            <span className="ln-group-count">{group.count}</span>
          </h3>
          {group.rules.map((rule) => (
            <div key={rule.rule} className="ln-rulegroup">
              <h4 className="ln-rulegroup-title po-mono">
                {rule.rule}
                <span className="ln-group-count">{rule.items.length}</span>
              </h4>
              <ul
                className="ln-list"
                aria-label={t("lint.group.listOf", { rule: rule.rule })}
              >
                {rule.items.map((item) => (
                  <FindingItem key={item.id} item={item} />
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
};
