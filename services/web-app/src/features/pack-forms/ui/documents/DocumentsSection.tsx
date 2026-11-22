import { useState } from "react";
import { AlertTriangle, ExternalLink, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  usePackDocLibrary,
  type PackModelDocument,
} from "@entities/pack-studio";
import { Badge, Button, Modal, Spinner } from "@shared/ui";
import {
  KNOWN_DOC_GROUPS,
  docGroupLabelKey,
  fileGroups,
  isBundle,
  versionLangs,
} from "../../lib/documents";
import { langName } from "../../lib/langName";
import {
  asRecord,
  asString,
  compactLocalized,
  moveOp,
  optionalOps,
  pickLocalized,
} from "../../lib/raw";
import { docManifest, useModelEditor } from "../../model/modelEditor";
import { FormBlock, FormRow, OrderButtons, SelectInput } from "../kit";
import { NewItemDialog } from "../NewItemDialog";
import type { VersionSectionProps } from "../VersionForm";

const useLang = () => {
  const { i18n } = useTranslation();
  return i18n.language.startsWith("en") ? "en" : "ru";
};

/** Группа навигации документа: правка в `doc.yaml` (у записи v1 в ростере). */
const GroupSelect = ({
  doc,
  index,
}: {
  doc: PackModelDocument;
  index: number;
}) => {
  const { t } = useTranslation("packForms");
  const { edit, readOnly } = useModelEditor();
  const data = asRecord(doc.data);
  const current = asString(data.group);
  const options = [
    { value: "", label: t("documents.noGroup") },
    ...KNOWN_DOC_GROUPS.map((g) => ({
      value: g,
      label: t(docGroupLabelKey(g)),
    })),
  ];
  return (
    <SelectInput
      ariaLabel={t("documents.group")}
      value={current}
      disabled={readOnly}
      testId={`pf-doc-group-${doc.id}`}
      options={options}
      onChange={(next) => {
        void (isBundle(doc)
          ? edit(docManifest(doc.id), optionalOps(data, ["group"], next))
          : edit(
              "version.yaml",
              optionalOps(data, ["documents", index, "group"], next),
            ));
      }}
    />
  );
};

