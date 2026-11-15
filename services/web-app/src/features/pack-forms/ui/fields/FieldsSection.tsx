import { useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  PenLine,
  Plus,
  Trash2,
} from "lucide-react";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";
import { resolveMetaAuto } from "@shared/lib/metaFields";
import { Badge, Button, Modal } from "@shared/ui";
import {
  FIELD_SCOPES,
  FIELD_TYPES,
  GROUP_SECTIONS,
  KINDS,
  PERSON_KEYS,
  REQUIRED_AT,
  documentName,
  fieldKeyProblem,
  fieldsOf,
  groupsOf,
  usageOf,
  type FieldEntry,
  type GroupEntry,
} from "../../lib/fields";
import {
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
} from "../../lib/raw";
import { useModelEditor } from "../../model/modelEditor";
import {
  ChipToggles,
  CommitInput,
  FormBlock,
  FormRow,
  LocalizedInput,
  OrderButtons,
  SelectInput,
} from "../kit";
import { NewItemDialog } from "../NewItemDialog";
import { FieldSample } from "./FieldSample";

const MANIFEST = "version.yaml";

const useLang = () => {
  const { i18n } = useTranslation();
  return i18n.language.startsWith("en") ? "en" : "ru";
};

// ── группы ──

const GroupsBlock = ({
  groups,
  fields,
}: {
  groups: GroupEntry[];
  fields: FieldEntry[];
}) => {
  const { t } = useTranslation("packForms");
  const { edit, readOnly, busy, model } = useModelEditor();
  const [adding, setAdding] = useState(false);
  const lang = useLang();
  const hasList = Array.isArray(asRecord(model.manifest.data).meta_groups);
  return (
    <FormBlock
      title={t("groups.title")}
      lead={t("groups.lead")}
      testId="pf-groups"
      actions={
        !readOnly && (
          <Button
            size="xs"
            variant="secondary"
            onClick={() => {
              setAdding(true);
            }}
            data-testid="pf-group-add"
          >
            <Plus size="0.6875rem" />
            {t("groups.add")}
          </Button>
        )
      }
    >
      {groups.length === 0 && <p className="pf-empty">{t("groups.empty")}</p>}
      <ol className="pf-list">
        {groups.map((group, i) => {
          const used = fields.filter(
            (f) => asString(f.spec.group) === group.id,
          );
          return (
            <li
              key={group.id}
              className="pf-item"
              data-testid={`pf-group-${group.id}`}
            >
              <div className="pf-item-head">
                <span className="mono pf-id">{group.id}</span>
                <span className="pf-item-sub">
                  {t("groups.count", { count: used.length })}
                </span>
                {!readOnly && (
                  <OrderButtons
                    index={i}
                    count={groups.length}
                    label={pickLocalized(group.raw.label, lang, group.id)}
                    disabled={busy}
                    onMove={(to) => {
                      void edit(MANIFEST, [
                        moveOp(["meta_groups"], group.index, to),
                      ]);
                    }}
                    deleteDisabledReason={
                      used.length > 0 ? t("groups.inUse") : undefined
                    }
                    onDelete={() => {
                      void edit(MANIFEST, [
                        deleteOp(["meta_groups", group.index]),
                      ]);
                    }}
                  />
                )}
              </div>
              <div className="pf-grid">
                <LocalizedInput
                  label={t("groups.label")}
                  value={group.raw.label}
                  disabled={readOnly}
                  required
                  testId={`pf-group-label-${group.id}`}
                  onCommit={(next) => {
                    void edit(
                      MANIFEST,
                      optionalOps(
                        group.raw,
                        ["meta_groups", group.index, "label"],
                        compactLocalized(next),
                      ),
                    );
                  }}
                />
                <FormRow
                  label={t("groups.section")}
                  hint={t("groups.sectionHint")}
                >
                  {(id) => (
                    <SelectInput
                      id={id}
                      ariaLabel={t("groups.section")}
                      value={asString(group.raw.section) || "meta"}
                      disabled={readOnly}
                      options={GROUP_SECTIONS.map((s) => ({
                        value: s,
                        label: t(`groups.sections.${s}`),
                      }))}
                      onChange={(next) => {
                        void edit(
                          MANIFEST,
                          optionalOps(
                            group.raw,
                            ["meta_groups", group.index, "section"],
                            next === "meta" ? "" : next,
                          ),
                        );
                      }}
                    />
                  )}
                </FormRow>
              </div>
            </li>
          );
        })}
      </ol>
      <NewItemDialog
        isOpen={adding}
        title={t("groups.addTitle")}
        idLabel={t("groups.id")}
        taken={groups.map((g) => g.id)}
        onClose={() => {
          setAdding(false);
        }}
        onCreate={async (id, label) => {
          const value = { id, label: compactLocalized(label) };
          const ok = await edit(MANIFEST, [
            hasList
              ? insertOp(["meta_groups"], groups.length, value)
              : setOp(["meta_groups"], [value]),
          ]);
          if (ok) setAdding(false);
        }}
      />
    </FormBlock>
  );
};

