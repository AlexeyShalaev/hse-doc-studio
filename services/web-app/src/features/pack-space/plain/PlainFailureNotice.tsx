import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import { plainFailure, type FailureInput } from "./failure";
import "./plain.css";

/** Строки «название: значение» под «Технические подробности»; пусто, если подробностей нет. */
export const TechDetails = ({
  rows,
}: {
  rows: readonly { label: string; value: string }[];
}) => {
  const { t } = useTranslation("packSpace");
  if (rows.length === 0) return null;
  return (
    <details className="sp-pl-tech">
      <summary>{t("plain.tech.summary")}</summary>
      <dl>
        {rows.map((row) => (
          <div key={row.label} style={{ display: "contents" }}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
};

/**
 * Сбой сборки PDF: что случилось и что делать словами, сырой текст сервера (Docker, пути) свёрнут в
 * «Технические подробности». `action` это кнопка рядом («Собрать ещё раз»).
 */
export const PlainFailureNotice = ({
  input,
  action,
  lead,
  extra,
  techExtra = [],
  testId,
}: {
  input: FailureInput;
  action?: ReactNode;
  /** Жирная первая фраза, если заголовок причины не первый («Не удалось собрать PDF…»). */
  lead?: string;
  /** Фраза после «Что делать» (например, «Место ошибки видно в журнале»). */
  extra?: ReactNode;
  /** Ещё строки в технические подробности (например, поле и значение отказа запроса). */
  techExtra?: readonly { label: string; value: string }[];
  testId?: string;
}) => {
  const { t } = useTranslation("packSpace");
  const words = plainFailure(input, t);
  return (
    <div data-testid={testId} data-family={words.family}>
      <Notice
        tone="err"
        role="alert"
        text={
          <span>
            {lead ? (
              <>
                <b>{lead}</b> {words.title}.
              </>
            ) : (
              <b>{words.title}.</b>
            )}{" "}
            {words.how}
            {extra ? <> {extra}</> : null}
            <TechDetails rows={[...words.tech, ...techExtra]} />
          </span>
        }
        action={action}
      />
    </div>
  );
};
