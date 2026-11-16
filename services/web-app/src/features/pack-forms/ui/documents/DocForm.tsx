import { useRef, useState } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@shared/ui";
import {
  ENGINES,
  KNOWN_DOC_GROUPS,
  SCOPES,
  STAFFING,
  docGroupLabelKey,
  fileGroups,
  versionLangs,
} from "../../lib/documents";
import { KINDS } from "../../lib/fields";
import { useRecordFocus } from "../../lib/focus";
import {
  asArray,
  asRecord,
  asString,
  asStrings,
  compactLocalized,
  deleteOp,
  insertOp,
  moveOp,
  optionalOps,
  setOp,
  type Raw,
  type YamlPath,
} from "../../lib/raw";
import { docManifest, useModelEditor } from "../../model/modelEditor";
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
import { NewItemDialog } from "../NewItemDialog";
import { DocLanguages } from "./DocLanguages";

type Write = (path: YamlPath, value: unknown, record: Raw) => void;

/** Путь файла в проекте: список из файлов папки документа и свой текст. */
const PathInput = ({
  label,
  value,
  choices,
  disabled,
  onCommit,
  testId,
}: {
  label: string;
  value: string;
  choices: string[];
  disabled: boolean;
  onCommit: (next: string) => void;
  testId: string;
}) => (
  <FormRow label={label}>
    {(id) => (
      <>
        <CommitInput
          id={id}
          mono
          ariaLabel={label}
          value={value}
          disabled={disabled}
          list={`${id}-files`}
          testId={testId}
          onCommit={(next) => {
            onCommit(next.trim());
          }}
        />
        <datalist id={`${id}-files`}>
          {choices.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>
      </>
    )}
  </FormRow>
);

const VariantCard = ({
  variant,
  index,
  langs,
  sources,
  write,
}: {
  variant: Raw;
  index: number;
  langs: string[];
  sources: string[];
  write: Write;
}) => {
  const { t } = useTranslation("packForms");
  const { readOnly } = useModelEditor();
  const path: YamlPath = ["variants", index];
  const variantLangs = asStrings(variant.supported_langs);
  return (
    <div className="pf-card single">
      <div className="pf-card-main">
        <LocalizedInput
          label={t("doc.variantLabel")}
          value={variant.label}
          disabled={readOnly}
          required
          onCommit={(next) => {
            write([...path, "label"], compactLocalized(next), variant);
          }}
        />
        <div className="pf-grid">
          <PathInput
            label={t("doc.sourceFile")}
            value={asString(variant.source_file)}
            choices={sources}
            disabled={readOnly}
            testId={`pf-variant-source-${String(index)}`}
            onCommit={(next) => {
              write([...path, "source_file"], next, variant);
            }}
          />
          <PathInput
            label={t("doc.outputFile")}
            value={asString(variant.output_file)}
            choices={[]}
            disabled={readOnly}
            testId={`pf-variant-output-${String(index)}`}
            onCommit={(next) => {
              write([...path, "output_file"], next, variant);
            }}
          />
          <FormRow label={t("doc.engine")} hint={t("doc.engineHint")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("doc.engine")}
                value={asString(variant.engine)}
                disabled={readOnly}
                options={[
                  { value: "", label: t("doc.engineDefault") },
                  ...ENGINES.map((e) => ({ value: e, label: e })),
                ]}
                onChange={(next) => {
                  write([...path, "engine"], next, variant);
                }}
              />
            )}
          </FormRow>
        </div>
        <LocalizedInput
          label={t("doc.outputName")}
          value={variant.output_name}
          disabled={readOnly}
          onCommit={(next) => {
            write([...path, "output_name"], compactLocalized(next), variant);
          }}
        />
        <ChipToggles
          label={t("doc.langs")}
          hint={t("doc.variantLangsHint")}
          at={`/variants/${String(index)}/supported_langs`}
          options={langs.map((l) => ({ value: l, label: l }))}
          value={variantLangs}
          disabled={readOnly}
          onChange={(next) => {
            write([...path, "supported_langs"], next, variant);
          }}
        />
      </div>
    </div>
  );
};