// ── поле ──

const FieldUsageList = ({
  fieldKey,
  spec,
}: {
  fieldKey: string;
  spec: Raw;
}) => {
  const { t } = useTranslation("packForms");
  const { model } = useModelEditor();
  const lang = useLang();
  const usage = usageOf(model, fieldKey);
  const quiet = usage.length === 0;
  return (
    <div className="pf-usage" data-testid="field-usage">
      <div className="pf-sample-title">{t("fields.usageTitle")}</div>
      {quiet ? (
        <p className="pf-warn" data-testid="field-unused">
          <AlertTriangle size="0.75rem" aria-hidden="true" />
          {asString(spec.required_at) === "create"
            ? t("fields.unusedRequired")
            : t("fields.unused")}
        </p>
      ) : (
        <ul className="pf-usage-list">
          {usage.map((u) => (
            <li key={u.document}>
              <span>{documentName(model, u.document, lang)}</span>
              <span className="pf-usage-how">
                {u.macros.map((m) => (
                  <code key={m}>\{m}</code>
                ))}
                {u.direct && <span>{t("fields.usageDirect")}</span>}
                {u.whole && <span>{t("fields.usageWhole")}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const FieldCard = ({
  field,
  groups,
  onRename,
  onDelete,
}: {
  field: FieldEntry;
  groups: GroupEntry[];
  onRename: () => void;
  onDelete: () => void;
}) => {
  const { t } = useTranslation("packForms");
  const { edit, readOnly } = useModelEditor();
  const lang = useLang();
  const { key, spec } = field;
  const base = ["meta_fields", key];
  const type = asString(spec.type) || "string";
  const options = asStrings(spec.options);
  const kinds = asStrings(spec.supported_kinds);
  const write = (name: string, value: unknown) => {
    void edit(MANIFEST, optionalOps(spec, [...base, name], value));
  };
  const auto = asString(spec.auto);
  const today = resolveMetaAuto(auto || null);

  return (
    <div className="pf-card" data-testid={`pf-field-card-${key}`}>
      <div className="pf-card-main">
        <div className="pf-grid">
          <FormRow label={t("fields.type")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("fields.type")}
                value={type}
                disabled={readOnly}
                testId="pf-field-type"
                options={FIELD_TYPES.map((v) => ({
                  value: v,
                  label: t(`fields.types.${v}`),
                }))}
                onChange={(next) => {
                  void edit(MANIFEST, [setOp([...base, "type"], next)]);
                }}
              />
            )}
          </FormRow>
          <FormRow label={t("fields.group")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("fields.group")}
                value={asString(spec.group)}
                disabled={readOnly}
                testId="pf-field-group"
                options={[
                  { value: "", label: t("fields.noGroup") },
                  ...groups.map((g) => ({
                    value: g.id,
                    label: pickLocalized(g.raw.label, lang, g.id),
                  })),
                ]}
                onChange={(next) => {
                  write("group", next);
                }}
              />
            )}
          </FormRow>
          <FormRow label={t("fields.requiredAt")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("fields.requiredAt")}
                value={asString(spec.required_at) || "create"}
                disabled={readOnly}
                testId="pf-field-required"
                options={REQUIRED_AT.map((v) => ({
                  value: v,
                  label: t(`fields.required.${v}`),
                }))}
                onChange={(next) => {
                  void edit(MANIFEST, [setOp([...base, "required_at"], next)]);
                }}
              />
            )}
          </FormRow>
          <FormRow label={t("fields.scope")} hint={t("fields.scopeHint")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("fields.scope")}
                value={asString(spec.scope) || "project"}
                disabled={readOnly}
                options={FIELD_SCOPES.map((v) => ({
                  value: v,
                  label: t(`fields.scopes.${v}`),
                }))}
                onChange={(next) => {
                  write("scope", next === "project" ? "" : next);
                }}
              />
            )}
          </FormRow>
        </div>
        <LocalizedInput
          label={t("fields.label")}
          value={spec.label}
          disabled={readOnly}
          required
          testId="pf-field-label"
          onCommit={(next) => {
            write("label", compactLocalized(next));
          }}
        />
        <LocalizedInput
          label={t("fields.help")}
          value={spec.help}
          disabled={readOnly}
          multiline
          testId="pf-field-help"
          onCommit={(next) => {
            write("help", compactLocalized(next));
          }}
        />
        <div className="pf-grid">
          {type !== "bool" && type !== "person" && (
            <FormRow label={t("fields.placeholder")}>
              {(id) => (
                <CommitInput
                  id={id}
                  ariaLabel={t("fields.placeholder")}
                  value={asString(spec.placeholder)}
                  disabled={readOnly}
                  testId="pf-field-placeholder"
                  onCommit={(next) => {
                    write("placeholder", next.trim());
                  }}
                />
              )}
            </FormRow>
          )}
          {type !== "person" && (
            <FormRow label={t("fields.default")}>
              {(id) =>
                type === "bool" ? (
                  <SelectInput
                    id={id}
                    ariaLabel={t("fields.default")}
                    value={
                      spec.default === true
                        ? "true"
                        : spec.default === false
                          ? "false"
                          : ""
                    }
                    disabled={readOnly}
                    options={[
                      { value: "", label: "—" },
                      { value: "true", label: t("fields.yes") },
                      { value: "false", label: t("fields.no") },
                    ]}
                    onChange={(next) => {
                      write("default", next === "" ? "" : next === "true");
                    }}
                  />
                ) : type === "select" ? (
                  <SelectInput
                    id={id}
                    ariaLabel={t("fields.default")}
                    value={asString(spec.default)}
                    disabled={readOnly}
                    options={[
                      { value: "", label: "—" },
                      ...options.map((o) => ({ value: o, label: o })),
                    ]}
                    onChange={(next) => {
                      write("default", next);
                    }}
                  />
                ) : (
                  <CommitInput
                    id={id}
                    ariaLabel={t("fields.default")}
                    value={asString(spec.default)}
                    disabled={readOnly}
                    testId="pf-field-default"
                    onCommit={(next) => {
                      write("default", next);
                    }}
                  />
                )
              }
            </FormRow>
          )}
          {(type === "string" || type === "select") && (
            <FormRow
              label={t("fields.auto")}
              hint={
                auto && today
                  ? t("fields.autoToday", { value: today })
                  : t("fields.autoHint")
              }
            >
              {(id) => (
                <SelectInput
                  id={id}
                  ariaLabel={t("fields.auto")}
                  value={auto}
                  disabled={readOnly}
                  options={[
                    { value: "", label: t("fields.autoNone") },
                    {
                      value: "academic_year",
                      label: t("fields.autoAcademicYear"),
                    },
                  ]}
                  onChange={(next) => {
                    write("auto", next);
                  }}
                />
              )}
            </FormRow>
          )}
        </div>
        {(type === "select" || type === "font" || has(spec, "options")) && (
          <OptionsEditor
            options={options}
            disabled={readOnly}
            onChange={(next) => {
              write("options", next);
            }}
          />
        )}
        <ChipToggles
          label={t("fields.kinds")}
          hint={t("fields.kindsHint")}
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
        {!readOnly && (
          <div className="pf-card-actions">
            <Button
              size="xs"
              variant="secondary"
              disabled={PERSON_KEYS.includes(key)}
              title={
                PERSON_KEYS.includes(key) ? t("fields.renamePerson") : undefined
              }
              onClick={onRename}
              data-testid="pf-field-rename"
            >
              <PenLine size="0.6875rem" />
              {t("fields.rename")}
            </Button>
            <Button
              size="xs"
              variant="ghost"
              onClick={onDelete}
              data-testid="pf-field-delete"
            >
              <Trash2 size="0.6875rem" />
              {t("fields.delete")}
            </Button>
          </div>
        )}
      </div>
      <aside className="pf-card-side">
        <FieldSample fieldKey={key} spec={spec} />
        <FieldUsageList fieldKey={key} spec={spec} />
      </aside>
    </div>
  );
};

