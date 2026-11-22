import { useState } from "react";
import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import type { FormFieldDef } from "@entities/form";
import { FieldRenderer } from "@features/form-fill";
import { Badge, Button } from "@shared/ui";
import { KINDS } from "../../lib/fields";
import {
  asArray,
  asLocalized,
  asRecord,
  asString,
  asStrings,
  compactLocalized,
  deleteOp,
  has,
  insertOp,
  moveOp,
  optionalOps,
  pickLocalized,
  setOp,
  type Raw,
  ITEM_ID,
  type YamlPath,
} from "../../lib/raw";
import { useModelEditor } from "../../model/modelEditor";
import { slugify, uniqueSlug } from "@shared/lib/slug";
import { NewItemDialog } from "../NewItemDialog";
import {
  CheckInput,
  ChipToggles,
  CommitInput,
  FormBlock,
  FormRow,
  LocalizedInput,
  OrderButtons,
  SelectInput,
} from "../kit";

// Анкеты версии (`forms`): template-studio.md, 5.2, срез T11. Форма та же, что у
// полей, по схеме анкеты; образец поля рисует движок анкет (features/form-fill).

const MANIFEST = "version.yaml";
export const FORM_FIELD_TYPES = [
  "text",
  "textarea",
  "number",
  "bool",
  "select",
  "multiselect",
  "table",
  "markdown",
];
const FORM_ICONS = ["", "bot", "clipboard", "clipboard-check", "file", "pen"];
const WIDGETS = ["radio", "chips", "slider"];

const useLang = () => {
  const { i18n } = useTranslation();
  return i18n.language.startsWith("en") ? "en" : "ru";
};

/** Скаляр условия видимости строкой для поля ввода. */
const scalarText = (value: unknown): string =>
  typeof value === "string" ||
  typeof value === "number" ||
  typeof value === "boolean"
    ? String(value)
    : "";

const numberOrNull = (value: unknown): number | null =>
  typeof value === "number" ? value : null;

/** Определение поля для движка анкет из записи пака (как его читает лоадер). */
export const formFieldDef = (raw: Raw): FormFieldDef => {
  const localizedOrNull = (value: unknown) =>
    value === undefined ? null : asLocalized(value);
  const visible = asRecord(raw.visible_if);
  return {
    id: asString(raw.id),
    type: asString(raw.type) || "text",
    label: asLocalized(raw.label),
    help: localizedOrNull(raw.help),
    placeholder: localizedOrNull(raw.placeholder),
    required: raw.required === true,
    options: asArray(raw.options).map((o) => {
      const option = asRecord(o);
      return {
        id: asString(option.id),
        label: asLocalized(option.label),
        default: option.default === true,
      };
    }),
    columns: asArray(raw.columns).map((c) => {
      const column = asRecord(c);
      return { id: asString(column.id), label: asLocalized(column.label) };
    }),
    min: numberOrNull(raw.min),
    max: numberOrNull(raw.max),
    step: numberOrNull(raw.step),
    min_length: numberOrNull(raw.min_length),
    default: raw.default ?? null,
    widget: asString(raw.widget) || null,
    visible_if: has(visible, "field")
      ? { field: asString(visible.field), equals: visible.equals }
      : null,
    content: localizedOrNull(raw.content),
  };
};

const FieldPreview = ({ raw }: { raw: Raw }) => {
  const { t } = useTranslation("packForms");
  const lang = useLang();
  const [value, setValue] = useState<unknown>(raw.default ?? null);
  return (
    <div className="pf-sample" data-testid="form-field-sample">
      <div className="pf-sample-title">{t("forms.sample")}</div>
      <FieldRenderer
        field={formFieldDef(raw)}
        value={value}
        onChange={setValue}
        lang={lang}
      />
    </div>
  );
};

