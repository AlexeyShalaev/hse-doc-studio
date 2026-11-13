import { useEffect, useMemo, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { useDocuments } from "@entities/document";
import { useProject } from "@entities/project";
import { useSignaturesState } from "@entities/signature";
import { useVersionDetail } from "@entities/template-catalog";
import { toast } from "@shared/lib";
import { CopyField, Modal, Notice } from "@shared/ui";
import { Spinner } from "@shared/ui/Spinner";
import {
  buildPackPresetYaml,
  type PackPreset,
  type PackPresetWarning,
} from "../lib/packPreset";

export type PackPresetDialogProps = {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  /** Документ, с вкладки которого открыли окно. */
  docId: string;
};

type Scope = "doc" | "all";

/**
 * «Скопировать как пресет шаблона» (docs/design/template-studio.md, 13): места подписей и метки даты
 * проекта как YAML для `version.yaml` пака. Окно только читает состояние подписей; при открытии
 * фрагмент сразу уходит в буфер, а текст остаётся в окне для ручного выделения.
 */
export const PackPresetDialog = ({
  isOpen,
  onClose,
  projectId,
  docId,
}: PackPresetDialogProps) => {
  const { t } = useTranslation("signatureStamper");
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      width={640}
      title={t("packPreset.title")}
      description={t("packPreset.description")}
      footer={
        <button type="button" className="btn" onClick={onClose}>
          {t("packPreset.close")}
        </button>
      }
    >
      {isOpen && <PackPresetBody projectId={projectId} docId={docId} />}
    </Modal>
  );
};

const PackPresetBody = ({
  projectId,
  docId,
}: {
  projectId: string;
  docId: string;
}) => {
  const { t } = useTranslation("signatureStamper");
  const projectQuery = useProject(projectId);
  const stateQuery = useSignaturesState(projectId);
  const documentsQuery = useDocuments(projectId);
  const project = projectQuery.data;
  const state = stateQuery.data;
  const documents = documentsQuery.data;
  const versionQuery = useVersionDetail(
    project?.lock.pack_id ?? "",
    project?.lock.template_id ?? "",
    project?.lock.version ?? "",
  );
  const version = versionQuery.data;
  const failed =
    projectQuery.isError ||
    stateQuery.isError ||
    documentsQuery.isError ||
    versionQuery.isError;
  const [scope, setScope] = useState<Scope>("doc");
  const [includeDisabled, setIncludeDisabled] = useState(false);

  const preset = useMemo((): PackPreset | null => {
    if (!project || !state || !documents || !version) return null;
    const { pack_id, template_id } = project.lock;
    return buildPackPresetYaml({
      placements: state.placements,
      documents,
      pack: {
        packId: pack_id,
        templateId: template_id,
        version: version.version,
        slots: version.signatures.slots,
        documents: version.documents,
        supportedStaffing: version.supported_staffing,
      },
      docIds: scope === "doc" ? [docId] : null,
      includeDisabled,
      texts: {
        header: t("packPreset.yaml.header", {
          pack: pack_id,
          template: template_id,
          version: version.version,
        }),
        hint: t("packPreset.yaml.hint"),
        asInPack: t("packPreset.yaml.asInPack"),
      },
    });
  }, [project, state, documents, version, scope, includeDisabled, docId, t]);

  // Первый готовый фрагмент копируется сам: это и есть действие пункта меню. Смена документов
  // или галочки в окне уже не копирует: для этого кнопка «Копировать».
  const autoCopied = useRef(false);
  useEffect(() => {
    if (autoCopied.current || preset === null) return;
    autoCopied.current = true;
    if (preset.yaml === "") return;
    // Без буфера (небезопасный адрес, нет прав) `clipboard` бросает сразу: ловим в цепочке.
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(preset.yaml))
      .then(() => {
        toast.success(t("packPreset.copied"));
      })
      .catch(() => {
        toast.warning(t("packPreset.copyFailed"));
      });
  }, [preset, t]);

  if (preset === null && failed) {
    return <Notice tone="err" role="alert" text={t("packPreset.loadFailed")} />;
  }
  if (preset === null) {
    return (
      <div className="flex justify-center" style={{ padding: "1.5rem" }}>
        <Spinner size="sm" />
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ gap: "0.75rem" }}>
      <div
        className="flex items-center"
        style={{ gap: "0.75rem", flexWrap: "wrap" }}
      >
        <div
          className="seg"
          role="radiogroup"
          aria-label={t("packPreset.scope.label")}
        >
          {(["doc", "all"] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={scope === value}
              className={scope === value ? "active" : undefined}
              onClick={() => {
                setScope(value);
              }}
            >
              {t(`packPreset.scope.${value}`)}
            </button>
          ))}
        </div>
        <label
          className="flex items-center"
          style={{ gap: "0.375rem", fontSize: "0.75rem" }}
        >
          <input
            type="checkbox"
            checked={includeDisabled}
            onChange={(event) => {
              setIncludeDisabled(event.target.checked);
            }}
          />
          {t("packPreset.includeDisabled")}
        </label>
      </div>

      {preset.yaml === "" ? (
        <Notice tone="info" role="status" text={t("packPreset.empty")} />
      ) : (
        <CopyField
          value={preset.yaml}
          label={t("packPreset.fieldLabel")}
          multiline
          wrap="spaces"
          rows={Math.min(18, Math.max(6, preset.yaml.split("\n").length))}
          onCopied={() => {
            toast.success(t("packPreset.copied"));
          }}
        />
      )}

      {preset.warnings.length > 0 && (
        <div
          className="flex flex-col"
          style={{ gap: "0.375rem" }}
          data-testid="pack-preset-warnings"
        >
          {preset.warnings.map((warning) => (
            <Notice
              key={JSON.stringify(warning)}
              tone={warning.code === "disabled" ? "info" : "warn"}
              text={warningText(warning, t)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const warningText = (warning: PackPresetWarning, t: TFunction): string => {
  switch (warning.code) {
    case "custom_slot":
      return t("packPreset.warn.customSlot", { slot: warning.slot });
    case "not_applicable":
      return t("packPreset.warn.notApplicable", warning);
    case "per_author_shared":
      return t("packPreset.warn.perAuthorShared", warning);
    case "duplicate":
      return t("packPreset.warn.duplicate", {
        slot: warning.slot,
        doc: warning.doc,
        kept: warning.kept,
        skipped: warning.skipped.join(", "),
      });
    case "invalid_place":
      return t("packPreset.warn.invalidPlace", {
        slot: warning.slot,
        doc: warning.doc,
        problem: t(`packPreset.problem.place.${warning.problem}`),
      });
    case "invalid_date":
      return t("packPreset.warn.invalidDate", {
        slot: warning.slot,
        doc: warning.doc,
        index: warning.index,
        problem: t(`packPreset.problem.date.${warning.problem}`),
      });
    case "too_many_dates":
      return t("packPreset.warn.tooManyDates", warning);
    case "disabled":
      return t("packPreset.warn.disabled", { count: warning.count });
  }
};
