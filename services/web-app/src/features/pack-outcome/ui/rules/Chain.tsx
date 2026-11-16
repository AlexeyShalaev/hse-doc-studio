import { Suspense, useState } from "react";
import { Cpu, ExternalLink, FileCode, Pencil } from "lucide-react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { packNewVersionPath, type OutcomeTrace } from "@entities/pack-studio";
import { Badge } from "@shared/ui";
import { isEditableShape, shapeOf } from "../../lib/edit/shape";
import type { TraceText } from "../../lib/explain";
import { useOutcomeModel } from "../../model";
import { useRuleEdit } from "../edit/context";
import { LazyRuleEditor } from "../edit/lazy";
import { useOpenRule } from "./useOpenRule";
import { DecisionStatus } from "./StateChip";

type ChainProps = {
  chain: readonly OutcomeTrace[];
  text: TraceText;
  /** Телефон: правка и переход к файлам только на компьютере. */
  phone: boolean;
};

const Origin = ({ trace, phone }: { trace: OutcomeTrace; phone: boolean }) => {
  const { t } = useTranslation("packOutcome");
  const rules = useOpenRule();
  const edit = useRuleEdit();
  const model = useOutcomeModel();
  const [editing, setEditing] = useState(false);
  const { rule } = trace;
  if (rule.origin === "builtin") {
    const name = rule.builtin ?? "";
    return (
      <p
        className="po-chain-origin"
        data-testid={`outcome-chain-${trace.id}-builtin`}
      >
        <Badge
          variant="info"
          title={t(`rules.builtin.${name}`, { defaultValue: "" })}
        >
          <Cpu size="0.75rem" aria-hidden="true" />
          {t("rules.inEngine")}
        </Badge>
        <span className="po-note">
          {t(`rules.builtin.${name}`, {
            defaultValue: t("rules.builtin.other"),
          })}
        </span>
      </p>
    );
  }
  const where = rules.locate(rule);
  const shape = shapeOf(rule.pointer ?? "");
  const editable =
    where !== null &&
    !phone &&
    edit?.available === true &&
    isEditableShape(shape);
  return (
    <div
      className="po-chain-origin"
      data-testid={`outcome-chain-${trace.id}-origin`}
    >
      <p className="po-mono po-chain-where">
        <FileCode size="0.75rem" aria-hidden="true" />
        <span>
          {rule.file}
          <span className="po-chain-pointer">{rule.pointer}</span>
        </span>
      </p>
      {where && !phone && (
        <span className="po-chain-actions">
          {editable && edit && (
            <button
              type="button"
              className="btn sm"
              aria-expanded={editing}
              aria-describedby={
                edit.blocked ? `po-edit-why-${trace.id}` : undefined
              }
              disabled={edit.blocked !== null}
              data-testid={`outcome-chain-${trace.id}-edit`}
              onClick={() => {
                edit.begin();
                setEditing((open) => !open);
              }}
            >
              <Pencil size="0.75rem" aria-hidden="true" />
              {t("rules.editRule")}
            </button>
          )}
          <button
            type="button"
            className="btn sm"
            data-testid={`outcome-chain-${trace.id}-open`}
            onClick={() => {
              rules.open(rule);
            }}
          >
            <ExternalLink size="0.75rem" aria-hidden="true" />
            {t("rules.openRule")}
          </button>
          {where.form && (
            <button
              type="button"
              className="btn sm"
              data-testid={`outcome-chain-${trace.id}-source`}
              onClick={() => {
                rules.open(rule, "source");
              }}
            >
              {t("rules.openSource")}
            </button>
          )}
        </span>
      )}
      {editable && edit?.blocked && (
        <p
          className="po-note"
          id={`po-edit-why-${trace.id}`}
          data-testid={`outcome-chain-${trace.id}-edit-why`}
        >
          {t(`edit.blocked.${edit.blocked}`)}{" "}
          {edit.blocked === "released" && (
            <Link
              className="po-edit-link"
              data-testid={`outcome-chain-${trace.id}-new-version`}
              to={packNewVersionPath(model.workspaceId, model.ref)}
            >
              {t("edit.newVersion")}
            </Link>
          )}
        </p>
      )}
      {editable && shape && where && editing && !edit.blocked && (
        <Suspense
          fallback={
            <p className="po-note" role="status">
              {t("edit.loading")}
            </p>
          }
        >
          <LazyRuleEditor
            trace={trace}
            target={{
              file: rule.file ?? "",
              pointer: rule.pointer ?? "",
              shape,
              kind: trace.kind,
            }}
            onClose={() => {
              setEditing(false);
            }}
          />
        </Suspense>
      )}
    </div>
  );
};

/**
 * Цепочка решений элемента: нумерованный список в порядке сервера. У каждого решения исход
 * (слово и значок), условие человеческой фразой, факт «сейчас такое-то значение» и место правила.
 */
export const Chain = ({ chain, text, phone }: ChainProps) => {
  const { t } = useTranslation("packOutcome");
  return (
    <ol
      className="po-chain"
      aria-label={t("rules.chain.title")}
      data-testid="outcome-chain"
    >
      {chain.map((trace, index) => {
        const facts = text.facts(trace);
        return (
          <li
            key={trace.id}
            className="po-chain-item"
            data-status={trace.status}
            data-testid={`outcome-chain-${trace.id}`}
          >
            <div className="po-chain-head">
              <span className="po-chain-no" aria-hidden="true">
                {index + 1}
              </span>
              <DecisionStatus
                status={trace.status}
                testId={`outcome-chain-${trace.id}-status`}
              />
              <span className="po-chain-kind">
                {t(`rules.kinds.${trace.kind}`, { defaultValue: trace.kind })}
              </span>
            </div>
            <p
              className="po-chain-cond"
              data-testid={`outcome-chain-${trace.id}-cond`}
            >
              {trace.terms.length > 0
                ? text.condition(trace)
                : t("rules.noTerms")}
            </p>
            {trace.status === "skipped" && (
              <p className="po-note">{t("rules.skippedNote")}</p>
            )}
            {facts.length > 0 && (
              <p
                className="po-chain-facts"
                data-testid={`outcome-chain-${trace.id}-facts`}
              >
                <span className="po-note">{t("rules.now")}</span>{" "}
                {facts.map((fact, i) => (
                  <span
                    key={`${fact.subject}-${String(i)}`}
                    className="po-fact"
                  >
                    {fact.subject}: <b>{fact.value}</b>
                  </span>
                ))}
              </p>
            )}
            <Origin trace={trace} phone={phone} />
          </li>
        );
      })}
    </ol>
  );
};
