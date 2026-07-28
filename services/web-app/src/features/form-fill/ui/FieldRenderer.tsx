import type { ReactElement } from "react";
import { useTranslation } from "react-i18next";
import type { FormFieldDef } from "@entities/form";
import { loc } from "../lib/forms";
import { TableField } from "./TableField";

export type FieldControlProps = {
  field: FormFieldDef;
  value: unknown;
  onChange: (value: unknown) => void;
  lang: string;
};

const asString = (v: unknown): string => (typeof v === "string" ? v : "");
const asStringArray = (v: unknown): string[] =>
  Array.isArray(v) ? (v as string[]) : [];
const asRows = (v: unknown): Record<string, string>[] =>
  Array.isArray(v) ? (v as Record<string, string>[]) : [];

const BoolControl = ({ field, value, onChange, lang }: FieldControlProps) => (
  <label className="flex items-center cursor-pointer" style={{ gap: 10 }}>
    <input
      type="checkbox"
      checked={value === true}
      onChange={(e) => {
        onChange(e.target.checked);
      }}
      style={{ accentColor: "var(--accent)" }}
    />
    <span style={{ fontSize: 12.5 }}>{loc(field.label, lang)}</span>
  </label>
);

const TextControl = ({ field, value, onChange, lang }: FieldControlProps) => (
  <input
    type="text"
    className="input"
    value={asString(value)}
    placeholder={loc(field.placeholder, lang)}
    onChange={(e) => {
      onChange(e.target.value);
    }}
  />
);

const TextareaControl = ({
  field,
  value,
  onChange,
  lang,
}: FieldControlProps) => {
  const { t } = useTranslation("formFill");
  const text = asString(value);
  return (
    <>
      <textarea
        className="textarea"
        rows={6}
        value={text}
        placeholder={loc(field.placeholder, lang)}
        onChange={(e) => {
          onChange(e.target.value);
        }}
      />
      {field.min_length != null && (
        <span className="hint">
          {t("field.charCount", {
            count: text.trim().length,
            min: field.min_length,
          })}
        </span>
      )}
    </>
  );
};

const NumberControl = ({ field, value, onChange }: FieldControlProps) => {
  const num = typeof value === "number" ? value : (field.min ?? 0);
  if (field.widget === "slider") {
    return (
      <div className="flex items-center gap-3">
        <input
          type="range"
          min={field.min ?? 0}
          max={field.max ?? 100}
          step={field.step ?? 1}
          value={num}
          onChange={(e) => {
            onChange(Number(e.target.value));
          }}
          style={{ flex: 1, accentColor: "var(--accent)" }}
        />
        <span
          className="mono"
          style={{
            fontSize: 14,
            fontWeight: 600,
            color: "var(--accent)",
            width: 52,
            textAlign: "right",
          }}
        >
          {num}
        </span>
      </div>
    );
  }
  return (
    <input
      type="number"
      className="input"
      min={field.min ?? undefined}
      max={field.max ?? undefined}
      step={field.step ?? undefined}
      value={num}
      onChange={(e) => {
        onChange(e.target.value === "" ? null : Number(e.target.value));
      }}
    />
  );
};

const Chip = ({
  selected,
  label,
  onClick,
}: {
  selected: boolean;
  label: string;
  onClick: () => void;
}) => (
  <button
    type="button"
    onClick={onClick}
    className="flex items-center cursor-pointer"
    style={{
      padding: "7px 12px",
      borderRadius: "var(--r-2)",
      fontSize: 12.5,
      fontWeight: selected ? 600 : 400,
      background: selected ? "var(--accent-soft)" : "var(--bg-2)",
      border:
        "1px solid " + (selected ? "var(--accent-line)" : "var(--border)"),
      color: selected ? "var(--accent)" : "var(--fg-1)",
      transition: "background 0.12s",
    }}
  >
    {label}
  </button>
);

const SelectControl = ({ field, value, onChange, lang }: FieldControlProps) => (
  <div className="flex flex-wrap" style={{ gap: 8 }}>
    {field.options.map((opt) => (
      <Chip
        key={opt.id}
        selected={value === opt.id}
        label={loc(opt.label, lang)}
        onClick={() => {
          onChange(opt.id);
        }}
      />
    ))}
  </div>
);

const MultiSelectControl = ({
  field,
  value,
  onChange,
  lang,
}: FieldControlProps) => {
  const selected = asStringArray(value);
  const toggle = (id: string) => {
    onChange(
      selected.includes(id)
        ? selected.filter((s) => s !== id)
        : [...selected, id],
    );
  };
  return (
    <div className="flex flex-wrap" style={{ gap: 8 }}>
      {field.options.map((opt) => (
        <Chip
          key={opt.id}
          selected={selected.includes(opt.id)}
          label={loc(opt.label, lang)}
          onClick={() => {
            toggle(opt.id);
          }}
        />
      ))}
    </div>
  );
};

const TableControl = ({ field, value, onChange, lang }: FieldControlProps) => (
  <TableField
    columns={field.columns}
    rows={asRows(value)}
    lang={lang}
    onChange={onChange}
  />
);

const CONTROLS: Record<string, (props: FieldControlProps) => ReactElement> = {
  bool: BoolControl,
  text: TextControl,
  textarea: TextareaControl,
  number: NumberControl,
  select: SelectControl,
  multiselect: MultiSelectControl,
  table: TableControl,
};

const FieldShell = ({
  field,
  lang,
  children,
}: {
  field: FormFieldDef;
  lang: string;
  children: ReactElement;
}) => (
  <div className="flex flex-col" style={{ gap: 8 }}>
    {/* bool renders its own inline label */}
    {field.type !== "bool" && (
      <label style={{ fontSize: 12.5, fontWeight: 500 }}>
        {loc(field.label, lang)}
        {field.required && <span style={{ color: "var(--c-err)" }}> *</span>}
      </label>
    )}
    {children}
    {field.help && (
      <span className="dim" style={{ fontSize: 11.5 }}>
        {loc(field.help, lang)}
      </span>
    )}
  </div>
);

const MarkdownBlock = ({
  field,
  lang,
}: {
  field: FormFieldDef;
  lang: string;
}) => (
  <div
    className="dim"
    style={{ fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap" }}
  >
    {loc(field.content, lang)}
  </div>
);

export const FieldRenderer = ({
  field,
  value,
  onChange,
  lang,
}: FieldControlProps) => {
  if (field.type === "markdown") {
    return <MarkdownBlock field={field} lang={lang} />;
  }
  const Control = CONTROLS[field.type] ?? TextControl;
  return (
    <FieldShell field={field} lang={lang}>
      <Control field={field} value={value} onChange={onChange} lang={lang} />
    </FieldShell>
  );
};