/** Варианты поля select: строки по порядку, запись списком целиком. */
const OptionsEditor = ({
  options,
  disabled,
  onChange,
}: {
  options: string[];
  disabled: boolean;
  onChange: (next: string[]) => void;
}) => {
  const { t } = useTranslation("packForms");
  const [draft, setDraft] = useState("");
  return (
    <fieldset className="pf-options" data-testid="pf-field-options">
      <legend className="pf-label">{t("fields.options")}</legend>
      <ol className="pf-list compact">
        {options.map((option, i) => (
          <li key={`${option}-${String(i)}`} className="pf-option">
            <CommitInput
              value={option}
              ariaLabel={t("fields.option", { n: i + 1 })}
              disabled={disabled}
              onCommit={(next) => {
                const trimmed = next.trim();
                onChange(
                  trimmed
                    ? options.map((o, j) => (j === i ? trimmed : o))
                    : options.filter((_, j) => j !== i),
                );
              }}
            />
            {!disabled && (
              <OrderButtons
                index={i}
                count={options.length}
                label={option}
                onMove={(to) => {
                  const next = [...options];
                  const [item] = next.splice(i, 1);
                  next.splice(to, 0, item ?? "");
                  onChange(next);
                }}
                onDelete={() => {
                  onChange(options.filter((_, j) => j !== i));
                }}
              />
            )}
          </li>
        ))}
      </ol>
      {!disabled && (
        <div className="pf-inline-add">
          <input
            className="input pf-input"
            value={draft}
            placeholder={t("fields.optionNew")}
            aria-label={t("fields.optionNew")}
            data-testid="pf-option-new"
            onChange={(e) => {
              setDraft(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && draft.trim()) {
                e.preventDefault();
                onChange([...options, draft.trim()]);
                setDraft("");
              }
            }}
          />
          <Button
            size="xs"
            variant="secondary"
            disabled={!draft.trim() || options.includes(draft.trim())}
            onClick={() => {
              onChange([...options, draft.trim()]);
              setDraft("");
            }}
          >
            <Plus size="0.6875rem" />
            {t("fields.optionAdd")}
          </Button>
        </div>
      )}
    </fieldset>
  );
};