/** Пары «id и подпись» (варианты выбора, колонки таблицы): список целиком. */
const PairsEditor = ({
  label,
  items,
  withDefault,
  disabled,
  onChange,
  testId,
}: {
  label: string;
  items: Raw[];
  withDefault?: boolean | undefined;
  disabled: boolean;
  onChange: (next: Raw[]) => void;
  testId: string;
}) => {
  const { t } = useTranslation("packForms");
  const lang = useLang();
  const [draft, setDraft] = useState("");
  const ids = items.map((i) => asString(i.id));
  const add = () => {
    // Человек пишет подпись варианта, короткое имя для файла строится из неё само.
    const text = draft.trim();
    if (!text) return;
    const id = uniqueSlug(slugify(text) || "option", ids);
    onChange([...items, { id, label: { ru: text } }]);
    setDraft("");
  };
  return (
    <fieldset className="pf-options" data-testid={testId}>
      <legend className="pf-label">{label}</legend>
      <ol className="pf-list compact">
        {items.map((item, i) => {
          const id = asString(item.id);
          return (
            <li key={`${id}-${String(i)}`} className="pf-pair">
              <LocalizedInput
                label={t("forms.pairLabel", {
                  name: pickLocalized(item.label, lang, id),
                })}
                value={item.label}
                disabled={disabled}
                required
                onCommit={(next) => {
                  onChange(
                    items.map((it, j) =>
                      j === i ? { ...it, label: compactLocalized(next) } : it,
                    ),
                  );
                }}
              />
              {withDefault && (
                <CheckInput
                  label={t("forms.optionDefault")}
                  checked={item.default === true}
                  disabled={disabled}
                  onChange={(next) => {
                    onChange(
                      items.map((it, j) => {
                        if (j !== i) return it;
                        const copy = { ...it };
                        if (next) copy.default = true;
                        else delete copy.default;
                        return copy;
                      }),
                    );
                  }}
                />
              )}
              {!disabled && (
                <OrderButtons
                  index={i}
                  count={items.length}
                  label={id}
                  onMove={(to) => {
                    const next = [...items];
                    const [moved] = next.splice(i, 1);
                    if (moved) next.splice(to, 0, moved);
                    onChange(next);
                  }}
                  onDelete={() => {
                    onChange(items.filter((_, j) => j !== i));
                  }}
                />
              )}
            </li>
          );
        })}
      </ol>
      {!disabled && (
        <div className="pf-inline-add">
          <input
            className="input pf-input mono"
            value={draft}
            placeholder={t("forms.pairNew")}
            aria-label={t("forms.pairNew")}
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          <Button
            size="xs"
            variant="secondary"
            disabled={!ITEM_ID.test(draft.trim()) || ids.includes(draft.trim())}
            onClick={add}
          >
            <Plus size="0.6875rem" />
            {t("forms.pairAdd")}
          </Button>
        </div>
      )}
    </fieldset>
  );
};

