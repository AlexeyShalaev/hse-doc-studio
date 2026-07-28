import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  ChevronRight,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import {
  buildRequirementsFormatPrompt,
  useUpdateRequirementsFormat,
  type RequirementFormat,
} from "@entities/requirements";
import { useWorkspaceStore } from "@shared/lib";

type Kind = RequirementFormat["kind"];

const LABEL_STYLE: React.CSSProperties = {
  fontSize: 10.5,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "var(--fg-3)",
  marginBottom: 4,
  display: "block",
};

type RequirementsFormatEditorProps = {
  projectId: string;
  format: RequirementFormat;
  overridden: boolean;
};

export const RequirementsFormatEditor = ({
  projectId,
  format,
  overridden,
}: RequirementsFormatEditorProps) => {
  const { t } = useTranslation("workspace");
  const kinds: { value: Kind; label: string; hint: string }[] = [
    {
      value: "macro",
      label: t("requirementsFormat.kindMacroLabel"),
      hint: t("requirementsFormat.kindMacroHint"),
    },
    {
      value: "id",
      label: t("requirementsFormat.kindIdLabel"),
      hint: t("requirementsFormat.kindIdHint"),
    },
    {
      value: "custom",
      label: t("requirementsFormat.kindCustomLabel"),
      hint: t("requirementsFormat.kindCustomHint"),
    },
  ];
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>(format.kind);
  const [idPattern, setIdPattern] = useState(format.id_pattern ?? "");
  const [defDocs, setDefDocs] = useState(format.definition_docs.join(", "));
  const [defPattern, setDefPattern] = useState(format.def_pattern ?? "");
  const [refPattern, setRefPattern] = useState(format.ref_pattern ?? "");

  const mutation = useUpdateRequirementsFormat(projectId);
  const askAgent = useWorkspaceStore((state) => state.askAgent);

  // Hand the format off to the unified agent: it inspects the real IDs in the
  // sources, then proposes/previews/applies a format via the new
  // preview_requirements_format / set_requirements_format tools.
  const handleAskAi = () => {
    askAgent(buildRequirementsFormatPrompt(format.kind));
  };

  // When the resolved server format changes (after Apply/Reset), re-sync the
  // editable fields. Adjusting state during render is React's recommended
  // alternative to a setState-in-effect for prop-derived local state.
  const [syncedFormat, setSyncedFormat] = useState(format);
  if (syncedFormat !== format) {
    setSyncedFormat(format);
    setKind(format.kind);
    setIdPattern(format.id_pattern ?? "");
    setDefDocs(format.definition_docs.join(", "));
    setDefPattern(format.def_pattern ?? "");
    setRefPattern(format.ref_pattern ?? "");
  }

  const handleApply = () => {
    mutation.mutate({
      kind,
      id_pattern: kind === "id" ? idPattern.trim() || null : null,
      definition_docs:
        kind === "id"
          ? defDocs
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : [],
      def_pattern: kind === "custom" ? defPattern.trim() || null : null,
      ref_pattern: kind === "custom" ? refPattern.trim() || null : null,
    });
  };

  const currentLabel =
    kinds.find((k) => k.value === format.kind)?.label ?? format.kind;
  const activeHint = kinds.find((k) => k.value === kind)?.hint ?? "";

  return (
    <div className="card" style={{ marginTop: 16, overflow: "hidden" }}>
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
        }}
        className="flex items-center"
        style={{
          width: "100%",
          gap: 10,
          padding: "12px 16px",
          background: "transparent",
          border: 0,
          cursor: "pointer",
          color: "var(--fg-0)",
          textAlign: "left",
        }}
      >
        <SlidersHorizontal size={15} style={{ color: "var(--fg-3)" }} />
        <span style={{ fontSize: 13, fontWeight: 600 }}>
          {t("requirementsFormat.header")}
        </span>
        <span className="chip" style={{ fontSize: 10.5 }}>
          {currentLabel}
        </span>
        <span
          className="chip"
          style={{ fontSize: 10, color: "var(--fg-3)" }}
          title={
            overridden
              ? t("requirementsFormat.scopeProjectTitle")
              : t("requirementsFormat.scopeTemplateTitle")
          }
        >
          {overridden
            ? t("requirementsFormat.scopeProject")
            : t("requirementsFormat.scopeTemplate")}
        </span>
        <span style={{ flex: 1 }} />
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {open && (
        <div
          style={{
            padding: "4px 16px 16px",
            borderTop: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: 14,
          }}
        >
          <div
            style={{ display: "flex", gap: 6, marginTop: 12, flexWrap: "wrap" }}
          >
            {kinds.map((k) => (
              <button
                key={k.value}
                type="button"
                className={`btn xs ${kind === k.value ? "primary" : ""}`}
                onClick={() => {
                  setKind(k.value);
                }}
              >
                {k.label}
              </button>
            ))}
          </div>

          <p
            className="dim"
            style={{ margin: 0, fontSize: 11.5, lineHeight: 1.5 }}
          >
            {activeHint}
          </p>

          {kind === "id" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE}>
                  {t("requirementsFormat.idPatternLabel")}
                </label>
                <input
                  className="input mono"
                  style={{ width: "100%" }}
                  value={idPattern}
                  onChange={(e) => {
                    setIdPattern(e.target.value);
                  }}
                  placeholder="ТЗ-Ф-\d+"
                  spellCheck={false}
                />
              </div>
              <div>
                <label style={LABEL_STYLE}>
                  {t("requirementsFormat.sourceDocsLabel")}
                </label>
                <input
                  className="input mono"
                  style={{ width: "100%" }}
                  value={defDocs}
                  onChange={(e) => {
                    setDefDocs(e.target.value);
                  }}
                  placeholder="technical_specification"
                  spellCheck={false}
                />
              </div>
            </div>
          )}

          {kind === "custom" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={LABEL_STYLE}>
                  {t("requirementsFormat.defPatternLabel")}
                </label>
                <input
                  className="input mono"
                  style={{ width: "100%" }}
                  value={defPattern}
                  onChange={(e) => {
                    setDefPattern(e.target.value);
                  }}
                  placeholder="(?m)^(?P<id>ТЗ-Ф-\d+)\s*&\s*(?P<title>[^&]*)"
                  spellCheck={false}
                />
              </div>
              <div>
                <label style={LABEL_STYLE}>
                  {t("requirementsFormat.refPatternLabel")}
                </label>
                <input
                  className="input mono"
                  style={{ width: "100%" }}
                  value={refPattern}
                  onChange={(e) => {
                    setRefPattern(e.target.value);
                  }}
                  placeholder="(?P<ids>ТЗ-Ф-\d+)"
                  spellCheck={false}
                />
              </div>
            </div>
          )}

          {mutation.isError && (
            <div
              style={{ fontSize: 11.5, color: "var(--c-err)", lineHeight: 1.5 }}
            >
              {mutation.error instanceof Error
                ? mutation.error.message
                : t("requirementsFormat.saveError")}
            </div>
          )}

          <div className="flex items-center" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn primary xs"
              onClick={handleApply}
              disabled={mutation.isPending}
            >
              {mutation.isPending
                ? t("requirementsFormat.saving")
                : t("requirementsFormat.apply")}
            </button>
            {overridden && (
              <button
                type="button"
                className="btn xs ghost"
                onClick={() => {
                  mutation.mutate(null);
                }}
                disabled={mutation.isPending}
              >
                {t("requirementsFormat.resetToTemplate")}
              </button>
            )}
            <span style={{ flex: 1 }} />
            <button
              type="button"
              className="btn xs ghost"
              onClick={handleAskAi}
              title={t("requirementsFormat.askAiTitle")}
            >
              <Sparkles size={13} />
              {t("requirementsFormat.askAi")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