// ── окна ──

const RenameDialog = ({
  field,
  taken,
  onClose,
}: {
  field: string | null;
  taken: string[];
  onClose: () => void;
}) => {
  const { t } = useTranslation("packForms");
  const { act, busy } = useModelEditor();
  const [to, setTo] = useState("");
  const trimmed = to.trim();
  const problem = fieldKeyProblem(trimmed, [...taken, ...PERSON_KEYS]);
  const close = () => {
    setTo("");
    onClose();
  };
  return (
    <Modal
      isOpen={field !== null}
      onClose={close}
      title={t("fields.renameTitle", { key: field ?? "" })}
      description={t("fields.renameLead")}
      width={480}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            {t("cancel")}
          </Button>
          <Button
            disabled={busy || problem !== null || field === null}
            data-testid="pf-rename-submit"
            onClick={() => {
              if (field === null) return;
              void act({ action: "rename_field", field, to: trimmed }).then(
                (ok) => {
                  if (ok) close();
                },
              );
            }}
          >
            {t("fields.renameSubmit")}
          </Button>
        </>
      }
    >
      <FormRow
        label={t("fields.renameTo")}
        hint={
          trimmed && problem ? (
            <span className="pf-error-text">
              {t(`kit.idProblem.${problem}`)}
            </span>
          ) : (
            t("kit.idHint.key")
          )
        }
      >
        {(id) => (
          <input
            id={id}
            className="input mono"
            value={to}
            autoFocus
            data-testid="pf-rename-to"
            onChange={(e) => {
              setTo(e.target.value);
            }}
          />
        )}
      </FormRow>
    </Modal>
  );
};

const DeleteFieldDialog = ({
  field,
  onClose,
}: {
  field: string | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packForms");
  const { edit, busy, model } = useModelEditor();
  const lang = useLang();
  const usage = field ? usageOf(model, field) : [];
  return (
    <Modal
      isOpen={field !== null}
      onClose={onClose}
      title={t("fields.deleteTitle", { key: field ?? "" })}
      description={t("fields.deleteLead")}
      width={480}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            variant="danger"
            disabled={busy || field === null}
            data-testid="pf-delete-submit"
            onClick={() => {
              if (field === null) return;
              void edit(MANIFEST, [deleteOp(["meta_fields", field])]).then(
                (ok) => {
                  if (ok) onClose();
                },
              );
            }}
          >
            {t("fields.delete")}
          </Button>
        </>
      }
    >
      {usage.length > 0 && (
        <p className="pf-warn">
          <AlertTriangle size="0.75rem" aria-hidden="true" />
          {t("fields.deletePrinted", {
            docs: usage
              .map((u) => documentName(model, u.document, lang))
              .join(", "),
          })}
        </p>
      )}
    </Modal>
  );
};

