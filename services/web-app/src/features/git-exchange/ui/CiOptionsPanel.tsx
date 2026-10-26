import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Notice } from "@shared/ui/ConflictKit";
import { Spinner } from "@shared/ui/Spinner";
import {
  CI_PROVIDERS,
  CI_PUBLISH,
  CI_TRIGGERS,
  toggleDoc,
  toggleTrigger,
  type CiOptions,
  type CiProblem,
} from "../model/ciOptions";
import { CheckRow } from "./CheckRow";
import { Segmented } from "./Segmented";

export type CiDocumentChoice = { id: string; label: string };

export type CiOptionsPanelProps = {
  options: CiOptions;
  onChange: (next: CiOptions) => void;
  documents: CiDocumentChoice[];
  documentsLoading: boolean;
  documentsFailed: boolean;
  problems: CiProblem[];
  disabled?: boolean;
};

const Group = ({ title, children }: { title: string; children: ReactNode }) => (
  <fieldset
    className="flex flex-col"
    style={{ gap: 8, margin: 0, padding: 0, border: 0, minWidth: 0 }}
  >
    <legend
      style={{
        padding: 0,
        marginBottom: 8,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: "var(--fg-2)",
      }}
    >
      {title}
    </legend>
    {children}
  </fieldset>
);

// Что собирать и когда: настройки файла автосборки. Каждое изменение сразу
// отражается в предпросмотре справа.
export const CiOptionsPanel = ({
  options,
  onChange,
  documents,
  documentsLoading,
  documentsFailed,
  problems,
  disabled = false,
}: CiOptionsPanelProps) => {
  const { t } = useTranslation("gitExchange");
  const imageId = useId();

  return (
    <div className="flex flex-col" style={{ gap: 18 }}>
      <Group title={t("ci.options.provider")}>
        <Segmented
          label={t("ci.options.provider")}
          disabled={disabled}
          value={options.provider}
          options={CI_PROVIDERS.map((value) => ({
            value,
            label: t(`ci.provider.${value}`),
          }))}
          onChange={(provider) => {
            onChange({ ...options, provider });
          }}
        />
      </Group>

      <Group title={t("ci.options.documents")}>
        <Segmented
          label={t("ci.options.documents")}
          disabled={disabled}
          value={options.docsMode}
          options={[
            { value: "all", label: t("ci.docs.all") },
            { value: "selected", label: t("ci.docs.selected") },
          ]}
          onChange={(docsMode) => {
            onChange({ ...options, docsMode });
          }}
        />
        {options.docsMode === "selected" && (
          <div
            className="flex flex-col"
            data-testid="ci-docs"
            style={{
              gap: 6,
              maxHeight: 148,
              overflowY: "auto",
              padding: 8,
              borderRadius: "var(--r-2)",
              border: "1px solid var(--border)",
              background: "var(--bg-1)",
            }}
          >
            {documentsLoading && (
              <span
                className="flex items-center dim"
                style={{ gap: 8, fontSize: 12 }}
                role="status"
              >
                <Spinner size="sm" />
                {t("ci.docs.loading")}
              </span>
            )}
            {documentsFailed && (
              <span className="dim" style={{ fontSize: 12 }} role="alert">
                {t("ci.docs.failed")}
              </span>
            )}
            {!documentsLoading &&
              !documentsFailed &&
              documents.length === 0 && (
                <span className="dim" style={{ fontSize: 12 }}>
                  {t("ci.docs.empty")}
                </span>
              )}
            {documents.map((doc) => (
              <CheckRow
                key={doc.id}
                disabled={disabled}
                checked={options.docs.includes(doc.id)}
                onChange={() => {
                  onChange({
                    ...options,
                    docs: toggleDoc(options.docs, doc.id),
                  });
                }}
              >
                {doc.label}
              </CheckRow>
            ))}
          </div>
        )}
        {problems.includes("no_documents") && (
          <Notice
            tone="warn"
            role="status"
            text={t("ci.problem.no_documents")}
          />
        )}
      </Group>

      <Group title={t("ci.options.publish")}>
        <Segmented
          label={t("ci.options.publish")}
          disabled={disabled}
          value={options.publish}
          options={CI_PUBLISH.map((value) => ({
            value,
            label: t(`ci.publish.${value}.label`),
          }))}
          onChange={(publish) => {
            onChange({ ...options, publish });
          }}
        />
        <p
          className="dim"
          style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5 }}
        >
          {t(`ci.publish.${options.publish}.hint`)}
        </p>
      </Group>

      <Group title={t("ci.options.triggers")}>
        {CI_TRIGGERS.map((trigger) => (
          <CheckRow
            key={trigger}
            disabled={disabled}
            checked={options.triggers.includes(trigger)}
            onChange={() => {
              onChange({
                ...options,
                triggers: toggleTrigger(options.triggers, trigger),
              });
            }}
            testId={`ci-trigger-${trigger}`}
          >
            {t(`ci.trigger.${trigger}`)}
          </CheckRow>
        ))}
        {problems.includes("no_triggers") && (
          <Notice
            tone="warn"
            role="status"
            text={t("ci.problem.no_triggers")}
          />
        )}
      </Group>

      <details>
        <summary
          style={{ cursor: "pointer", fontSize: 12, color: "var(--fg-1)" }}
        >
          {t("ci.advanced.title")}
        </summary>
        <div className="field" style={{ marginTop: 10 }}>
          <label htmlFor={imageId}>{t("ci.advanced.image")}</label>
          <input
            id={imageId}
            className="input mono"
            value={options.image}
            disabled={disabled}
            spellCheck={false}
            autoComplete="off"
            placeholder={t("ci.advanced.imagePlaceholder")}
            onChange={(event) => {
              onChange({ ...options, image: event.target.value });
            }}
          />
          <p className="hint" style={{ margin: 0 }}>
            {t("ci.advanced.imageHint")}
          </p>
        </div>
      </details>
    </div>
  );
};