const FormFieldCard = ({
  raw,
  path,
  siblings,
}: {
  raw: Raw;
  path: YamlPath;
  siblings: Raw[];
}) => {
  const { t } = useTranslation("packForms");
  const { edit, readOnly } = useModelEditor();
  const type = asString(raw.type) || "text";
  const write = (name: string, value: unknown) => {
    void edit(MANIFEST, optionalOps(raw, [...path, name], value));
  };
  const visible = asRecord(raw.visible_if);
  const others = siblings
    .map((s) => asString(s.id))
    .filter((id) => id && id !== asString(raw.id));
  const numberInput = (name: string) => (
    <FormRow key={name} label={t(`forms.${name}`)}>
      {(id) => (
        <CommitInput
          id={id}
          ariaLabel={t(`forms.${name}`)}
          value={typeof raw[name] === "number" ? String(raw[name]) : ""}
          disabled={readOnly}
          onCommit={(next) => {
            const trimmed = next.trim();
            const num = Number(trimmed);
            if (trimmed === "") write(name, "");
            else if (Number.isFinite(num)) write(name, num);
          }}
        />
      )}
    </FormRow>
  );

  return (
    <div
      className="pf-card"
      data-testid={`pf-form-field-card-${asString(raw.id)}`}
    >
      <div className="pf-card-main">
        <div className="pf-grid">
          <FormRow label={t("forms.fieldType")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("forms.fieldType")}
                value={type}
                disabled={readOnly}
                testId="pf-form-field-type"
                options={FORM_FIELD_TYPES.map((v) => ({
                  value: v,
                  label: t(`forms.types.${v}`),
                }))}
                onChange={(next) => {
                  void edit(MANIFEST, [setOp([...path, "type"], next)]);
                }}
              />
            )}
          </FormRow>
          {type !== "markdown" && (
            <CheckInput
              label={t("forms.required")}
              checked={raw.required === true}
              disabled={readOnly}
              onChange={(next) => {
                write("required", next ? true : "");
              }}
            />
          )}
          {(type === "select" ||
            type === "multiselect" ||
            type === "number") && (
            <FormRow label={t("forms.widget")} hint={t("forms.widgetHint")}>
              {(id) => (
                <>
                  <CommitInput
                    id={id}
                    ariaLabel={t("forms.widget")}
                    value={asString(raw.widget)}
                    disabled={readOnly}
                    list={`${id}-widgets`}
                    onCommit={(next) => {
                      write("widget", next.trim());
                    }}
                  />
                  <datalist id={`${id}-widgets`}>
                    {WIDGETS.map((w) => (
                      <option key={w} value={w} />
                    ))}
                  </datalist>
                </>
              )}
            </FormRow>
          )}
        </div>
        {type === "markdown" ? (
          <LocalizedInput
            label={t("forms.content")}
            value={raw.content}
            disabled={readOnly}
            multiline
            required
            onCommit={(next) => {
              write("content", compactLocalized(next));
            }}
          />
        ) : (
          <>
            <LocalizedInput
              label={t("forms.fieldLabel")}
              value={raw.label}
              disabled={readOnly}
              required
              testId="pf-form-field-label"
              onCommit={(next) => {
                write("label", compactLocalized(next));
              }}
            />
            <LocalizedInput
              label={t("forms.help")}
              value={raw.help}
              disabled={readOnly}
              multiline
              onCommit={(next) => {
                write("help", compactLocalized(next));
              }}
            />
            {(type === "text" || type === "textarea") && (
              <LocalizedInput
                label={t("forms.placeholder")}
                value={raw.placeholder}
                disabled={readOnly}
                onCommit={(next) => {
                  write("placeholder", compactLocalized(next));
                }}
              />
            )}
          </>
        )}
        <div className="pf-grid">
          {type === "number" && ["min", "max", "step"].map(numberInput)}
          {(type === "text" || type === "textarea") &&
            numberInput("min_length")}
        </div>
        {(type === "select" || type === "multiselect") && (
          <PairsEditor
            label={t("forms.options")}
            items={asArray(raw.options).map(asRecord)}
            withDefault
            disabled={readOnly}
            testId="pf-form-options"
            onChange={(next) => {
              write("options", next);
            }}
          />
        )}
        {type === "table" && (
          <PairsEditor
            label={t("forms.columns")}
            items={asArray(raw.columns).map(asRecord)}
            disabled={readOnly}
            testId="pf-form-columns"
            onChange={(next) => {
              write("columns", next);
            }}
          />
        )}
        <div className="pf-grid">
          <FormRow label={t("forms.visibleIf")} hint={t("forms.visibleIfHint")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("forms.visibleIf")}
                value={asString(visible.field)}
                disabled={readOnly}
                options={[
                  { value: "", label: t("forms.always") },
                  ...others.map((o) => ({ value: o, label: o })),
                ]}
                onChange={(next) => {
                  write(
                    "visible_if",
                    next ? { field: next, equals: visible.equals ?? true } : "",
                  );
                }}
              />
            )}
          </FormRow>
          {has(visible, "field") && (
            <FormRow label={t("forms.equals")}>
              {(id) => (
                <CommitInput
                  id={id}
                  ariaLabel={t("forms.equals")}
                  value={scalarText(visible.equals)}
                  disabled={readOnly}
                  onCommit={(next) => {
                    const equals =
                      next === "true" ? true : next === "false" ? false : next;
                    write("visible_if", {
                      field: asString(visible.field),
                      equals,
                    });
                  }}
                />
              )}
            </FormRow>
          )}
        </div>
      </div>
      <aside className="pf-card-side">
        <FieldPreview raw={raw} />
      </aside>
    </div>
  );
};

