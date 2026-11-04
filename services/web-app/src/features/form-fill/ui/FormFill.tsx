import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Check, Copy, FileText, Save } from "lucide-react";
import {
  useForm,
  useFormPreview,
  useUpdateForm,
  type FormAnswers,
  type FormData,
} from "@entities/form";
import { Spinner } from "@shared/ui/Spinner";
import { toast } from "@shared/lib";
import {
  computeDefaults,
  isFieldVisible,
  loc,
  mergeAnswers,
} from "../lib/forms";
import { FieldRenderer } from "./FieldRenderer";

export type FormFillProps = {
  projectId: string;
  formId: string;
  lang?: string;
};

const Card = ({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) => (
  <div
    className="card"
    style={{
      padding: "1.125rem",
      display: "flex",
      flexDirection: "column",
      gap: "0.875rem",
    }}
  >
    {title && (
      <h3 style={{ margin: 0, fontSize: "0.8125rem", fontWeight: 600 }}>
        {title}
      </h3>
    )}
    {children}
  </div>
);

type FormEditorProps = {
  projectId: string;
  formId: string;
  form: FormData;
  lang: string;
};

// Inner editor: state is initialized once from the loaded form (lazy initial
// state, no effect). Remounted via `key={formId}` when the form changes, which
// resets the buffer cleanly.
const FormEditor = ({ projectId, formId, form, lang }: FormEditorProps) => {
  const { t } = useTranslation("formFill");
  const { data: preview } = useFormPreview(projectId, formId, true);
  const { mutate: updateForm, isPending: saving } = useUpdateForm();

  const [answers, setAnswers] = useState<FormAnswers>(() =>
    mergeAnswers(computeDefaults(form.sections), form.answers),
  );
  const [completed, setCompleted] = useState<boolean>(form.completed);
  const [dirty, setDirty] = useState(false);

  const setField = (id: string, value: unknown) => {
    setAnswers((prev) => ({ ...prev, [id]: value }));
    setDirty(true);
  };

  const handleSave = () => {
    updateForm(
      { projectId, formId, body: { completed, answers } },
      {
        onSuccess: () => {
          setDirty(false);
          toast.success(t("toast.saved"));
        },
      },
    );
  };

  const handleCopy = () => {
    if (!preview) return;
    navigator.clipboard
      .writeText(preview.content)
      .then(() => {
        toast.info(t("toast.copied"));
      })
      .catch(() => {
        toast.error(t("toast.copyFailed"));
      });
  };

  return (
    <div
      className="grid-split"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)",
        gap: "1.25rem",
        marginTop: "1.5rem",
      }}
    >
      <div className="flex flex-col gap-4">
        {form.sections.map((section) => {
          const visible = section.fields.filter((f) =>
            isFieldVisible(f, answers),
          );
          if (visible.length === 0) return null;
          return (
            <Card key={section.id} title={loc(section.title, lang)}>
              {visible.map((field) => (
                <FieldRenderer
                  key={field.id}
                  field={field}
                  value={answers[field.id]}
                  lang={lang}
                  onChange={(v) => {
                    setField(field.id, v);
                  }}
                />
              ))}
            </Card>
          );
        })}

        <label
          className="flex items-center cursor-pointer"
          style={{ gap: "0.625rem", padding: "0 0.25rem" }}
        >
          <input
            type="checkbox"
            checked={completed}
            onChange={(e) => {
              setCompleted(e.target.checked);
              setDirty(true);
            }}
            style={{ accentColor: "var(--accent)" }}
          />
          <span style={{ fontSize: "0.78125rem" }}>
            {t("editor.signedCheckbox")}
          </span>
        </label>
      </div>

      <div className="flex flex-col gap-3">
        <div
          className="card"
          style={{ padding: 0, overflow: "hidden", position: "sticky", top: 0 }}
        >
          <div
            className="flex items-center justify-between"
            style={{
              padding: "0.625rem 0.875rem",
              borderBottom: "1px solid var(--border)",
              background: "var(--bg-2)",
            }}
          >
            <div className="flex items-center gap-2">
              <FileText size="0.75rem" style={{ color: "var(--fg-2)" }} />
              <span className="mono" style={{ fontSize: "0.6875rem" }}>
                {preview?.output_name ?? t("preview.fallbackName")}
              </span>
            </div>
            {form.complete ? (
              <span
                className="chip"
                style={{ color: "var(--c-ok)", borderColor: "var(--c-ok)" }}
              >
                <Check size="0.625rem" /> {t("preview.ready")}
              </span>
            ) : (
              <span
                className="chip"
                style={{ color: "var(--c-warn)", borderColor: "var(--c-warn)" }}
              >
                <AlertTriangle size="0.625rem" /> {t("preview.incomplete")}
              </span>
            )}
          </div>

          <div
            className="code"
            style={{
              padding: "0.875rem",
              fontFamily: "var(--font-mono)",
              fontSize: "0.71875rem",
              lineHeight: 1.7,
              background: "var(--bg-0)",
              maxHeight: "28.75rem",
              overflowY: "auto",
            }}
          >
            <pre
              style={{
                margin: 0,
                fontFamily: "inherit",
                whiteSpace: "pre-wrap",
              }}
            >
              {preview?.content ?? t("preview.unavailable")}
            </pre>
          </div>

          <div
            className="flex gap-2"
            style={{
              padding: "0.625rem",
              borderTop: "1px solid var(--border)",
            }}
          >
            <button
              type="button"
              className="btn primary flex-1"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? <Spinner size="sm" /> : <Save size="0.6875rem" />}
              {dirty ? t("preview.saveDirty") : t("preview.save")}
            </button>
            <button
              type="button"
              className="btn"
              onClick={handleCopy}
              disabled={!preview}
            >
              <Copy size="0.6875rem" />
            </button>
          </div>
        </div>

        {!form.complete && form.errors.length > 0 && (
          <div
            className="card"
            style={{
              padding: "0.875rem",
              display: "flex",
              flexDirection: "column",
              gap: "0.375rem",
            }}
          >
            <span
              className="dim"
              style={{
                fontSize: "0.6875rem",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              {t("errors.title")}
            </span>
            {form.errors.map((err) => (
              <div
                key={err.field_id}
                className="flex items-start gap-2"
                style={{ fontSize: "0.75rem", color: "var(--c-warn)" }}
              >
                <AlertTriangle
                  size="0.75rem"
                  style={{ flexShrink: 0, marginTop: "0.125rem" }}
                />
                <span>{err.message}</span>
              </div>
            ))}
            {dirty && (
              <span className="dim" style={{ fontSize: "0.6875rem" }}>
                {t("errors.saveHint")}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export const FormFill = ({ projectId, formId, lang = "ru" }: FormFillProps) => {
  const { data, isLoading } = useForm(projectId, formId);

  if (isLoading || !data) {
    return (
      <div className="flex justify-center" style={{ padding: "2rem" }}>
        <Spinner />
      </div>
    );
  }

  return (
    <FormEditor
      key={formId}
      projectId={projectId}
      formId={formId}
      form={data}
      lang={lang}
    />
  );
};