/**
 * Форма `doc.yaml` документа (5.3; T12): названия, файлы, требования, языки,
 * вид работы и состав, группа навигации, варианты и перевод файлов.
 */
export const DocForm = ({
  docId,
  at,
}: {
  docId: string;
  at?: string | null | undefined;
}) => {
  const { t } = useTranslation("packForms");
  const root = useRef<HTMLDivElement>(null);
  useRecordFocus(root, at, docId);
  const { model, edit, readOnly, busy } = useModelEditor();
  const [addingVariant, setAddingVariant] = useState(false);
  const doc = model.documents.find((d) => d.id === docId);
  if (!doc?.manifest) {
    return (
      <p className="pf-empty pf-section">
        {t("doc.notInRoster", { id: docId })}
      </p>
    );
  }
  const file = docManifest(doc.id);
  const data = asRecord(doc.data);
  const langs = versionLangs(model.manifest.data);
  const write: Write = (path, value, record) => {
    void edit(file, optionalOps(record, path, value));
  };
  // Пути в проекте без языкового кода: `report/report.tex`.
  const sources = fileGroups(doc.files).map((g) => g.bare);
  const variants = asArray(data.variants).map(asRecord);
  const kinds = asStrings(data.supported_kinds);
  const staffing = asStrings(data.supported_staffing);
  const group = asString(data.group);

  return (
    <div className="pf-section" data-testid="pf-doc-form" ref={root}>
      <FormBlock title={t("doc.title", { id: doc.id })} lead={t("doc.lead")}>
        <LocalizedInput
          label={t("doc.name")}
          value={data.name}
          disabled={readOnly}
          required
          testId="pf-doc-name"
          onCommit={(next) => {
            write(["name"], compactLocalized(next), data);
          }}
        />
        <div className="pf-grid">
          <LocalizedInput
            label={t("doc.code")}
            value={data.code}
            disabled={readOnly}
            onCommit={(next) => {
              write(["code"], compactLocalized(next), data);
            }}
          />
          <LocalizedInput
            label={t("doc.outputName")}
            value={data.output_name}
            disabled={readOnly}
            onCommit={(next) => {
              write(["output_name"], compactLocalized(next), data);
            }}
          />
        </div>
        <div className="pf-grid">
          <PathInput
            label={t("doc.sourceFile")}
            value={asString(data.source_file)}
            choices={sources}
            disabled={readOnly}
            testId="pf-doc-source-file"
            onCommit={(next) => {
              write(["source_file"], next, data);
            }}
          />
          <PathInput
            label={t("doc.outputFile")}
            value={asString(data.output_file)}
            choices={[]}
            disabled={readOnly}
            testId="pf-doc-output-file"
            onCommit={(next) => {
              write(["output_file"], next, data);
            }}
          />
          <FormRow label={t("doc.gostRef")} hint={t("doc.gostRefHint")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("doc.gostRef")}
                value={asString(data.gost_ref)}
                disabled={readOnly}
                testId="pf-doc-gost"
                options={[
                  { value: "", label: t("doc.noGost") },
                  ...model.checks.map((c) => ({ value: c, label: c })),
                ]}
                onChange={(next) => {
                  write(["gost_ref"], next, data);
                }}
              />
            )}
          </FormRow>
          <FormRow label={t("doc.scope")} hint={t("doc.scopeHint")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("doc.scope")}
                value={asString(data.scope) || "shared"}
                disabled={readOnly}
                options={SCOPES.map((s) => ({
                  value: s,
                  label: t(`doc.scopes.${s}`),
                }))}
                onChange={(next) => {
                  void edit(file, [setOp(["scope"], next)]);
                }}
              />
            )}
          </FormRow>
          <FormRow label={t("documents.group")} hint={t("documents.groupHint")}>
            {(id) => (
              <SelectInput
                id={id}
                ariaLabel={t("documents.group")}
                value={group}
                disabled={readOnly}
                options={[
                  { value: "", label: t("documents.noGroup") },
                  ...KNOWN_DOC_GROUPS.map((g) => ({
                    value: g,
                    label: `${t(docGroupLabelKey(g))} (${g})`,
                  })),
                ]}
                onChange={(next) => {
                  write(["group"], next, data);
                }}
              />
            )}
          </FormRow>
          <CheckInput
            label={t("doc.required")}
            hint={t("doc.requiredHint")}
            checked={data.required === true}
            disabled={readOnly}
            testId="pf-doc-required"
            onChange={(next) => {
              void edit(file, [setOp(["required"], next)]);
            }}
          />
        </div>
        <ChipToggles
          label={t("doc.langs")}
          hint={t("doc.langsHint")}
          options={langs.map((l) => ({ value: l, label: l }))}
          value={asStrings(data.supported_langs)}
          disabled={readOnly}
          testId="pf-doc-langs"
          at="/supported_langs"
          onChange={(next) => {
            write(["supported_langs"], next, data);
          }}
        />
        <div className="pf-grid">
          <ChipToggles
            label={t("doc.kinds")}
            at="/supported_kinds"
            options={KINDS.map((k) => ({ value: k, label: t(`kinds.${k}`) }))}
            value={kinds.length ? kinds : KINDS}
            disabled={readOnly}
            onChange={(next) => {
              write(
                ["supported_kinds"],
                next.length === KINDS.length ? [] : next,
                data,
              );
            }}
          />
          <ChipToggles
            label={t("doc.staffing")}
            at="/supported_staffing"
            options={STAFFING.map((s) => ({
              value: s,
              label: t(`doc.staffingValues.${s}`),
            }))}
            value={staffing.length ? staffing : STAFFING}
            disabled={readOnly}
            onChange={(next) => {
              write(
                ["supported_staffing"],
                next.length === STAFFING.length ? [] : next,
                data,
              );
            }}
          />
        </div>
      </FormBlock>
      <FormBlock
        title={t("languages.filesTitle")}
        lead={t("languages.filesLead")}
      >
        <DocLanguages doc={doc} langs={langs} />
      </FormBlock>
      <FormBlock
        title={t("doc.variants")}
        lead={t("doc.variantsLead")}
        actions={
          !readOnly && (
            <Button
              size="xs"
              variant="secondary"
              onClick={() => {
                setAddingVariant(true);
              }}
              data-testid="pf-variant-add"
            >
              <Plus size="0.6875rem" />
              {t("doc.variantAdd")}
            </Button>
          )
        }
      >
        {variants.length === 0 && (
          <p className="pf-empty">{t("doc.noVariants")}</p>
        )}
        <ol className="pf-list">
          {variants.map((variant, i) => {
            const id = asString(variant.id);
            return (
              <li
                key={`${id}-${String(i)}`}
                className="pf-item"
                data-testid={`pf-variant-${id}`}
                data-pf-at={`/variants/${String(i)}`}
              >
                <div className="pf-item-head">
                  <span className="mono pf-id">{id}</span>
                  <span className="pf-item-sub" />
                  {!readOnly && (
                    <OrderButtons
                      index={i}
                      count={variants.length}
                      label={id}
                      disabled={busy}
                      onMove={(to) => {
                        void edit(file, [moveOp(["variants"], i, to)]);
                      }}
                      onDelete={() => {
                        void edit(file, [deleteOp(["variants", i])]);
                      }}
                    />
                  )}
                </div>
                <VariantCard
                  variant={variant}
                  index={i}
                  langs={langs}
                  sources={sources}
                  write={write}
                />
              </li>
            );
          })}
        </ol>
      </FormBlock>
      <NewItemDialog
        isOpen={addingVariant}
        title={t("doc.variantAddTitle")}
        idLabel={t("doc.variantId")}
        pattern="id"
        taken={variants.map((v) => asString(v.id))}
        onClose={() => {
          setAddingVariant(false);
        }}
        onCreate={async (id, label) => {
          const value = { id, label: compactLocalized(label) };
          const ok = await edit(file, [
            Array.isArray(data.variants)
              ? insertOp(["variants"], variants.length, value)
              : setOp(["variants"], [value]),
          ]);
          if (ok) setAddingVariant(false);
        }}
      />
    </div>
  );
};