const SectionEditor = ({
  section,
  path,
  index,
  count,
}: {
  section: Raw;
  path: YamlPath;
  index: number;
  count: number;
}) => {
  const { t } = useTranslation("packForms");
  const { edit, readOnly, busy } = useModelEditor();
  const lang = useLang();
  const fields = asArray(section.fields).map(asRecord);
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newType, setNewType] = useState("text");
  const sectionId = asString(section.id);
  const sectionsPath = path.slice(0, -1);
  return (
    <li
      className="pf-item pf-subitem"
      data-testid={`pf-section-${sectionId}`}
      data-pf-at={`/${path.join("/")}`}
    >
      <div className="pf-item-head">
        <span className="pf-item-title" title={sectionId}>
          {pickLocalized(section.title, lang, sectionId)}
        </span>
        <span className="pf-item-sub">
          {t("forms.fieldsCount", { count: fields.length })}
        </span>
        {!readOnly && (
          <OrderButtons
            index={index}
            count={count}
            label={pickLocalized(section.title, lang, sectionId)}
            disabled={busy}
            onMove={(to) => {
              void edit(MANIFEST, [moveOp(sectionsPath, index, to)]);
            }}
            onDelete={() => {
              void edit(MANIFEST, [deleteOp(path)]);
            }}
          />
        )}
      </div>
      <LocalizedInput
        label={t("forms.sectionTitle")}
        value={section.title}
        disabled={readOnly}
        onCommit={(next) => {
          void edit(
            MANIFEST,
            optionalOps(section, [...path, "title"], compactLocalized(next)),
          );
        }}
      />
      <ul className="pf-list">
        {fields.map((field, i) => {
          const id = asString(field.id);
          const expanded = open === id;
          return (
            <li
              key={`${id}-${String(i)}`}
              className={clsx("pf-item", expanded && "open")}
              data-pf-at={`/${[...path, "fields", i].join("/")}`}
            >
              <div className="pf-item-head">
                <button
                  type="button"
                  className="pf-item-toggle"
                  aria-expanded={expanded}
                  data-testid={`pf-form-field-${id}`}
                  onClick={() => {
                    setOpen(expanded ? null : id);
                  }}
                >
                  {expanded ? (
                    <ChevronDown size="0.75rem" />
                  ) : (
                    <ChevronRight size="0.75rem" />
                  )}
                  <span className="pf-item-title truncate" title={id}>
                    {pickLocalized(field.label, lang, id)}
                  </span>
                  <Badge variant="subtle">
                    {t(`forms.types.${asString(field.type) || "text"}`, {
                      defaultValue: asString(field.type),
                    })}
                  </Badge>
                </button>
                {!readOnly && (
                  <OrderButtons
                    index={i}
                    count={fields.length}
                    label={pickLocalized(field.label, lang, id)}
                    disabled={busy}
                    onMove={(to) => {
                      void edit(MANIFEST, [moveOp([...path, "fields"], i, to)]);
                    }}
                    onDelete={() => {
                      void edit(MANIFEST, [deleteOp([...path, "fields", i])]);
                    }}
                  />
                )}
              </div>
              {expanded && (
                <FormFieldCard
                  raw={field}
                  path={[...path, "fields", i]}
                  siblings={fields}
                />
              )}
            </li>
          );
        })}
      </ul>
      {!readOnly && (
        <Button
          size="xs"
          variant="ghost"
          onClick={() => {
            setAdding(true);
          }}
          data-testid={`pf-form-field-add-${sectionId}`}
        >
          <Plus size="0.6875rem" />
          {t("forms.fieldAdd")}
        </Button>
      )}
      <NewItemDialog
        isOpen={adding}
        title={t("forms.fieldAddTitle")}
        idLabel={t("forms.fieldId")}
        taken={fields.map((f) => asString(f.id))}
        pattern="id"
        onClose={() => {
          setAdding(false);
        }}
        extra={
          <FormRow label={t("forms.fieldType")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("forms.fieldType")}
                value={newType}
                options={FORM_FIELD_TYPES.map((v) => ({
                  value: v,
                  label: t(`forms.types.${v}`),
                }))}
                onChange={setNewType}
              />
            )}
          </FormRow>
        }
        onCreate={async (id, label) => {
          const value: Raw =
            newType === "markdown"
              ? { id, type: newType, content: compactLocalized(label) }
              : { id, type: newType, label: compactLocalized(label) };
          const ok = await edit(MANIFEST, [
            Array.isArray(section.fields)
              ? insertOp([...path, "fields"], fields.length, value)
              : setOp([...path, "fields"], [value]),
          ]);
          if (ok) {
            setAdding(false);
            setOpen(id);
          }
        }}
      />
    </li>
  );
};

