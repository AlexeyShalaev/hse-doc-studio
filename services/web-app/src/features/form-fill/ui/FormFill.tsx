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
    style={{ padding: 18, display: "flex", flexDirection: "column", gap: 14 }}
  >
    {title && (
      <h3 style={{ margin: 0, fontSize: 13, fontWeight: 600 }}>{title}</h3>
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
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.25fr) minmax(0, 1fr)",
        gap: 20,
        marginTop: 24,
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
          style={{ gap: 10, padding: "0 4px" }}
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
          <span style={{ fontSize: 12.5 }}>{t("editor.signedCheckbox")}</span>
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
              padding: "10px 14px",
              borderBottom: "1px solid var(--border)",
              background: "var(--bg-2)",
            }}
          >
            <div className="flex items-center gap-2">
              <FileText size={12} style={{ color: "var(--fg-2)" }} />
              <span className="mono" style={{ fontSize: 11 }}>
                {preview?.output_name ?? t("preview.fallbackName")}
              </span>
            </div>
            {form.complete ? (
              <span
                className="chip"
                style={{ color: "var(--c-ok)", borderColor: "var(--c-ok)" }}
              >
                <Check size={10} /> {t("preview.ready")}
              </span>
            ) : (
              <span
                className="chip"
                style={{ color: "var(--c-warn)", borderColor: "var(--c-warn)" }}
              >
                <AlertTriangle size={10} /> {t("preview.incomplete")}
              </span>
            )}
          </div>

          <div
            className="code"
            style={{
              padding: 14,
              fontFamily: "var(--font-mono)",
              fontSize: 11.5,
              lineHeight: 1.7,
              background: "var(--bg-0)",
              maxHeight: 460,
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
            style={{ padding: 10, borderTop: "1px solid var(--border)" }}
          >
            <button
              type="button"
              className="btn primary flex-1"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? <Spinner size="sm" /> : <Save size={11} />}
              {dirty ? t("preview.saveDirty") : t("preview.save")}
            </button>
            <button
              type="button"
              className="btn"
              onClick={handleCopy}
              disabled={!preview}
            >
              <Copy size={11} />
            </button>
          </div>
        </div>

        {!form.complete && form.errors.length > 0 && (
          <div
            className="card"
            style={{
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 6,
            }}
          >
            <span
              className="dim"
              style={{
                fontSize: 11,
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
                style={{ fontSize: 12, color: "var(--c-warn)" }}
              >
                <AlertTriangle
                  size={12}
                  style={{ flexShrink: 0, marginTop: 2 }}
                />
                <span>{err.message}</span>
              </div>
            ))}
            {dirty && (
              <span className="dim" style={{ fontSize: 11 }}>
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
      <div className="flex justify-center" style={{ padding: 32 }}>
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