// ── раздел ──

/** Поля анкеты и их группы (template-studio.md, 5.2; срез T11). */
export const FieldsSection = () => {
  const { t } = useTranslation("packForms");
  const { model, edit, readOnly } = useModelEditor();
  const lang = useLang();
  const data = asRecord(model.manifest.data);
  const fields = fieldsOf(data);
  const groups = groupsOf(data);
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newType, setNewType] = useState("string");
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const keys = fields.map((f) => f.key);

  return (
    <div className="pf-section" data-testid="pf-fields">
      <GroupsBlock groups={groups} fields={fields} />
      <FormBlock
        title={t("fields.title")}
        lead={t("fields.lead")}
        actions={
          !readOnly && (
            <Button
              size="xs"
              variant="secondary"
              onClick={() => {
                setAdding(true);
              }}
              data-testid="pf-field-add"
            >
              <Plus size="0.6875rem" />
              {t("fields.add")}
            </Button>
          )
        }
      >
        {fields.length === 0 && <p className="pf-empty">{t("fields.empty")}</p>}
        <ul className="pf-list">
          {fields.map((field) => {
            const expanded = open === field.key;
            const printed = usageOf(model, field.key).length;
            const group = groups.find(
              (g) => g.id === asString(field.spec.group),
            );
            return (
              <li
                key={field.key}
                className={clsx("pf-item", expanded && "open")}
              >
                <button
                  type="button"
                  className="pf-item-toggle"
                  aria-expanded={expanded}
                  data-testid={`pf-field-${field.key}`}
                  onClick={() => {
                    setOpen(expanded ? null : field.key);
                  }}
                >
                  {expanded ? (
                    <ChevronDown size="0.75rem" />
                  ) : (
                    <ChevronRight size="0.75rem" />
                  )}
                  <span className="mono pf-id">{field.key}</span>
                  <span className="pf-item-label truncate">
                    {pickLocalized(field.spec.label, lang, "")}
                  </span>
                  <span className="pf-item-marks">
                    <Badge variant="subtle">
                      {t(
                        `fields.types.${asString(field.spec.type) || "string"}`,
                        {
                          defaultValue: asString(field.spec.type),
                        },
                      )}
                    </Badge>
                    {group && (
                      <Badge variant="default">
                        {pickLocalized(group.raw.label, lang, group.id)}
                      </Badge>
                    )}
                    {printed > 0 ? (
                      <Badge variant="info">
                        {t("fields.printedIn", { count: printed })}
                      </Badge>
                    ) : (
                      <Badge variant="warning">{t("fields.notPrinted")}</Badge>
                    )}
                  </span>
                </button>
                {expanded && (
                  <FieldCard
                    field={field}
                    groups={groups}
                    onRename={() => {
                      setRenaming(field.key);
                    }}
                    onDelete={() => {
                      setDeleting(field.key);
                    }}
                  />
                )}
              </li>
            );
          })}
        </ul>
      </FormBlock>
      <NewItemDialog
        isOpen={adding}
        title={t("fields.addTitle")}
        idLabel={t("fields.key")}
        taken={keys}
        onClose={() => {
          setAdding(false);
        }}
        extra={
          <FormRow label={t("fields.type")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("fields.type")}
                value={newType}
                testId="pf-new-type"
                options={FIELD_TYPES.map((v) => ({
                  value: v,
                  label: t(`fields.types.${v}`),
                }))}
                onChange={setNewType}
              />
            )}
          </FormRow>
        }
        onCreate={async (key, label) => {
          const spec: Raw = {
            type: newType,
            label: compactLocalized(label),
            required_at: "never",
          };
          const ok = await edit(MANIFEST, [
            has(data, "meta_fields") && fields.length > 0
              ? setOp(["meta_fields", key], spec)
              : setOp(["meta_fields"], { [key]: spec }),
          ]);
          if (ok) {
            setAdding(false);
            setOpen(key);
          }
        }}
      />
      <RenameDialog
        field={renaming}
        taken={keys}
        onClose={() => {
          if (renaming === open) setOpen(null);
          setRenaming(null);
        }}
      />
      <DeleteFieldDialog
        field={deleting}
        onClose={() => {
          setDeleting(null);
        }}
      />
    </div>
  );
};