const FormCard = ({ form, index }: { form: Raw; index: number }) => {
  const { t } = useTranslation("packForms");
  const { edit, readOnly } = useModelEditor();
  const path: YamlPath = ["forms", index];
  const write = (name: string, value: unknown) => {
    void edit(MANIFEST, optionalOps(form, [...path, name], value));
  };
  const output = asRecord(form.output);
  const writeOutput = (name: string, value: string) => {
    const next: Raw = Object.fromEntries(
      Object.entries({ ...output, [name]: value }).filter(([, v]) => v !== ""),
    );
    void edit(
      MANIFEST,
      optionalOps(form, [...path, "output"], next.template ? next : ""),
    );
  };
  const sections = asArray(form.sections).map(asRecord);
  const kinds = asStrings(form.supported_kinds);
  const [adding, setAdding] = useState(false);
  return (
    <div
      className="pf-card single"
      data-testid={`pf-form-card-${asString(form.id)}`}
    >
      <div className="pf-card-main">
        <LocalizedInput
          label={t("forms.formTitle")}
          value={form.title}
          disabled={readOnly}
          required
          testId="pf-form-title"
          onCommit={(next) => {
            write("title", compactLocalized(next));
          }}
        />
        <div className="pf-grid">
          <FormRow label={t("forms.icon")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("forms.icon")}
                value={asString(form.icon)}
                disabled={readOnly}
                options={FORM_ICONS.map((v) => ({
                  value: v,
                  label: v || t("forms.iconDefault"),
                }))}
                onChange={(next) => {
                  write("icon", next);
                }}
              />
            )}
          </FormRow>
          <CheckInput
            label={t("forms.requiredForPack")}
            hint={t("forms.requiredForPackHint")}
            checked={form.required_for_pack === true}
            disabled={readOnly}
            testId="pf-form-required-for-pack"
            onChange={(next) => {
              write("required_for_pack", next ? true : "");
            }}
          />
          <CheckInput
            label={t("forms.perAuthor")}
            hint={t("forms.perAuthorHint")}
            checked={form.per_author === true}
            disabled={readOnly}
            onChange={(next) => {
              write("per_author", next ? true : "");
            }}
          />
        </div>
        <ChipToggles
          label={t("fields.kinds")}
          options={KINDS.map((k) => ({
            value: k,
            label: t(`kinds.${k}`),
          }))}
          value={kinds.length ? kinds : KINDS}
          disabled={readOnly}
          onChange={(next) => {
            write("supported_kinds", next.length === KINDS.length ? [] : next);
          }}
        />
        <fieldset className="pf-group">
          <legend className="pf-label">{t("forms.output")}</legend>
          <div className="pf-grid">
            <FormRow
              label={t("forms.outputTemplate")}
              hint={t("forms.outputTemplateHint")}
            >
              {(id) => (
                <CommitInput
                  id={id}
                  mono
                  ariaLabel={t("forms.outputTemplate")}
                  value={asString(output.template)}
                  disabled={readOnly}
                  onCommit={(next) => {
                    writeOutput("template", next.trim());
                  }}
                />
              )}
            </FormRow>
            <FormRow label={t("forms.outputName")}>
              {(id) => (
                <CommitInput
                  id={id}
                  ariaLabel={t("forms.outputName")}
                  value={asString(output.output_name)}
                  disabled={readOnly || !output.template}
                  onCommit={(next) => {
                    writeOutput("output_name", next.trim());
                  }}
                />
              )}
            </FormRow>
            <FormRow label={t("forms.outputFormat")}>
              {(id) => (
                <CommitInput
                  id={id}
                  ariaLabel={t("forms.outputFormat")}
                  value={asString(output.format)}
                  disabled={readOnly || !output.template}
                  onCommit={(next) => {
                    writeOutput("format", next.trim());
                  }}
                />
              )}
            </FormRow>
          </div>
        </fieldset>
        <div className="pf-subhead">
          <span className="pf-label">{t("forms.sections")}</span>
          {!readOnly && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => {
                setAdding(true);
              }}
              data-testid="pf-section-add"
            >
              <Plus size="0.6875rem" />
              {t("forms.sectionAdd")}
            </Button>
          )}
        </div>
        <ol className="pf-list">
          {sections.map((section, i) => (
            <SectionEditor
              key={`${asString(section.id)}-${String(i)}`}
              section={section}
              path={[...path, "sections", i]}
              index={i}
              count={sections.length}
            />
          ))}
        </ol>
      </div>
      <NewItemDialog
        isOpen={adding}
        title={t("forms.sectionAddTitle")}
        idLabel={t("forms.sectionId")}
        taken={sections.map((s) => asString(s.id))}
        pattern="id"
        onClose={() => {
          setAdding(false);
        }}
        onCreate={async (id, label) => {
          const value = { id, title: compactLocalized(label), fields: [] };
          const ok = await edit(MANIFEST, [
            Array.isArray(form.sections)
              ? insertOp([...path, "sections"], sections.length, value)
              : setOp([...path, "sections"], [value]),
          ]);
          if (ok) setAdding(false);
        }}
      />
    </div>
  );
};