const RemoveDialog = ({
  doc,
  onClose,
}: {
  doc: PackModelDocument | null;
  onClose: () => void;
}) => {
  const { t } = useTranslation("packForms");
  const lang = useLang();
  const { act, busy } = useModelEditor();
  return (
    <Modal
      isOpen={doc !== null}
      onClose={onClose}
      title={t("documents.removeTitle", {
        name: doc ? pickLocalized(asRecord(doc.data).name, lang, doc.id) : "",
      })}
      description={t("documents.removeLead")}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button
            variant="danger"
            disabled={busy || doc === null}
            data-testid="pf-doc-remove-submit"
            onClick={() => {
              if (doc === null) return;
              void act({ action: "remove_document", document: doc.id }).then(
                (ok) => {
                  if (ok) onClose();
                },
              );
            }}
          >
            {t("documents.remove")}
          </Button>
        </>
      }
    >
      {doc && doc.references.length > 0 && (
        <div className="pf-warn" data-testid="pf-doc-references">
          <AlertTriangle size="0.75rem" aria-hidden="true" />
          <div>
            {t("documents.referenced")}
            <ul className="pf-refs mono">
              {doc.references.map((ref) => (
                <li key={ref}>{ref}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </Modal>
  );
};

/** Источник нового документа: пустой или копия документа из паков пространства. */
const SourcePicker = ({
  workspaceId,
  value,
  onChange,
}: {
  workspaceId: string;
  value: string;
  onChange: (next: string) => void;
}) => {
  const { t } = useTranslation("packForms");
  const lang = useLang();
  const library = usePackDocLibrary(workspaceId, true);
  return (
    <FormRow label={t("documents.source")} hint={t("documents.sourceHint")}>
      {(id) =>
        library.isPending ? (
          <Spinner size="sm" />
        ) : (
          <SelectInput
            id={id}
            ariaLabel={t("documents.source")}
            value={value}
            testId="pf-doc-source"
            options={[
              { value: "", label: t("documents.blank") },
              ...(library.data?.documents ?? []).map((d) => ({
                value: d.path,
                label: `${pickLocalized(d.name, lang, d.id)} · ${d.pack}/${d.template} ${d.version}`,
              })),
            ]}
            onChange={onChange}
          />
        )
      }
    </FormRow>
  );
};

/** Ростер документов: порядок, группы навигации, новый и удаляемый документ (5.3; T12). */
export const DocumentsSection = ({
  workspaceId,
  onOpenFile,
}: VersionSectionProps) => {
  const { t, i18n } = useTranslation("packForms");
  const { model, edit, act, readOnly, busy } = useModelEditor();
  const lang = useLang();
  const langs = versionLangs(model.manifest.data);
  const [adding, setAdding] = useState(false);
  const [source, setSource] = useState("");
  const [removing, setRemoving] = useState<PackModelDocument | null>(null);
  const docs = model.documents;
  const base = model.manifest.path.replace(/version\.yaml$/, "");
  let previousGroup: string | null = null;

  return (
    <div className="pf-section" data-testid="pf-documents">
      <FormBlock
        title={t("documents.title")}
        lead={t("documents.lead")}
        actions={
          !readOnly && (
            <Button
              size="xs"
              variant="secondary"
              onClick={() => {
                setAdding(true);
              }}
              data-testid="pf-doc-add"
            >
              <Plus size="0.6875rem" />
              {t("documents.add")}
            </Button>
          )
        }
      >
        {docs.length === 0 && (
          <p className="pf-empty">{t("documents.empty")}</p>
        )}
        <ol className="pf-list">
          {docs.map((doc, i) => {
            const data = asRecord(doc.data);
            const group = asString(data.group);
            const divider = i > 0 && group !== previousGroup;
            previousGroup = group;
            const present = new Set(doc.files.map((f) => f.lang));
            const shared = fileGroups(doc.files).some((g) => "" in g.byLang);
            return (
              <li
                key={doc.id}
                className={divider ? "pf-item pf-divided" : "pf-item"}
                data-testid={`pf-doc-${doc.id}`}
              >
                <div className="pf-item-head">
                  <span className="pf-item-title truncate" title={doc.id}>
                    {pickLocalized(data.name, lang, doc.id)}
                  </span>
                  <span className="pf-item-marks">
                    {data.required === true && (
                      <Badge variant="info">{t("documents.required")}</Badge>
                    )}
                    {asString(data.scope) === "personal" && (
                      <Badge variant="subtle">{t("documents.personal")}</Badge>
                    )}
                    {langs.map((code) => (
                      <Badge
                        key={code}
                        variant={
                          present.has(code) || shared ? "default" : "warning"
                        }
                        title={
                          present.has(code)
                            ? t("languages.present")
                            : shared
                              ? t("languages.shared")
                              : t("languages.missing")
                        }
                      >
                        {langName(code, i18n.language)}
                      </Badge>
                    ))}
                    {!isBundle(doc) && <Badge variant="warning">v1</Badge>}
                  </span>
                  {!readOnly && (
                    <OrderButtons
                      index={i}
                      count={docs.length}
                      label={pickLocalized(data.name, lang, doc.id)}
                      disabled={busy}
                      onMove={(to) => {
                        void edit("version.yaml", [
                          moveOp(["documents"], i, to),
                        ]);
                      }}
                      onDelete={() => {
                        setRemoving(doc);
                      }}
                    />
                  )}
                </div>
                <div className="pf-grid">
                  <FormRow
                    label={t("documents.group")}
                    hint={t("documents.groupHint")}
                  >
                    {() => <GroupSelect doc={doc} index={i} />}
                  </FormRow>
                  {isBundle(doc) && onOpenFile && (
                    <div className="pf-row pf-row-end">
                      <Button
                        size="xs"
                        variant="ghost"
                        onClick={() => {
                          onOpenFile(`${base}files/${doc.id}/doc.yaml`);
                        }}
                        data-testid={`pf-doc-open-${doc.id}`}
                      >
                        <ExternalLink size="0.6875rem" />
                        {t("documents.open")}
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </FormBlock>
      <NewItemDialog
        isOpen={adding}
        title={t("documents.addTitle")}
        idLabel={t("documents.id")}
        idHint={t("documents.tech.idHint")}
        pattern="id"
        taken={docs.map((d) => d.id)}
        onClose={() => {
          setAdding(false);
          setSource("");
        }}
        extra={
          adding ? (
            <SourcePicker
              workspaceId={workspaceId}
              value={source}
              onChange={setSource}
            />
          ) : null
        }
        onCreate={async (id, label) => {
          const ok = await act({
            action: "add_document",
            document: id,
            name: compactLocalized(label),
            ...(source ? { source } : {}),
          });
          if (ok) {
            setAdding(false);
            setSource("");
          }
        }}
      />
      <RemoveDialog
        doc={removing}
        onClose={() => {
          setRemoving(null);
        }}
      />
    </div>
  );
};