/** Анкеты версии: список, карточка анкеты, секции и поля с образцом (5.2; T11). */
export const FormsSection = () => {
  const { t } = useTranslation("packForms");
  const { model, edit, readOnly, busy } = useModelEditor();
  const lang = useLang();
  const data = asRecord(model.manifest.data);
  const forms = asArray(data.forms).map(asRecord);
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  return (
    <div className="pf-section" data-testid="pf-forms">
      <FormBlock
        title={t("forms.title")}
        lead={t("forms.lead")}
        actions={
          !readOnly && (
            <Button
              size="xs"
              variant="secondary"
              onClick={() => {
                setAdding(true);
              }}
              data-testid="pf-form-add"
            >
              <Plus size="0.6875rem" />
              {t("forms.add")}
            </Button>
          )
        }
      >
        {forms.length === 0 && <p className="pf-empty">{t("forms.empty")}</p>}
        <ul className="pf-list">
          {forms.map((form, i) => {
            const id = asString(form.id);
            const expanded = open === id;
            return (
              <li
                key={`${id}-${String(i)}`}
                className={clsx("pf-item", expanded && "open")}
                data-pf-at={`/forms/${String(i)}`}
              >
                <div className="pf-item-head">
                  <button
                    type="button"
                    className="pf-item-toggle"
                    aria-expanded={expanded}
                    data-testid={`pf-form-${id}`}
                    onClick={() => {
                      setOpen(expanded ? null : id);
                    }}
                  >
                    {expanded ? (
                      <ChevronDown size="0.75rem" />
                    ) : (
                      <ChevronRight size="0.75rem" />
                    )}
                    <span className="pf-item-title truncate" title={id}>
                      {pickLocalized(form.title, lang, id)}
                    </span>
                    {form.required_for_pack === true && (
                      <Badge variant="info">{t("forms.inPack")}</Badge>
                    )}
                  </button>
                  {!readOnly && (
                    <OrderButtons
                      index={i}
                      count={forms.length}
                      label={pickLocalized(form.title, lang, id)}
                      disabled={busy}
                      onMove={(to) => {
                        void edit(MANIFEST, [moveOp(["forms"], i, to)]);
                      }}
                      onDelete={() => {
                        void edit(MANIFEST, [deleteOp(["forms", i])]);
                      }}
                    />
                  )}
                </div>
                {expanded && <FormCard form={form} index={i} />}
              </li>
            );
          })}
        </ul>
      </FormBlock>
      <NewItemDialog
        isOpen={adding}
        title={t("forms.addTitle")}
        idLabel={t("forms.formId")}
        taken={forms.map((f) => asString(f.id))}
        pattern="id"
        onClose={() => {
          setAdding(false);
        }}
        onCreate={async (id, label) => {
          const value = {
            id,
            title: compactLocalized(label),
            schema_version: 1,
            sections: [
              { id: "main", title: { ru: "Основное", en: "Main" }, fields: [] },
            ],
          };
          const ok = await edit(MANIFEST, [
            Array.isArray(data.forms)
              ? insertOp(["forms"], forms.length, value)
              : setOp(["forms"], [value]),
          ]);
          if (ok) {
            setAdding(false);
            setOpen(id);
          }
        }}
      />
    </div>
  );
};
